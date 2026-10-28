"""Fit SDV HMA on the local Employees dataset and stage honeytoken rows.

This script reads the source database and writes model/data artifacts only. It
does not insert, update, or delete any MySQL rows.
"""

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from sdv.metadata import Metadata
from sdv.multi_table import HMASynthesizer
from sdv.utils import load_synthesizer

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "database" / "hma_artifacts"
TABLES = ("employee", "dept_emp", "dept_manager", "salary", "title")
CHILD_TABLES = ("dept_emp", "dept_manager", "salary", "title")
DATE_COLUMNS = {
    "employee": ("birth_date", "hire_date"),
    "dept_emp": ("from_date", "to_date"),
    "dept_manager": ("from_date", "to_date"),
    "salary": ("from_date", "to_date"),
    "title": ("from_date", "to_date"),
}
# Demo A and Demo B share the employee database. Demo B owns 910001-910050;
# reserve the adjacent range for Demo A's HMA candidates.
TOKEN_START_DEFAULT = 910051


def connect():
    user = os.getenv("READER_USER") or os.environ["DB_USER"]
    password = os.getenv("READER_PASSWORD") or os.environ["DB_PASSWORD"]
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=user,
        password=password,
        database=os.getenv("DB_NAME", "employee"),
    )


def load_source_data():
    connection = connect()
    try:
        cursor = connection.cursor(dictionary=True)
        data = {}
        for table in TABLES:
            # Exclude existing honeytokens from the training population.
            cursor.execute(f"SELECT * FROM `{table}` WHERE emp_no < 900000")
            rows = cursor.fetchall()
            if not rows:
                raise RuntimeError(f"Source table `{table}` is empty")
            frame = pd.DataFrame(rows)
            for column in DATE_COLUMNS[table]:
                if column not in frame.columns:
                    continue
                # Ordinal day numbers avoid pandas' timestamp ceiling (year
                # 2262); the Employees DB uses 9999-01-01 as an open-ended date.
                frame[column] = frame[column].map(
                    lambda value: value.date().toordinal()
                    if isinstance(value, datetime)
                    else value.toordinal()
                    if isinstance(value, date)
                    else None
                )
            data[table] = frame
        cursor.execute("SELECT dept_no FROM department")
        department_ids = {row["dept_no"] for row in cursor.fetchall()}
        if not department_ids:
            raise RuntimeError("Source table `department` is empty")
        cursor.execute("SELECT emp_no FROM employee WHERE emp_no >= 900000")
        occupied_token_range = {int(row["emp_no"]) for row in cursor.fetchall()}
        return data, department_ids, occupied_token_range
    finally:
        connection.close()


def build_metadata(data):
    # Child table composite primary keys are not supported by the free HMA
    # workflow. Surrogate IDs let HMA model the parent-child row relationships;
    # those helper IDs are removed before insertion into MySQL.
    model_data = {name: frame.copy() for name, frame in data.items()}
    for table in CHILD_TABLES:
        model_data[table]["_sdv_row_id"] = range(1, len(model_data[table]) + 1)

    metadata = Metadata.detect_from_dataframes(
        model_data,
        infer_keys=None,
    )
    metadata.update_column("emp_no", sdtype="id", table_name="employee")
    metadata.set_primary_key("emp_no", table_name="employee")

    for table in CHILD_TABLES:
        metadata.update_column("_sdv_row_id", sdtype="id", table_name=table)
        metadata.set_primary_key("_sdv_row_id", table_name=table)
        metadata.update_column("emp_no", sdtype="id", table_name=table)
        metadata.add_relationship(
            parent_table_name="employee",
            child_table_name=table,
            parent_primary_key="emp_no",
            child_foreign_key="emp_no",
        )

    metadata.validate()
    metadata.validate_data(model_data)
    return model_data, metadata


def choose_free_token_start(requested_start, count, occupied_ids):
    start = requested_start
    while any(emp_no in occupied_ids for emp_no in range(start, start + count)):
        start += count
    return start


def remap_synthetic_data(synthetic_data, department_ids, token_start, token_count):
    employees = synthetic_data["employee"].copy().reset_index(drop=True)
    if len(employees) != token_count:
        raise RuntimeError(
            f"SDV returned {len(employees)} employees; expected {token_count}"
        )

    old_ids = employees["emp_no"].tolist()
    new_ids = list(range(token_start, token_start + token_count))
    id_map = dict(zip(old_ids, new_ids))
    employees["emp_no"] = new_ids

    result = {"employee": employees}
    for table in CHILD_TABLES:
        frame = synthetic_data[table].copy()
        frame = frame[frame["emp_no"].isin(id_map)].copy()
        frame["emp_no"] = frame["emp_no"].map(id_map)
        frame = frame.drop(columns=["_sdv_row_id"], errors="ignore")

        if "dept_no" in frame.columns:
            frame = frame[frame["dept_no"].isin(department_ids)].copy()

        # The MySQL sample schema uses composite keys, even though HMA models
        # helper surrogate keys. Remove duplicate business keys before staging.
        business_keys = {
            "dept_emp": ["emp_no", "dept_no"],
            "dept_manager": ["emp_no", "dept_no"],
            "salary": ["emp_no", "from_date"],
            "title": ["emp_no", "title", "from_date"],
        }[table]
        frame = frame.drop_duplicates(subset=business_keys, keep="first")
        result[table] = frame.reset_index(drop=True)

    # Convert modeled ordinal values back to MySQL DATE strings. Values are
    # clipped to Python's supported calendar range before conversion.
    for table, columns in DATE_COLUMNS.items():
        frame = result[table]
        for column in columns:
            if column not in frame.columns:
                continue

            def ordinal_to_date(value):
                if pd.isna(value):
                    return None
                ordinal = int(round(float(value)))
                ordinal = min(max(ordinal, date.min.toordinal()), date.max.toordinal())
                return date.fromordinal(ordinal).isoformat()

            frame[column] = frame[column].map(ordinal_to_date)

        # Preserve the Employees schema's temporal invariant. HMA models each
        # field's distribution, so a small number of sampled intervals can
        # otherwise end before their start date.
        if "from_date" in frame.columns and "to_date" in frame.columns:
            invalid = frame.apply(
                lambda row: bool(row["to_date"])
                and row["to_date"] < row["from_date"],
                axis=1,
            )
            frame.loc[invalid, "to_date"] = frame.loc[invalid, "from_date"]

    # Each honeytoken must be visible as a current employee in exactly one
    # department. Preserve HMA's first generated department as Demo A's
    # placement, and make any additional memberships historical.
    dept_emp = result["dept_emp"].copy()
    hire_dates = dict(zip(result["employee"]["emp_no"], result["employee"]["hire_date"]))
    for emp_no in new_ids:
        indices = dept_emp.index[dept_emp["emp_no"] == emp_no].tolist()
        if not indices:
            raise RuntimeError(f"HMA generated no department row for employee {emp_no}")
        active_index = indices[0]
        dept_emp.at[active_index, "from_date"] = hire_dates[emp_no]
        dept_emp.at[active_index, "to_date"] = "9999-01-01"
        for historical_index in indices[1:]:
            if str(dept_emp.at[historical_index, "to_date"]) == "9999-01-01":
                dept_emp.at[historical_index, "to_date"] = dept_emp.at[historical_index, "from_date"]
    result["dept_emp"] = dept_emp

    # These rows are needed by the existing employee lookup demo.
    for table in ("salary", "dept_emp"):
        covered = set(result[table]["emp_no"])
        missing = sorted(set(new_ids) - covered)
        if missing:
            raise RuntimeError(
                f"HMA generated no {table} row for {len(missing)} employee(s). "
                "No candidate files were applied. Regenerate the sample or review "
                "the source data before relaxing this requirement."
            )

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--token-start", type=int, default=None)
    parser.add_argument(
        "--reuse-model",
        action="store_true",
        help="Reuse the local employee_hma.pkl instead of re-fitting HMA.",
    )
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_data, department_ids, occupied_ids = load_source_data()
    requested_start = (
        args.token_start
        or int(os.getenv("HONEYTOKEN_START", str(TOKEN_START_DEFAULT)))
    )
    token_start = choose_free_token_start(requested_start, args.count, occupied_ids)
    if token_start != requested_start:
        print(
            f"ID range {requested_start}-{requested_start + args.count - 1} is "
            f"occupied. Using next free range {token_start}-{token_start + args.count - 1}."
        )

    model_path = ARTIFACT_DIR / "employee_hma.pkl"
    if args.reuse_model:
        if not model_path.exists():
            raise FileNotFoundError(f"No saved HMA model at {model_path}")
        synthesizer = load_synthesizer(filepath=str(model_path))
    else:
        model_data, metadata = build_metadata(source_data)
        metadata.save_to_json(str(ARTIFACT_DIR / "metadata.json"), mode="overwrite")
        synthesizer = HMASynthesizer(metadata, locales=["en_US"], verbose=False)
        synthesizer.fit(model_data)
        synthesizer.save(str(model_path))

    # `sample` sets the exact parent-table count and scales connected tables.
    sampled = synthesizer.sample(num_rows=args.count, main_table_name="employee")
    candidates = remap_synthetic_data(
        sampled,
        department_ids,
        token_start,
        args.count,
    )
    for table, frame in candidates.items():
        frame.to_csv(ARTIFACT_DIR / f"{table}.csv", index=False)

    manifest = {
        "method": "SDV HMASynthesizer",
        "token_count": args.count,
        "token_start": token_start,
        "token_end": token_start + args.count - 1,
        "source_database": os.getenv("DB_NAME", "employee"),
        "source_tables": list(TABLES),
        "training_filter": "Excluded emp_no >= 900000 to prevent existing honeytokens entering HMA training.",
        "department_table": "Existing reference table; not synthesized",
        "date_handling": "Modeled as ordinal days and converted back to ISO dates; supports 9999-01-01 sentinel.",
        "synthetic_row_counts": {
            table: int(len(frame)) for table, frame in candidates.items()
        },
        "created_on": date.today().isoformat(),
        "applied_to_mysql": False,
    }
    (ARTIFACT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("HMA model fitted and candidates staged. No MySQL rows were changed.")
    print(f"Artifacts: {ARTIFACT_DIR}")
    print(json.dumps(manifest["synthetic_row_counts"], indent=2))


if __name__ == "__main__":
    main()
