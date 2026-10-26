"""Compare Static and ML detectors on the same held-out scenario families."""
import json
import re
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
EMPLOYEE_SOURCE = ROOT / "data" / "employee_ab" / "load_employee.sql"
FEATURES = ["result_count", "hour", "target_table_count", "query_frequency",
            "query_duration_ms", "is_department_query"]
PROFILES = {
    "routine_point_lookup": (0, .01),
    "legitimate_bulk_report": (0, .04),
    "offhours_maintenance": (0, .01),
    "rapid_id_enumeration": (1, .20),
    "department_sweep": (1, .35),
    "afterhours_bulk_access": (1, .18),
    "low_and_slow_targeting": (1, .01),
}
THRESHOLD = .65


def build_scenarios(seed, n_each=1000):
    """Generate balanced normal/attack sessions across seven scenario families."""
    rng = np.random.default_rng(seed)
    names = {}
    for label in (0, 1):
        families = [name for name, (y, _) in PROFILES.items() if y == label]
        values = np.resize(np.array(families, dtype=object), n_each)
        rng.shuffle(values)
        names[label] = values
    scenario_type = np.concatenate((names[0], names[1]))
    y = np.r_[np.zeros(n_each, dtype=int), np.ones(n_each, dtype=int)]
    x = np.zeros((len(y), len(FEATURES)), dtype=float)
    business = np.arange(7, 21)
    offhours = np.array([0, 1, 2, 3, 22, 23])

    def put(family, result, hour, tables, frequency, duration, dept):
        mask = scenario_type == family
        n = int(mask.sum())
        x[mask] = np.column_stack((result(n), hour(n), tables(n), frequency(n), duration(n), dept(n)))

    put("routine_point_lookup", lambda n: rng.poisson(6, n)+1,
        lambda n: rng.choice(business, n), lambda n: rng.choice([1, 2], n, p=[.7, .3]),
        lambda n: rng.poisson(5, n)+1, lambda n: rng.lognormal(3.3, .55, n),
        lambda n: rng.binomial(1, .2, n))
    put("legitimate_bulk_report", lambda n: rng.integers(20, 100, n),
        lambda n: rng.integers(8, 18, n), lambda n: rng.choice([2, 3], n),
        lambda n: rng.integers(1, 10, n), lambda n: rng.lognormal(4.0, .5, n), lambda n: np.ones(n))
    put("offhours_maintenance", lambda n: rng.integers(1, 25, n),
        lambda n: rng.choice(offhours, n), lambda n: rng.choice([1, 2], n),
        lambda n: rng.integers(1, 12, n), lambda n: rng.lognormal(3.6, .45, n),
        lambda n: rng.binomial(1, .25, n))
    put("rapid_id_enumeration", lambda n: rng.integers(20, 180, n),
        lambda n: rng.choice(np.r_[business, offhours], n), lambda n: rng.choice([1, 2, 3], n),
        lambda n: rng.integers(20, 180, n), lambda n: rng.lognormal(4.2, .65, n), lambda n: np.zeros(n))
    put("department_sweep", lambda n: rng.integers(50, 251, n),
        lambda n: rng.choice(np.r_[business, offhours], n), lambda n: rng.choice([2, 3, 4], n),
        lambda n: rng.integers(15, 160, n), lambda n: rng.lognormal(4.5, .65, n), lambda n: np.ones(n))
    put("afterhours_bulk_access", lambda n: rng.integers(20, 201, n),
        lambda n: rng.choice(offhours, n), lambda n: rng.choice([2, 3, 4], n),
        lambda n: rng.integers(10, 120, n), lambda n: rng.lognormal(4.5, .7, n),
        lambda n: rng.binomial(1, .55, n))
    put("low_and_slow_targeting", lambda n: rng.integers(1, 9, n),
        lambda n: rng.choice(np.r_[business, offhours], n), lambda n: rng.choice([1, 2], n, p=[.8, .2]),
        lambda n: rng.integers(1, 10, n), lambda n: rng.lognormal(3.4, .55, n),
        lambda n: rng.binomial(1, .2, n))
    hit_rates = np.array([PROFILES[s][1] for s in scenario_type])
    token_hit = rng.binomial(1, hit_rates).astype(int)
    return x, y, token_hit, scenario_type


def metric_row(y, pred, latency):
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"total_queries": int(len(y)), "TP": int(tp), "TN": int(tn), "FP": int(fp), "FN": int(fn),
        "accuracy": float(accuracy_score(y, pred)), "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)), "f1_score": float(f1_score(y, pred, zero_division=0)),
        "false_positive_rate": float(fp/(fp+tn)) if fp+tn else 0.0,
        "mean_prediction_latency_ms": float(np.mean(latency))}


def main():
    if not EMPLOYEE_SOURCE.exists():
        raise SystemExit("Missing dataset ID file: data/employee_ab/load_employee.sql")
    employee_ids = np.array([int(v) for v in re.findall(r"\((\d+),'", EMPLOYEE_SOURCE.read_text(encoding="utf-8"))])
    if len(employee_ids) != 10000:
        raise SystemExit(f"Expected 10,000 dataset_large IDs, found {len(employee_ids)}")
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"protocol": {"repeats": 5, "test_size": .30, "threshold": THRESHOLD,
        "scenario_types": {name: {"label": label, "synthetic_static_token_hit_rate": hit}
                           for name, (label, hit) in PROFILES.items()},
        "note": "All methods use the same held-out generated rows. Labels and token-hit rates are synthetic assumptions, not measured attack traffic."}, "runs": []}
    detail_rows = []

    for repeat in range(5):
        x, y, token_hit, types = build_scenarios(401 + repeat)
        id_rng = np.random.default_rng(8100 + repeat)
        subjects = id_rng.choice(employee_ids, size=len(y), replace=True)
        train, test = train_test_split(np.arange(len(y)), test_size=.30,
            random_state=1500 + repeat, stratify=y)
        models = {
            "B_random_forest": RandomForestClassifier(n_estimators=200, max_depth=8,
                class_weight="balanced", random_state=401+repeat, n_jobs=-1),
        }
        preds = {"A_static_honeytoken": token_hit[test].copy()}
        scores = {"A_static_honeytoken": np.full(len(test), np.nan)}
        latency = {"A_static_honeytoken": np.zeros(len(test))}
        for name, model in models.items():
            model.fit(x[train], y[train])
            t0 = time.perf_counter()
            score = model.predict_proba(x[test])[:, 1]
            per_row = (time.perf_counter() - t0) * 1000 / len(test)
            risk_pred = (score >= THRESHOLD).astype(int)
            preds[name] = risk_pred
            preds[name + "_plus_honeytoken"] = np.logical_or(risk_pred, token_hit[test]).astype(int)
            scores[name] = score
            scores[name + "_plus_honeytoken"] = score
            latency[name] = np.full(len(test), per_row)
            latency[name + "_plus_honeytoken"] = np.full(len(test), per_row)
        run = {"repeat": repeat+1, "train_rows": len(train), "test_rows": len(test)}
        for method, pred in preds.items():
            run[method] = metric_row(y[test], pred, latency[method])
            for j, idx in enumerate(test):
                detail_rows.append({"repeat": repeat+1, "scenario_id": f"r{repeat+1}-s{idx:04d}",
                    "scenario_type": str(types[idx]), "subject_emp_no": int(subjects[idx]),
                    "actual_label": int(y[idx]), "static_honeytoken_hit": int(token_hit[idx]),
                    "result_count": int(x[idx, 0]), "hour": int(x[idx, 1]),
                    "target_table_count": int(x[idx, 2]), "query_frequency": int(x[idx, 3]),
                    "query_duration_ms": float(x[idx, 4]), "is_department_query": int(x[idx, 5]),
                    "model": method, "predicted_label": int(pred[j]),
                    "risk_score": None if np.isnan(scores[method][j]) else float(scores[method][j]),
                    "latency_ms": float(latency[method][j])})
        summary["runs"].append(run)

    detail = pd.DataFrame(detail_rows)
    detail.to_csv(OUT / "ab_query_results.csv", index=False)
    method_names = [k for k in summary["runs"][0] if k.startswith(("A_", "B_"))]
    aggregate = []
    for method in method_names:
        repeated = [run[method] for run in summary["runs"]]
        aggregate.append({"model": method, **{m: float(np.mean([r[m] for r in repeated]))
            for m in ("accuracy", "precision", "recall", "f1_score", "false_positive_rate", "mean_prediction_latency_ms")}})
    summary["mean_metrics"] = aggregate
    pd.DataFrame(aggregate).to_csv(OUT / "ab_metrics.csv", index=False)

    by_scenario = []
    for (family, method), group in detail.groupby(["scenario_type", "model"], sort=True):
        actual = group.actual_label.to_numpy()
        predicted = group.predicted_label.to_numpy()
        by_scenario.append({"scenario_type": family, "model": method, "scenario_count": len(group),
            "actual_label": int(actual[0]), "alert_rate": float(predicted.mean()),
            "correct_rate": float(np.mean(actual == predicted))})
    pd.DataFrame(by_scenario).to_csv(OUT / "ab_scenario_metrics.csv", index=False)

    final_x, final_y, _, _ = build_scenarios(9001, n_each=2000)
    production_model = RandomForestClassifier(n_estimators=200, max_depth=8,
        class_weight="balanced", random_state=401, n_jobs=-1).fit(final_x, final_y)
    model_dir = ROOT / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(production_model, model_dir / "random_forest_synthetic.joblib")
    (model_dir / "model_metadata.json").write_text(json.dumps({
        "model": "RandomForestClassifier", "training_data": "seeded synthetic multi-scenario behavior",
        "training_seed": 9001, "rows": len(final_y), "positive_threshold": THRESHOLD,
        "scenario_types": list(PROFILES), "feature_order": FEATURES}, indent=2), encoding="utf-8")
    (OUT / "ab_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(pd.DataFrame(aggregate).to_string(index=False))
    print(f"By-scenario table: {OUT / 'ab_scenario_metrics.csv'}")
    print(f"Detailed predictions: {OUT / 'ab_query_results.csv'}")


if __name__ == "__main__":
    main()
