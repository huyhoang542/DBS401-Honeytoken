"""Remove only known old Demo A/B honeytokens from the local shared MySQL.

Default is a dry run. With --apply, deletes employee/child rows and registry
entries only inside the listed honeytoken ID ranges, clears both demos' lab
access/alert logs, and removes the local artifacts consumed by the dashboards.
It preserves schemas, ordinary employee rows, and the explicit before-reset CSV
backup. Run with MySQL administrator credentials.
"""

import argparse
import getpass
from pathlib import Path

import mysql.connector
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
RANGES = {
    "Demo A legacy range": ("honeytoken_security", 900001, 900050),
    "Demo B legacy range": ("honeytoken_security_b", 900001, 900050),
    "Demo A HMA range": ("honeytoken_security", 910051, 910100),
    "Demo B old token range": ("honeytoken_security_b", 910001, 910050),
}
CHILD_TABLES = ("salary", "dept_emp", "dept_manager", "title")
SECURITY_DATABASES = ("honeytoken_security", "honeytoken_security_b")
DASHBOARD_ARTIFACTS = (
    "RandomForest/results/ab_metrics.csv",
    "RandomForest/results/ab_metrics.json",
    "RandomForest/results/ab_query_results.csv",
    "RandomForest/results/ab_scenario_metrics.csv",
    "RandomForest/results/behavior_events.sqlite3",
    "RandomForest/results/live_attack_metrics.json",
    "RandomForest/results/live_attack_query_results.csv",
    "RandomForest/results/live_attack_session_results.csv",
    "RandomForest/results/live_attack_scenario_metrics.csv",
    "RandomForest/results/live_attack_placement_session_results.csv",
    "RandomForest/results/live_attack_placement_scenario_metrics.csv",
    "RandomForest/results/placement_history.csv",
    "RandomForest/models/random_forest_live_sim.joblib",
    "RandomForest/models/live_sim_model_metadata.json",
    "RandomForest/models/random_forest_synthetic.joblib",
    "RandomForest/models/model_metadata.json",
)


def clear_dashboard_artifacts():
    removed = []
    for relative in DASHBOARD_ARTIFACTS:
        path = (PROJECT / relative).resolve()
        if PROJECT.resolve() not in path.parents:
            raise RuntimeError(f"Refusing to remove a path outside the project: {path}")
        if path.is_file():
            path.unlink()
            removed.append(relative)
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the bounded reset.")
    args = parser.parse_args()

    env_a = dotenv_values(PROJECT / "SDV_HMA" / ".env")
    env_b = dotenv_values(PROJECT / "RandomForest" / ".env")
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
            cursor.execute(
                f"SELECT COUNT(*) FROM `{security_db}`.security_alerts a "
                f"JOIN `{security_db}`.honeytoken_registry r ON r.token_id=a.token_id "
                "WHERE r.emp_no BETWEEN %s AND %s", (start, end),
            )
            alerts = cursor.fetchone()[0]
            print(f"  {label}: IDs {start}-{end}; employee rows={employees}; registry rows={registered}; related alerts={alerts}")
        for security_db in SECURITY_DATABASES:
            cursor.execute(f"SELECT COUNT(*) FROM `{security_db}`.access_events")
            event_count = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM `{security_db}`.security_alerts")
            alert_count = cursor.fetchone()[0]
            print(f"  {security_db}: dashboard event rows={event_count}; alert rows={alert_count} (will be cleared with --apply)")
        local_artifacts = [relative for relative in DASHBOARD_ARTIFACTS if (PROJECT / relative).is_file()]
        print(f"  Local dashboard outputs/models: {len(local_artifacts)} files will be removed with --apply")
        if not args.apply:
            print("Dry run only. Re-run with --apply to remove the listed token rows and clear lab dashboard data/artifacts.")
            return

        # Keep token, registry, and dashboard log resets within one DB transaction.
        for _, (security_db, start, end) in RANGES.items():
            ids = list(range(start, end + 1))
            marks = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"SELECT token_id FROM `{security_db}`.honeytoken_registry "
                "WHERE emp_no BETWEEN %s AND %s", (start, end),
            )
            token_ids = [row[0] for row in cursor.fetchall()]
            if token_ids:
                token_marks = ",".join(["%s"] * len(token_ids))
                cursor.execute(
                    f"DELETE FROM `{security_db}`.security_alerts "
                    f"WHERE token_id IN ({token_marks})", token_ids,
                )
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name='placement_update_history'",
                (security_db,),
            )
            if cursor.fetchone()[0]:
                cursor.execute(
                    f"DELETE FROM `{security_db}`.placement_update_history "
                    "WHERE token_emp_no BETWEEN %s AND %s", (start, end),
                )
            for table in CHILD_TABLES:
                cursor.execute(f"DELETE FROM `{table}` WHERE emp_no IN ({marks})", ids)
            cursor.execute(f"DELETE FROM employee WHERE emp_no IN ({marks})", ids)
            cursor.execute(
                f"DELETE FROM `{security_db}`.honeytoken_registry WHERE emp_no IN ({marks})", ids
            )

        for security_db in SECURITY_DATABASES:
            cursor.execute(f"DELETE FROM `{security_db}`.security_alerts")
            cursor.execute(f"DELETE FROM `{security_db}`.access_events")

        connection.commit()
        removed = clear_dashboard_artifacts()
        print("Reset committed. Honeytoken rows, registry entries, lab alerts, and access-event dashboard logs were cleared.")
        print(f"Removed {len(removed)} local dashboard/result/model artifacts.")
        print("Database schemas, ordinary employee rows, and the explicit before-reset CSV backup were preserved.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
