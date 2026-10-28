"""Validate or transactionally apply staged HMA-content/RF-placement tokens."""
import argparse
import csv
import getpass
import json
import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "database" / "rf_artifacts"
TABLES = ("employee", "salary", "dept_emp", "dept_manager", "title")
SECURITY_DB = "honeytoken_security_b"

load_dotenv(ROOT / ".env")


def read_rows(table):
    path = ARTIFACT_DIR / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing candidate file: {path}. Run generate_rf_honeytokens.py first.")
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


def insert_rows(cursor, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    col_sql = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    query = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
    cursor.executemany(query, [tuple(row.get(column) or None for column in columns) for row in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit staged Demo B token rows")
    parser.add_argument("--admin", action="store_true", help="Prompt for MySQL administrator credentials")
    args = parser.parse_args()
    manifest_path = ARTIFACT_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}; run generate_rf_honeytokens.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("applied_to_mysql") is not False:
        raise RuntimeError("Candidate manifest is not marked as unapplied")
    staged = {table: read_rows(table) for table in TABLES}
    token_ids = [int(row["emp_no"]) for row in staged["employee"]]
    if not token_ids or len(token_ids) != len(set(token_ids)):
        raise RuntimeError("Empty or duplicate employee token IDs in candidate set")

    if args.admin:
        user = input("MySQL administrator user [root]: ").strip() or "root"
        password = getpass.getpass("MySQL administrator password: ")
        connection = connect(user, password)
    else:
        connection = connect()

    try:
        cursor = connection.cursor()
        bounds = (min(token_ids), max(token_ids))
        cursor.execute("SELECT emp_no FROM employee WHERE emp_no BETWEEN %s AND %s LIMIT 1", bounds)
        if cursor.fetchone():
            raise RuntimeError("Demo B candidate ID range is occupied in employee; no rows changed")
        cursor.execute(
            f"SELECT emp_no FROM `{SECURITY_DB}`.honeytoken_registry "
            "WHERE emp_no BETWEEN %s AND %s LIMIT 1", bounds)
        if cursor.fetchone():
            raise RuntimeError("Demo B candidate ID range is occupied in registry; no rows changed")
        print("ID collision check passed.")
        print("Staged rows: " + ", ".join(f"{table}={len(rows)}" for table, rows in staged.items()))
        print(f"Strategy: {manifest['placement_strategy']} | IDs: {bounds[0]}–{bounds[1]}")
        if not args.apply:
            print("Dry run only. Re-run with --apply --admin to insert the token rows.")
            return

        for table in TABLES:
            insert_rows(cursor, table, staged[table])
        registry_rows = [(emp_no, "RF_ADAPTIVE_HMA", manifest["placement_version"]) for emp_no in token_ids]
        cursor.executemany(
            f"INSERT INTO `{SECURITY_DB}`.honeytoken_registry "
            "(emp_no, placement_strategy, placement_version) VALUES (%s, %s, %s)",
            registry_rows,
        )
        connection.commit()
        manifest["applied_to_mysql"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Applied {len(token_ids)} Demo B tokens with Random Forest-selected placement.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
