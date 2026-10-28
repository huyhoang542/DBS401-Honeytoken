"""Reproducible, held-out synthetic behavior benchmark for A vs B."""
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import train_test_split
import joblib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
EMPLOYEE_SOURCE = ROOT / "data" / "employee_ab" / "load_employee.sql"


def build_scenarios(seed, n_each=1000):
    rng = np.random.default_rng(seed)
    n = n_each
    normal = np.column_stack((rng.poisson(6, n) + 1,
        rng.choice(np.arange(7, 21), n), rng.choice([1, 2], n, p=[.7, .3]),
        rng.poisson(5, n) + 1, rng.lognormal(3.3, .55, n), rng.binomial(1, .3, n)))
    attack = np.column_stack((rng.integers(20, 350, n), rng.choice([0,1,2,3,22,23], n),
        rng.choice([2,3,4], n), rng.integers(20, 250, n), rng.lognormal(4.4, .8, n),
        rng.binomial(1, .65, n)))
    # Hard cases: some attacks imitate ordinary point queries, while some legitimate
    # reporting sessions are broad or off-hours. This creates meaningful overlap.
    hard_attack = n // 3
    attack[:hard_attack, 0] = rng.poisson(10, hard_attack) + 1
    attack[:hard_attack, 1] = rng.integers(7, 21, hard_attack)
    attack[:hard_attack, 2] = rng.choice([1, 2], hard_attack, p=[.65, .35])
    attack[:hard_attack, 3] = rng.poisson(8, hard_attack) + 1
    attack[:hard_attack, 4] = rng.lognormal(3.6, .65, hard_attack)
    attack[:hard_attack, 5] = rng.binomial(1, .3, hard_attack)
    hard_normal = n // 5
    normal[:hard_normal, 0] = rng.integers(20, 90, hard_normal)
    normal[:hard_normal, 1] = rng.choice([0,1,2,22,23], hard_normal)
    normal[:hard_normal, 2] = rng.choice([2, 3], hard_normal)
    normal[:hard_normal, 3] = rng.integers(10, 80, hard_normal)
    x = np.vstack([normal, attack]).astype(float)
    y = np.r_[np.zeros(n, dtype=int), np.ones(n, dtype=int)]
    # Static A only alerts when a token is returned: attacks encounter one 20% of the time.
    hit = np.r_[rng.binomial(1, .01, n), rng.binomial(1, .20, n)]
    return x, y, hit


def metrics(y, pred, latencies):
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"total_queries": int(len(y)), "TP": int(tp), "TN": int(tn),
        "FP": int(fp), "FN": int(fn), "accuracy": float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1_score": float(f1_score(y, pred, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
        "mean_prediction_latency_ms": float(np.mean(latencies))}


def main():
    if not EMPLOYEE_SOURCE.exists():
        raise SystemExit("Prepare the GitHub dataset first: python evaluation/prepare_isolated_dataset.py")
    employee_ids = np.array([int(value) for value in re.findall(
        r"\((\d+),'", EMPLOYEE_SOURCE.read_text(encoding="utf-8"))], dtype=int)
    if len(employee_ids) != 10000:
        raise SystemExit(f"Expected 10,000 dataset_large employee IDs; found {len(employee_ids)}")
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows, summaries = [], {"protocol": {"repeats": 5, "test_size": .30,
        "positive_label": "suspicious behavior scenario", "scenario_source": "synthetic, seeded",
        "note": "Not a real-world attack efficacy estimate; employee dataset supplies database entities, not attack labels."},
        "runs": []}
    for repeat in range(5):
        x, y, token_hit = build_scenarios(401 + repeat)
        scenario_rng = np.random.default_rng(8100 + repeat)
        subject_ids = scenario_rng.choice(employee_ids, size=len(y), replace=True)
        indexes = np.arange(len(y))
        train, test = train_test_split(indexes, test_size=.30, random_state=1500 + repeat,
                                       stratify=y)
        models = {
            "B_random_forest": RandomForestClassifier(n_estimators=200, max_depth=8,
                class_weight="balanced", random_state=401 + repeat, n_jobs=-1),
        }
        run_row = {"repeat": repeat + 1, "train_rows": len(train), "test_rows": len(test)}
        static_started = time.perf_counter()
        static_prediction = token_hit[test].astype(int)
        static_elapsed = (time.perf_counter() - static_started) * 1000
        predictions = {"A_static_honeytoken": static_prediction}
        latencies = {"A_static_honeytoken": np.full(len(test), static_elapsed / len(test))}
        scores = {"A_static_honeytoken": [None] * len(test)}
        for name, model in models.items():
            model.fit(x[train], y[train])
            started = time.perf_counter()
            score = model.predict_proba(x[test])[:, 1]
            pred = (score >= .65).astype(int)
            elapsed = (time.perf_counter() - started) * 1000
            predictions[name] = pred
            latencies[name] = np.full(len(test), elapsed / len(test))
            scores[name] = score
        for name, pred in predictions.items():
            m = metrics(y[test], pred, latencies[name])
            run_row[name] = m
            for j, idx in enumerate(test):
                all_rows.append({"repeat": repeat + 1, "scenario_id": f"r{repeat+1}-s{idx:04d}",
                    "subject_emp_no": int(subject_ids[idx]),
                    "actual_label": int(y[idx]), "static_honeytoken_hit": int(token_hit[idx]),
                    "result_count": int(x[idx, 0]), "hour": int(x[idx, 1]),
                    "target_table_count": int(x[idx, 2]), "query_frequency": int(x[idx, 3]),
                    "query_duration_ms": float(x[idx, 4]), "is_department_query": int(x[idx, 5]),
                    "model": name, "predicted_label": int(pred[j]),
                    "risk_score": float(scores[name][j]) if name != "A_static_honeytoken" else None,
                    "latency_ms": float(latencies[name][j])})
        summaries["runs"].append(run_row)
    pd.DataFrame(all_rows).to_csv(OUT / "ab_query_results.csv", index=False)
    summary_rows = []
    for model_name in ["A_static_honeytoken", "B_random_forest"]:
        records = [run[model_name] for run in summaries["runs"]]
        summary_rows.append({"model": model_name, **{
            metric: float(np.mean([record[metric] for record in records]))
            for metric in ["accuracy", "precision", "recall", "f1_score",
                           "false_positive_rate", "mean_prediction_latency_ms"]}})
    summaries["mean_metrics"] = summary_rows
    (OUT / "ab_metrics.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    pd.DataFrame(summary_rows).to_csv(OUT / "ab_metrics.csv", index=False)
    final_x, final_y, _ = build_scenarios(9001, n_each=2000)
    production_model = RandomForestClassifier(n_estimators=200, max_depth=8,
        class_weight="balanced", random_state=401, n_jobs=-1).fit(final_x, final_y)
    model_dir = ROOT / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(production_model, model_dir / "random_forest_synthetic.joblib")
    (model_dir / "model_metadata.json").write_text(json.dumps({
        "model": "RandomForestClassifier", "training_data": "seeded synthetic behavior scenarios",
        "training_seed": 9001, "rows": len(final_y), "positive_threshold": 0.65,
        "feature_order": ["result_count", "hour", "target_table_count", "query_frequency",
                          "query_duration_ms", "is_department_query"]}, indent=2), encoding="utf-8")
    print(pd.DataFrame(summary_rows).to_string(index=False))
    print(f"Saved detailed results under {OUT}")


if __name__ == "__main__":
    # Keep the original command working, but route it to the shared multi-scenario
    # evaluator so old run instructions do not invoke the superseded benchmark.
    from run_common_scenarios import main as run_shared_scenarios
    run_shared_scenarios()
