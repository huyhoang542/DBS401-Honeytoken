"""Stage HMA-generated token records with Random-Forest-selected departments.

Record contents and relational rows are copied from Demo A's SDV/HMA candidates
so the experiment varies placement strategy while holding token content fixed.
The RF risk scores are derived from Demo B's trained live model telemetry.
This script only writes candidate CSV files; it does not modify MySQL.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import mysql.connector
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
HMA_DIR = PROJECT / "SDV_HMA" / "database" / "hma_artifacts"
OUTPUT_DIR = ROOT / "database" / "rf_artifacts"
TABLES = ("employee", "salary", "dept_emp", "dept_manager", "title")
SECURITY_DB = "honeytoken_security_b"
DATASET_DB = "employee"
TOKEN_START_DEFAULT = 910001
SENTINEL_DATE = "9999-01-01"

load_dotenv(ROOT / ".env")

# When invoked as ``python database\generate_rf_honeytokens.py``, Python adds
# the database/ directory (not RandomForest/) to sys.path. Add the project root so
# the shared adaptive placement allocator can be imported reliably.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read_hma_candidates():
    manifest_path = HMA_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(
            "Missing Demo A HMA candidates. Run from SDV_HMA: "
            "python database\\generate_hma_honeytokens.py (or --reuse-model)."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = {}
    for table in TABLES:
        path = HMA_DIR / f"{table}.csv"
        if not path.exists():
            raise SystemExit(f"Missing HMA candidate file: {path}")
        frames[table] = pd.read_csv(path, dtype=str, keep_default_na=False)
    count = len(frames["employee"])
    if count <= 0 or count != int(manifest.get("token_count", -1)):
        raise SystemExit("HMA candidate count does not match its manifest")
    return frames, manifest, count


def require_live_rf_model():
    metadata_path = ROOT / "models" / "live_sim_model_metadata.json"
    if not metadata_path.exists():
        raise SystemExit(
            "Missing live Random Forest metadata. Capture and train Demo B first: "
            "python evaluation\\run_live_attack_simulation.py --capture-only; "
            "python evaluation\\train_live_model.py"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = str(metadata.get("training_source", "")).lower()
    if metadata.get("model") != "RandomForestClassifier" or "mysql" not in source or "telemetry" not in source:
        raise SystemExit("B token placement requires the live Random Forest trained from MySQL telemetry")
    return metadata


def connect_reader():
    user = os.getenv("READER_USER")
    password = os.getenv("READER_PASSWORD")
    if not user or not password or password.startswith("YOUR_"):
        raise SystemExit("Set READER_USER and READER_PASSWORD in RandomForest/.env")
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=user,
        password=password,
        database=DATASET_DB,
    )


def load_risk_distribution():
    history_path = ROOT / "results" / "behavior_events.sqlite3"
    if not history_path.exists():
        raise SystemExit("No Demo B query history. Run department queries through query_gateway first.")
    with sqlite3.connect(history_path) as history_db:
        rows = history_db.execute(
            "SELECT department_no, AVG(risk_score) FROM behavior_events "
            "WHERE department_no IS NOT NULL GROUP BY department_no"
        ).fetchall()
    risk_by_department = {str(dept): float(score) for dept, score in rows if dept is not None}
    if not risk_by_department:
        raise SystemExit("No department risk scores. Run Demo B department queries through the gateway first.")
    return risk_by_department


def get_departments():
    connection = connect_reader()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT dept_no FROM department ORDER BY dept_no")
        departments = [str(row[0]) for row in cursor.fetchall()]
        cursor.close()
    finally:
        connection.close()
    if not departments:
        raise SystemExit("No departments found in the employee database")
    return departments


def remap_and_place(frames, token_start, departments, target_counts):
    employees = frames["employee"].copy().reset_index(drop=True)
    old_ids = employees["emp_no"].astype(int).tolist()
    new_ids = list(range(token_start, token_start + len(old_ids)))
    id_map = dict(zip(old_ids, new_ids))
    employees["emp_no"] = new_ids
    hire_dates = dict(zip(new_ids, employees["hire_date"].astype(str)))
    result = {"employee": employees}

    for table in ("salary", "dept_emp", "dept_manager", "title"):
        frame = frames[table].copy().reset_index(drop=True)
        frame["emp_no"] = frame["emp_no"].astype(int).map(id_map)
        if frame["emp_no"].isna().any():
            raise RuntimeError(f"HMA {table} contains an employee ID absent from the employee table")
        frame["emp_no"] = frame["emp_no"].astype(int)
        result[table] = frame

    dept_emp = result["dept_emp"].copy()
    # Use HMA's generated department assignment as the initial placement record.
    # Ensure each token has exactly one active assignment so the gateway and
    # department-targeted tests can observe it.
    assigned_departments = [dept for dept in departments for _ in range(target_counts.get(dept, 0))]
    if len(assigned_departments) != len(new_ids):
        raise RuntimeError("Risk allocation does not equal the HMA token count")
    active_indices = []
    for emp_no, target_department in zip(new_ids, assigned_departments):
        indices = dept_emp.index[dept_emp["emp_no"] == emp_no].tolist()
        if not indices:
            raise RuntimeError(f"HMA did not generate a department row for token {emp_no}")
        active_index = indices[0]
        active_indices.append(active_index)
        dept_emp.at[active_index, "dept_no"] = target_department
        dept_emp.at[active_index, "from_date"] = hire_dates[emp_no]
        dept_emp.at[active_index, "to_date"] = SENTINEL_DATE
        for historical_index in indices[1:]:
            if str(dept_emp.at[historical_index, "to_date"]) == SENTINEL_DATE:
                dept_emp.at[historical_index, "to_date"] = dept_emp.at[historical_index, "from_date"]

    # The Employees schema requires one row per (emp_no, dept_no). If the RF
    # destination duplicates a generated historical assignment, keep the active
    # row and drop only that redundant historical key.
    dept_emp["_active_priority"] = 0
    dept_emp.loc[active_indices, "_active_priority"] = 1
    dept_emp = dept_emp.sort_values("_active_priority", ascending=False)
    dept_emp = dept_emp.drop_duplicates(subset=["emp_no", "dept_no"], keep="first")
    dept_emp = dept_emp.drop(columns="_active_priority").reset_index(drop=True)
    active = dept_emp[dept_emp["to_date"].astype(str) == SENTINEL_DATE]
    if active["emp_no"].nunique() != len(new_ids) or len(active) != len(new_ids):
        raise RuntimeError("Could not establish exactly one active department placement per HMA token")
    result["dept_emp"] = dept_emp
    return result


def main():
    frames, hma_manifest, count = read_hma_candidates()
    rf_metadata = require_live_rf_model()
    departments = get_departments()
    risk_by_department = load_risk_distribution()

    from adaptive.placement import allocate_token_budget

    targets = allocate_token_budget(departments, risk_by_department, count)
    requested_start = int(os.getenv("TOKEN_START", str(TOKEN_START_DEFAULT)))
    generated = remap_and_place(frames, requested_start, departments, targets)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for table, frame in generated.items():
        frame.to_csv(OUTPUT_DIR / f"{table}.csv", index=False)

    manifest = {
        "content_generator": "SDV HMASynthesizer",
        "content_source_manifest": str(HMA_DIR / "manifest.json"),
        "placement_strategy": "RandomForest risk-weighted allocation by department",
        "placement_risk_source": rf_metadata.get("training_source"),
        "placement_version": "rf_adaptive_hma_v1",
        "token_count": count,
        "token_start": requested_start,
        "token_end": requested_start + count - 1,
        "database": DATASET_DB,
        "risk_by_department": {dept: risk_by_department.get(dept, 0.0) for dept in departments},
        "target_tokens_by_department": targets,
        "synthetic_row_counts": {table: int(len(frame)) for table, frame in generated.items()},
        "applied_to_mysql": False,
        "note": "HMA generates realistic relational content. Random Forest scores select department placement; it does not synthesize record fields.",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Demo B HMA content staged with Random Forest-selected department placement.")
    print("No MySQL rows were changed.")
    print(f"Artifacts: {OUTPUT_DIR}")
    print("Target token counts by department: " + json.dumps(targets, ensure_ascii=False))


if __name__ == "__main__":
    main()
