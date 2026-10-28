"""Persist the generated CSV benchmark in the shared MySQL A/B schema."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SECURITY_DB = os.getenv("SECURITY_DB_NAME", "honeytoken_security_b")
if SECURITY_DB != "honeytoken_security_b" or os.getenv("DB_NAME", "employee_ab") != "employee_ab":
    raise ValueError("Demo B is isolated: keep DB_NAME=employee_ab and SECURITY_DB_NAME=honeytoken_security_b")
RESULTS = ROOT / "results" / "ab_query_results.csv"
DATASET = "bytebase/mysql/dataset_large"
SCENARIOS = "synthetic_behavior_seeded_v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert the rows into MySQL")
    args = parser.parse_args()
    if not RESULTS.exists():
        raise SystemExit("Run evaluation/run_benchmark.py first")
    df = pd.read_csv(RESULTS)
    groups = list(df.groupby(["repeat", "model"], sort=True))
    print(f"Prepared {len(groups)} experiment runs and {len(df)} query-result rows")
    if not args.apply:
        print(f"Dry run only; pass --apply to persist into {SECURITY_DB}.")
        return
    db = mysql.connector.connect(host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")), user=os.environ["MONITOR_USER"],
        password=os.environ["MONITOR_PASSWORD"])
    cursor = db.cursor()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        for (repeat, model), part in groups:
            version = "A_STATIC" if model == "A_static_honeytoken" else "B_ADAPTIVE"
            config = {"model": model, "threshold": .65 if model.startswith("B_") else None,
                      "scenario_source": "synthetic seeded behavior scenarios"}
            cursor.execute(f"""INSERT INTO {SECURITY_DB}.experiment_runs
                (demo_version,run_name,dataset_version,honeytoken_budget,scenario_set,
                 random_seed,model_name,model_config,completed_at,notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6),%s)""",
                (version, f"{stamp}_repeat{int(repeat)}_{model}", DATASET, 50, SCENARIOS,
                 401 + int(repeat) - 1, model, json.dumps(config),
                 "Synthetic benchmark; labels represent suspicious behavior, not token presence."))
            run_id = cursor.lastrowid
            insert_sql = f"""INSERT INTO {SECURITY_DB}.experiment_query_results
                (run_id,scenario_id,query_type,target_table,requested_rows,returned_rows,
                 actual_label,predicted_label,risk_score,latency_ms,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            records = []
            for row in part.itertuples(index=False):
                metadata = {"subject_emp_no": int(row.subject_emp_no),
                    "static_honeytoken_hit": int(row.static_honeytoken_hit),
                    "result_count": int(row.result_count), "hour": int(row.hour),
                    "target_table_count": int(row.target_table_count),
                    "query_frequency": int(row.query_frequency),
                    "query_duration_ms": float(row.query_duration_ms),
                    "is_department_query": int(row.is_department_query)}
                risk_score = None if pd.isna(row.risk_score) else float(row.risk_score)
                records.append((run_id, row.scenario_id, "SIMULATED_BEHAVIOR", "employee",
                    int(row.result_count), int(row.result_count), int(row.actual_label),
                    int(row.predicted_label), risk_score, float(row.latency_ms), json.dumps(metadata)))
            cursor.executemany(insert_sql, records)
        db.commit()
        print(f"Persisted {len(groups)} runs and {len(df)} results.")
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    main()
