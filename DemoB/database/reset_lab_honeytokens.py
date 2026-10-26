"""Reset only the known Demo A/B honeytoken ranges on the local shared MySQL.

Default is a dry run. With --apply, removes employee and child rows, token
registry entries, and monitoring alerts/events for both demos. It does not drop
schemas or touch employee IDs outside the explicitly bounded token ranges.
Run with MySQL administrator credentials.
"""

import argparse
import getpass
from pathlib import Path

import mysql.connector
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
RANGES = {
    "Demo A old Faker": ("honeytoken_security", 900001, 900050),
    "Demo A HMA range": ("honeytoken_security", 910051, 910100),
    "Demo B Faker": ("honeytoken_security_b", 910001, 910050),
}
CHILD_TABLES = ("salary", "dept_emp", "dept_manager", "title")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the bounded reset.")
    args = parser.parse_args()

    env_a = dotenv_values(PROJECT / "DemoA" / ".env")
    env_b = dotenv_values(PROJECT / "DemoB" / ".env")
    hosts = {env_a.get("DB_HOST", "localhost"), env_b.get("DB_HOST", "localhost")}
    ports = {int(env_a.get("DB_PORT", "3306")), int(env_b.get("DB_PORT", "3306"))}
    if not hosts <= {"localhost", "127.0.0.1"} or len(ports) != 1:
        raise SystemExit("Safety stop: both demos must point to the same local MySQL server.")
    if env_a.get("DB_NAME", "employee") != "employee" or env_b.get("DB_NAME", "employee") != "employee":
        raise SystemExit("Safety stop: reset is scoped to the shared employee database only.")

    user = input("MySQL administrator user [root]: ").strip() or "root"
    password = getpass.getpass("MySQL administrator password: ")
    connection = mysql.connector.connect(
        host=next(iter(hosts)), port=next(iter(ports)), user=user, password=password,
        database="employee",
    )
    try:
        cursor = connection.cursor()
        print("Planned reset scope:")
        for label, (security_db, start, end) in RANGES.items():
            cursor.execute("SELECT COUNT(*) FROM employee WHERE emp_no BETWEEN %s AND %s", (start, end))
            employees = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT COUNT(*) FROM `{security_db}`.honeytoken_registry WHERE emp_no BETWEEN %s AND %s",
                (start, end),
            )
            registered = cursor.fetchone()[0]
            print(f"  {label}: IDs {start}-{end}; employee rows={employees}; registry rows={registered}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to remove the listed token ranges and A/B monitoring logs.")
            return

        # Keep all table changes atomic. The two security DBs contain only the
        # lab's monitoring records; clearing them gives both demos a clean start.
        for security_db in ("honeytoken_security", "honeytoken_security_b"):
            cursor.execute(f"DELETE FROM `{security_db}`.security_alerts")
            cursor.execute(f"DELETE FROM `{security_db}`.access_events")

        for _, (security_db, start, end) in RANGES.items():
            ids = list(range(start, end + 1))
            marks = ",".join(["%s"] * len(ids))
            for table in CHILD_TABLES:
                cursor.execute(f"DELETE FROM `{table}` WHERE emp_no IN ({marks})", ids)
            cursor.execute(f"DELETE FROM employee WHERE emp_no IN ({marks})", ids)
            cursor.execute(
                f"DELETE FROM `{security_db}`.honeytoken_registry WHERE emp_no IN ({marks})", ids
            )

        connection.commit()
        print("Reset committed. Employee rows and registry entries in the listed ranges were removed.")
        print("Both demos' security alerts/events were cleared; schemas and ordinary employee rows remain.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
