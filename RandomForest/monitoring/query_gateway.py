"""Demo B query gateway: multi-row lookups, behavior features and ML risk."""
import argparse
import os
import sys
import time
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.risk_model import score_behavior  # noqa: E402
from monitoring.behavior_store import recent_frequency, save_event  # noqa: E402

load_dotenv(ROOT / ".env")
SECURITY_DB = os.getenv("SECURITY_DB_NAME", "honeytoken_security_b")
DATASET_DB = os.getenv("DB_NAME", "employee")
if SECURITY_DB != "honeytoken_security_b" or DATASET_DB not in {"employee", "employee_ab"}:
    raise ValueError("Demo B requires SECURITY_DB_NAME=honeytoken_security_b and DB_NAME=employee or employee_ab")


def connect(user, password, use_dataset=True):
    options = dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=user, password=password,
    )
    if use_dataset:
        options["database"] = DATASET_DB
    return mysql.connector.connect(**options)


def query_employees(emp_nos=None, dept_no=None, limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    started = time.perf_counter()
    reader = monitor = None
    try:
        reader = connect(os.environ["READER_USER"], os.environ["READER_PASSWORD"])
        monitor = connect(os.environ["MONITOR_USER"], os.environ["MONITOR_PASSWORD"], use_dataset=False)
        rc, mc = reader.cursor(dictionary=True), monitor.cursor(dictionary=True)
        if emp_nos:
            placeholders = ",".join(["%s"] * len(emp_nos))
            sql = ("SELECT e.emp_no,e.first_name,e.last_name,e.hire_date "
                   "FROM employee e WHERE e.emp_no IN (" + placeholders + ") LIMIT %s")
            params = tuple(emp_nos) + (limit,)
            target, table_count = "employee_id", 1
        elif dept_no:
            sql = ("SELECT e.emp_no,e.first_name,e.last_name,e.hire_date "
                   "FROM employee e JOIN dept_emp d ON d.emp_no=e.emp_no "
                   "WHERE d.dept_no=%s AND d.to_date='9999-01-01' LIMIT %s")
            params = (dept_no, limit)
            target, table_count = "department", 2
        else:
            raise ValueError("Supply employee IDs or a department number")
        rc.execute(sql, params)
        rows = rc.fetchall()
        ids = [int(row["emp_no"]) for row in rows]
        tokens = {}
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            mc.execute(f"SELECT emp_no,token_id FROM {SECURITY_DB}.honeytoken_registry "
                       "WHERE is_active=TRUE AND emp_no IN (" + placeholders + ")", tuple(ids))
            tokens = {int(row["emp_no"]): row["token_id"] for row in mc.fetchall()}
        elapsed_ms = (time.perf_counter() - started) * 1000
        features = {
            "result_count": len(rows), "hour": time.localtime().tm_hour,
            "target_table_count": table_count,
            "query_frequency": recent_frequency(os.environ["READER_USER"]),
            "query_duration_ms": elapsed_ms, "is_department_query": int(dept_no is not None),
        }
        risk = score_behavior(features)
        hit_tokens = [tokens[i] for i in ids if i in tokens]
        text = "department query" if dept_no else "employee ID batch query"
        mc.execute(f"""INSERT INTO {SECURITY_DB}.access_events
            (username,query_type,target_table,query_text,returned_rows,honeytoken_hit)
            VALUES (%s,'SELECT',%s,%s,%s,%s)""",
            (os.environ["READER_USER"], "employee", text, len(rows), bool(hit_tokens)))
        event_id = mc.lastrowid
        for token_id in hit_tokens:
            mc.execute(f"""INSERT INTO {SECURITY_DB}.security_alerts
                (event_id,token_id,severity,message) VALUES (%s,%s,%s,%s)""",
                (event_id, token_id, "HIGH", "Honeytoken record accessed through Demo B gateway"))
        monitor.commit()
        save_event(os.environ["READER_USER"], text, features, risk["score"], risk["label"],
                   bool(hit_tokens), department_no=dept_no)
        print(f"Returned rows: {len(rows)} | risk: {risk['score']:.3f} ({risk['label']})")
        if risk["label"] == "HIGH":
            print("ML RISK: HIGH")
        print("ALERT: Honeytoken accessed!" if hit_tokens else "No honeytoken detected.")
        for row in rows:
            print(row)
        return {"features": features, "risk": risk, "rows": rows, "hits": hit_tokens}
    except Exception:
        if monitor is not None:
            monitor.rollback()
        raise
    finally:
        if reader is not None:
            reader.close()
        if monitor is not None:
            monitor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="Comma-separated employee numbers")
    parser.add_argument("--department", help="Department number, e.g. d001")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    ids = [int(value) for value in args.ids.split(",")] if args.ids else None
    query_employees(ids, args.department, args.limit)


if __name__ == "__main__":
    main()
