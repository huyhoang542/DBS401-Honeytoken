"""Run controlled, read-only attack-like query sessions against local employee DB.

This is a lab simulator, not an exploit. It executes bounded SELECT statements,
labels sessions by the scenario script, checks each demo's token registry, and
cross-validates Demo B on captured database telemetry with whole sessions held out.
"""
import csv
import argparse
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import joblib
import mysql.connector
import numpy as np
from dotenv import dotenv_values
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
OUT = ROOT / "results"
FEATURES = ["result_count", "hour", "target_table_count", "query_frequency",
            "query_duration_ms", "is_department_query"]
TOKEN_DBS = {"Demo A": "honeytoken_security", "Demo B": "honeytoken_security_b"}
READERS = {"Demo A": "READER", "Demo B": "READER"}
MONITORS = {"Demo A": "MONITOR", "Demo B": "MONITOR"}


def config_for(demo):
    path = PROJECT / demo.replace(" ", "") / ".env"
    values = dotenv_values(path)
    if not path.exists():
        raise SystemExit(f"Missing {path}; prepare both demos' .env files first.")
    host = values.get("DB_HOST", "localhost")
    if host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Safety stop: this simulator only connects to localhost/127.0.0.1.")
    return values


def connect(values, user_key, dataset=True):
    user = values.get(user_key + "_USER")
    password = values.get(user_key + "_PASSWORD")
    if not user or not password or password.startswith("YOUR_"):
        raise SystemExit(f"Set {user_key}_USER and {user_key}_PASSWORD in the demo .env")
    options = {"host": values.get("DB_HOST", "localhost"),
               "port": int(values.get("DB_PORT", "3306")), "user": user,
               "password": password}
    if dataset:
        db_name = values.get("DB_NAME", "employee")
        if db_name != "employee":
            raise SystemExit("A/B live comparison requires DB_NAME=employee in both demos.")
        options["database"] = db_name
    return mysql.connector.connect(**options)


def load_fixture(values):
    """Read real IDs/departments from the shared public sample database."""
    db = connect(values, "READER")
    try:
        cur = db.cursor()
        cur.execute("SELECT emp_no FROM employee WHERE emp_no < 900000 ORDER BY emp_no LIMIT 120")
        ids = [int(row[0]) for row in cur.fetchall()]
        cur.execute("SELECT dept_no FROM department ORDER BY dept_no")
        departments = [row[0] for row in cur.fetchall()]
        if len(ids) < 100 or not departments:
            raise SystemExit("employee database is not seeded as expected (need >=100 IDs and departments).")
        cur.close()
        return ids, departments
    finally:
        db.close()


def scenarios(employee_ids, departments, seed, token_ids):
    rng = random.Random(seed)
    ids = employee_ids[:]
    rng.shuffle(ids)
    cases = []
    def add(name, label, ops):
        cases.append((name, label, ops))
    # Normal controls
    add("routine_point_lookup", 0, [("point", (value,)) for value in ids[:12]])
    # Use several realistic report sizes so the model sees benign bulk reads
    # during session-held-out training/evaluation, rather than one fixed shape.
    add("legitimate_bulk_report", 0, [
        ("batch", (tuple(ids[12:22]),)),
        ("batch", (tuple(ids[22:47]),)),
        ("batch", (tuple(ids[12:62]),)),
    ])
    add("maintenance_read", 0, [("point", (value,)) for value in ids[62:74]])
    # Controlled attack-like sessions. The department/range scans are bounded.
    add("rapid_id_enumeration", 1, [("range", (lo, lo + 9999))
        for lo in range(10001, 920051, 10000)])
    add("department_sweep", 1, [("department", (dept,)) for dept in departments])
    add("broad_employee_collection", 1, [("batch", (tuple(ids[74:120]),)) for _ in range(8)])
    # Low-and-slow is a paced series of real point reads; wait is capped at 100 ms.
    add("low_and_slow_targeting", 1, [("slow_point", (value,)) for value in ids[20:30]])
    # Evaluator knows the canary IDs; the SELECTs still execute as the ordinary
    # reader account. Treat this as a controlled canary-hit validation scenario.
    add("token_probe_validation", 1, [("point", (value,)) for value in token_ids])
    return cases


def execute_operation(cursor, operation):
    kind, args = operation
    if kind in {"point", "slow_point"}:
        cursor.execute("SELECT emp_no,first_name,last_name,hire_date FROM employee WHERE emp_no=%s", args)
    elif kind == "batch":
        values = args[0]
        marks = ",".join(["%s"] * len(values))
        cursor.execute("SELECT emp_no,first_name,last_name,hire_date FROM employee WHERE emp_no IN (" + marks + ") LIMIT 100", values)
    elif kind == "range":
        cursor.execute("SELECT emp_no,first_name,last_name,hire_date FROM employee WHERE emp_no BETWEEN %s AND %s ORDER BY emp_no LIMIT 1000", args)
    elif kind == "department":
        cursor.execute("SELECT e.emp_no,e.first_name,e.last_name,e.hire_date FROM employee e JOIN dept_emp d ON d.emp_no=e.emp_no WHERE d.dept_no=%s AND d.to_date='9999-01-01' ORDER BY e.emp_no LIMIT 250", args)
    else:
        raise ValueError(kind)
    return cursor.fetchall()


def get_token_hits(monitor_cursor, security_db, emp_nos):
    if not emp_nos:
        return set()
    marks = ",".join(["%s"] * len(emp_nos))
    monitor_cursor.execute(f"SELECT emp_no FROM {security_db}.honeytoken_registry WHERE is_active=TRUE AND emp_no IN ({marks})", tuple(emp_nos))
    return {int(row[0]) for row in monitor_cursor.fetchall()}


def collect_demo(demo, values, employee_ids, departments, repeat):
    data = []
    reader = connect(values, "READER")
    monitor = connect(values, "MONITOR", dataset=False)
    try:
        reader.start_transaction(readonly=True)
        cursor = reader.cursor()
        mc = monitor.cursor()
        frequency = Counter()
        mc.execute(f"SELECT emp_no FROM {TOKEN_DBS[demo]}.honeytoken_registry WHERE is_active=TRUE ORDER BY emp_no")
        token_ids = [int(row[0]) for row in mc.fetchall()]
        if not token_ids:
            raise SystemExit(f"No active honeytokens found for {demo}; seed its registry first.")
        for family, label, ops in scenarios(employee_ids, departments, 7100 + repeat, token_ids):
            session_id = f"r{repeat}-{family}"
            for index, operation in enumerate(ops, 1):
                if operation[0] == "slow_point":
                    time.sleep(0.1)
                start = time.perf_counter()
                rows = execute_operation(cursor, operation)
                duration_ms = (time.perf_counter() - start) * 1000
                emp_nos = [int(row[0]) for row in rows]
                hits = get_token_hits(mc, TOKEN_DBS[demo], emp_nos)
                frequency[session_id] += 1
                data.append({"demo": demo, "repeat": repeat, "session_id": session_id,
                    "scenario_type": family, "actual_label": label,
                    "scenario_id": f"{session_id}-q{index:03d}",
                    "result_count": len(rows), "hour": time.localtime().tm_hour,
                    "target_table_count": 2 if operation[0] == "department" else 1,
                    "query_frequency": frequency[session_id],
                    "query_duration_ms": duration_ms,
                    "is_department_query": int(operation[0] == "department"),
                    "static_honeytoken_hit": int(bool(hits)), "hit_count": len(hits),
                    "query_type": operation[0]})
        cursor.close()
        mc.close()
        reader.rollback()
    finally:
        reader.close()
        monitor.close()
    return data


def metric_row(actual, predicted):
    tn, fp, fn, tp = confusion_matrix(actual, predicted, labels=[0, 1]).ravel()
    return {"queries": int(len(actual)), "TP": int(tp), "TN": int(tn), "FP": int(fp), "FN": int(fn),
        "accuracy": float(accuracy_score(actual, predicted)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-only", action="store_true",
                        help="Collect read-only MySQL telemetry and labels, but do not train. Run train_live_model.py next.")
    parser.add_argument("--train-inline", action="store_true",
                        help="Also run the older session-level evaluation in this script. The documented workflow uses train_live_model.py.")
    args = parser.parse_args()
    all_rows = []
    employee_ids, departments = None, None
    configs = {demo: config_for(demo) for demo in ("Demo A", "Demo B")}
    employee_ids, departments = load_fixture(configs["Demo B"])
    for demo in ("Demo A", "Demo B"):
        for repeat in range(1, 6):
            print(f"Executing {demo}, repeat {repeat}/5 ...")
            all_rows.extend(collect_demo(demo, configs[demo], employee_ids, departments, repeat))

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "live_attack_query_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)

    if args.capture_only or not args.train_inline:
        print(f"Captured {len(all_rows)} labeled lab queries to {csv_path}")
        print("No model was trained. Next run: python evaluation/train_live_model.py")
        return

    summaries = {}
    # Demo A: static alert is an actual hit against its own registered planted tokens.
    a = [row for row in all_rows if row["demo"] == "Demo A"]
    summaries["Demo A static honeytoken"] = metric_row(
        np.array([r["actual_label"] for r in a]), np.array([r["static_honeytoken_hit"] for r in a]))
    # Demo B: out-of-fold evaluation, holding out entire query sessions to prevent
    # rows from one simulated actor session leaking between train and test.
    b = [row for row in all_rows if row["demo"] == "Demo B"]
    x = np.array([[float(row[name]) for name in FEATURES] for row in b])
    y = np.array([row["actual_label"] for row in b], dtype=int)
    groups = np.array([row["session_id"] for row in b])
    folds = min(5, len(set(groups)))
    if folds < 2 or len(set(y)) < 2:
        raise SystemExit("Need multiple labeled sessions from both classes to evaluate ML.")
    model = RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced",
                                   random_state=401, n_jobs=-1)
    scores = cross_val_predict(model, x, y, groups=groups,
        cv=GroupKFold(n_splits=folds), method="predict_proba", n_jobs=1)[:, 1]
    pred = (scores >= 0.65).astype(int)
    summaries["Demo B live-telemetry Random Forest"] = metric_row(y, pred)
    summaries["Demo B live-telemetry RF OR token"] = metric_row(
        y, np.logical_or(pred, np.array([r["static_honeytoken_hit"] for r in b])).astype(int))
    for row, score, prediction in zip(b, scores, pred):
        row["risk_score"] = float(score)
        row["ml_predicted_label"] = int(prediction)
    # Train the interactive prototype on all collected lab traces, clearly marked as
    # simulated-lab training data (not real production incident labels).
    model.fit(x, y)
    model_path = ROOT / "models" / "random_forest_live_sim.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    metadata = {"model": "RandomForestClassifier", "training_source": "real MySQL telemetry from this controlled local simulator",
        "labels": "scripted scenario ground truth; not production incident labels",
        "rows": int(len(y)), "sessions": int(len(set(groups))), "features": FEATURES,
        "threshold": 0.65, "evaluation": "GroupKFold; entire query sessions held out",
        "warning": "Lab demonstration only; do not claim field effectiveness."}
    (ROOT / "models" / "live_sim_model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Also score one outcome per full session so long scenarios do not dominate
    # the headline comparison just because they issue more SQL statements.
    session_rows = []
    keys = sorted({(row["demo"], row["session_id"]) for row in all_rows})
    for demo, session_id in keys:
        entries = [row for row in all_rows if row["demo"] == demo and row["session_id"] == session_id]
        label = int(entries[0]["actual_label"])
        static_alert = int(any(row["static_honeytoken_hit"] for row in entries))
        if demo == "Demo B":
            ml_alert = int(any(row["ml_predicted_label"] for row in entries))
            combined_alert = int(bool(ml_alert or static_alert))
        else:
            ml_alert = combined_alert = ""
        session_rows.append({"demo": demo, "session_id": session_id,
            "scenario_type": entries[0]["scenario_type"], "actual_label": label,
            "A_static_alert": static_alert if demo == "Demo A" else "",
            "B_ml_alert": ml_alert, "B_ml_or_token_alert": combined_alert,
            "query_count": len(entries)})
    session_summary = {}
    for demo, method, column in (
        ("Demo A", "Demo A static honeytoken", "A_static_alert"),
        ("Demo B", "Demo B live-telemetry Random Forest", "B_ml_alert"),
        ("Demo B", "Demo B live-telemetry RF OR token", "B_ml_or_token_alert"),
    ):
        entries = [row for row in session_rows if row["demo"] == demo]
        session_summary[method] = metric_row(
            np.array([row["actual_label"] for row in entries]),
            np.array([int(row[column]) for row in entries]))
    scenario_rows = []
    for demo, family in sorted({(row["demo"], row["scenario_type"]) for row in session_rows}):
        entries = [row for row in session_rows if row["demo"] == demo and row["scenario_type"] == family]
        for column, method in (("A_static_alert", "static"), ("B_ml_alert", "ml"),
                               ("B_ml_or_token_alert", "ml_or_token")):
            values = [int(row[column]) for row in entries if row[column] != ""]
            if values:
                scenario_rows.append({"demo": demo, "scenario_type": family,
                    "actual_label": entries[0]["actual_label"], "detector": method,
                    "sessions": len(values), "session_alert_rate": float(np.mean(values))})
    scenario_path = OUT / "live_attack_scenario_metrics.csv"
    with scenario_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(scenario_rows[0]))
        writer.writeheader()
        writer.writerows(scenario_rows)
    session_path = OUT / "live_attack_session_results.csv"
    with session_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(session_rows[0]))
        writer.writeheader()
        writer.writerows(session_rows)

    # Add fields consistently to CSV, including blank ML fields for A.
    for row in all_rows:
        row.setdefault("risk_score", "")
        row.setdefault("ml_predicted_label", "")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    result = {"source": "live read-only queries to localhost employee database",
        "shared_dataset": "employee", "repeats": 5, "scenario_families":
        ["routine_point_lookup", "legitimate_bulk_report", "maintenance_read",
         "rapid_id_enumeration", "department_sweep", "broad_employee_collection", "low_and_slow_targeting"],
        "label_policy": "scenario script sets attack=1 and normal control=0",
        "ml_evaluation": "Demo B telemetry; GroupKFold by complete session; not production traffic",
        "query_level_metrics": summaries, "session_level_metrics": session_summary,
        "query_results_csv": str(csv_path), "session_results_csv": str(session_path),
        "scenario_metrics_csv": str(scenario_path), "model_artifact": str(model_path)}
    (OUT / "live_attack_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    print(f"Query-level output: {csv_path}")
    print(f"Run summary: {OUT / 'live_attack_metrics.json'}")


if __name__ == "__main__":
    main()
