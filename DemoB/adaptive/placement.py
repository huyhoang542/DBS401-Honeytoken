"""Recommend or apply fixed-budget token redistribution across departments."""
import argparse
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SECURITY_DB = os.getenv("SECURITY_DB_NAME", "honeytoken_security_b")
DATASET_DB = os.getenv("DB_NAME", "employee")
if SECURITY_DB != "honeytoken_security_b" or DATASET_DB not in {"employee", "employee_ab"}:
    raise ValueError("Demo B requires SECURITY_DB_NAME=honeytoken_security_b and DB_NAME=employee or employee_ab")
HISTORY = ROOT / "results" / "placement_history.csv"


def allocate_token_budget(departments, risk_by_department, budget):
    """Allocate a fixed honeytoken budget in proportion to RF risk scores."""
    if budget < 0 or not departments:
        raise ValueError("A non-negative budget and at least one department are required")
    weights = {dept: max(0.0, float(risk_by_department.get(dept, 0.0))) + 0.01
               for dept in departments}
    total_weight = sum(weights.values())
    quotas = {dept: budget * weights[dept] / total_weight for dept in departments}
    targets = {dept: int(quotas[dept]) for dept in departments}
    remaining = budget - sum(targets.values())
    ranked = sorted(departments, key=lambda dept: (-(quotas[dept] - targets[dept]), dept))
    for dept in ranked[:remaining]:
        targets[dept] += 1
    return targets


def connection():
    user = os.getenv("PLACEMENT_USER") or os.getenv("DB_USER") or os.getenv("MONITOR_USER")
    password = os.getenv("PLACEMENT_PASSWORD") or os.getenv("DB_PASSWORD") or os.getenv("MONITOR_PASSWORD")
    if not user or not password:
        raise RuntimeError("Set PLACEMENT_USER/PLACEMENT_PASSWORD (or DB_USER/DB_PASSWORD) in .env")
    return mysql.connector.connect(host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")), user=user, password=password,
        database=DATASET_DB)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the inspected recommendation")
    parser.add_argument("--dry-run", action="store_true", help="Print the recommendation without writes (default)")
    args = parser.parse_args()
    db = connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT dept_no FROM department ORDER BY dept_no")
        departments = [row["dept_no"] for row in cursor.fetchall()]
        if not departments:
            raise RuntimeError("No departments found")
        cursor.execute(f"""SELECT r.emp_no, d.dept_no FROM {SECURITY_DB}.honeytoken_registry r
            JOIN dept_emp d ON d.emp_no=r.emp_no AND d.to_date='9999-01-01'
            WHERE r.is_active=TRUE ORDER BY r.emp_no""")
        tokens = cursor.fetchall()
        if not tokens:
            raise RuntimeError("No active registered honeytokens found")
        from monitoring.behavior_store import DB_PATH
        import sqlite3
        if not DB_PATH.exists():
            raise RuntimeError("No behavior history. Run department queries through query_gateway first.")
        with sqlite3.connect(DB_PATH) as history_db:
            risk_rows = history_db.execute("""SELECT department_no, AVG(risk_score) FROM behavior_events
                WHERE department_no IS NOT NULL GROUP BY department_no""").fetchall()
        risk_by_department = {dept: float(score) for dept, score in risk_rows if dept in departments}
        if not risk_by_department:
            raise RuntimeError("No department risk scores found. Run Demo B department queries first.")
        budget = len(tokens)
        target_counts = allocate_token_budget(departments, risk_by_department, budget)
        token_counts = {dept: 0 for dept in departments}
        for token in tokens:
            if token["dept_no"] in token_counts:
                token_counts[token["dept_no"]] += 1
        planned = []
        surplus = {dept: token_counts[dept] - target_counts[dept] for dept in departments}
        deficits = {dept: target_counts[dept] - token_counts[dept] for dept in departments}
        movable = {dept: [token for token in tokens if token["dept_no"] == dept]
                   for dept in departments}
        for destination in departments:
            while deficits[destination] > 0:
                origins = [dept for dept in departments if surplus[dept] > 0]
                if not origins:
                    raise RuntimeError("Placement allocation did not balance to the token budget")
                origin = max(origins, key=lambda dept: (surplus[dept], dept))
                token = movable[origin].pop()
                planned.append((int(token["emp_no"]), origin, destination))
                surplus[origin] -= 1
                deficits[destination] -= 1
        print(f"Active tokens: {len(tokens)} | proposed moves: {len(planned)}")
        print("Average risk by department: " + ", ".join(
            f"{dept}={risk_by_department.get(dept, 0.0):.3f}" for dept in departments))
        for move in planned:
            print(f"emp_no={move[0]}: {move[1]} -> {move[2]}")
        if not args.apply:
            print("Dry run only; pass --apply to write changes.")
            return
        now = datetime.now(timezone.utc).isoformat()
        update_started = time.perf_counter()
        history_ids = []
        for emp_no, old, target in planned:
            cursor.execute("UPDATE dept_emp SET dept_no=%s WHERE emp_no=%s AND dept_no=%s AND to_date='9999-01-01'",
                           (target, emp_no, old))
            if cursor.rowcount != 1:
                raise RuntimeError(f"Expected one active department row for token {emp_no}")
            cursor.execute(f"UPDATE {SECURITY_DB}.honeytoken_registry SET placement_strategy='ADAPTIVE', placement_version=%s WHERE emp_no=%s AND is_active=TRUE",
                           ("adaptive_" + now[:10], emp_no))
            if cursor.rowcount != 1:
                raise RuntimeError(f"Expected one active registry row for token {emp_no}")
            cursor.execute(f"""INSERT INTO {SECURITY_DB}.placement_update_history
                (run_id,token_emp_no,from_department,to_department,placement_strategy,update_cost_ms)
                VALUES (NULL,%s,%s,%s,'ADAPTIVE_RISK',NULL)""", (emp_no, old, target))
            history_ids.append(cursor.lastrowid)
        db.commit()
        update_cost_ms = (time.perf_counter() - update_started) * 1000
        for history_id in history_ids:
            cursor.execute(f"UPDATE {SECURITY_DB}.placement_update_history SET update_cost_ms=%s WHERE placement_id=%s",
                           (update_cost_ms, history_id))
        db.commit()
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        exists = HISTORY.exists()
        with HISTORY.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not exists:
                writer.writerow(["timestamp_utc", "emp_no", "from_department", "to_department", "update_cost_ms"])
            writer.writerows([[now, *move, round(update_cost_ms, 4)] for move in planned])
        print(f"Applied {len(planned)} moves in {update_cost_ms:.3f} ms; history: {HISTORY}")
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    main()
