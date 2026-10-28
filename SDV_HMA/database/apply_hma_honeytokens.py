"""Apply staged HMA rows to MySQL; defaults to a validation-only dry run."""

import argparse
import csv
import getpass
import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "database" / "hma_artifacts"
SECURITY_DB = os.getenv("SECURITY_DB_NAME", "honeytoken_security")
TABLES = ("employee", "salary", "dept_emp", "dept_manager", "title")


def read_csv(table):
    path = ARTIFACT_DIR / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing HMA candidate file: {path}")
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def connect(user=None, password=None):
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=user or os.environ["DB_USER"],
        password=password if password is not None else os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "employee"),
    )


def sql_value(value):
    if value in ("", "NaN", "nan", "None"):
        return None
    return value


def insert_rows(cursor, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    quoted_columns = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    query = f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders})"
    cursor.executemany(
        query,
        [tuple(sql_value(row.get(column)) for column in columns) for row in rows],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit candidate rows. Without this flag only validates ID collisions.",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Prompt for MySQL administrator credentials if honey_seeder lacks an INSERT grant.",
    )
    args = parser.parse_args()
    staged = {table: read_csv(table) for table in TABLES}
    employees = staged["employee"]
    if not employees:
        raise RuntimeError("HMA employee candidate file is empty")
    token_ids = [int(row["emp_no"]) for row in employees]
    if len(token_ids) != len(set(token_ids)):
        raise RuntimeError("Duplicate emp_no values in HMA candidate")

    if args.admin:
        admin_user = input("MySQL administrator user [root]: ").strip() or "root"
        admin_password = getpass.getpass("MySQL administrator password: ")
        connection = connect(admin_user, admin_password)
    else:
        connection = connect()
    try:
        cursor = connection.cursor()
        ids = (min(token_ids), max(token_ids))
        cursor.execute(
            "SELECT emp_no FROM employee WHERE emp_no BETWEEN %s AND %s LIMIT 1",
            ids,
        )
        if cursor.fetchone():
            raise RuntimeError("Candidate ID range exists in employee; no rows changed")
        cursor.execute(
            f"SELECT emp_no FROM `{SECURITY_DB}`.honeytoken_registry "
            "WHERE emp_no BETWEEN %s AND %s LIMIT 1",
            ids,
        )
        if cursor.fetchone():
            raise RuntimeError("Candidate ID range exists in registry; no rows changed")

        print("ID collision check passed.")
        print("Staged rows: " + ", ".join(
            f"{table}={len(rows)}" for table, rows in staged.items()
        ))
        if not args.apply:
            print("Dry run only. Re-run with --apply to commit these new IDs.")
            return

        # Insert child rows before registering the tokens, but employee must
        # precede its children due to the dataset's foreign keys.
        insert_order = ("employee", "salary", "dept_emp", "dept_manager", "title")
        for table in insert_order:
            insert_rows(cursor, table, staged[table])
        registry = [
            (emp_no, "HMA_SDV", "baseline_hma_v1") for emp_no in token_ids
        ]
        cursor.executemany(
            f"INSERT INTO `{SECURITY_DB}`.honeytoken_registry "
            "(emp_no, placement_strategy, placement_version) "
            "VALUES (%s, %s, %s)",
            registry,
        )
        connection.commit()
        print(f"Applied {len(token_ids)} HMA honeytokens transactionally.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
