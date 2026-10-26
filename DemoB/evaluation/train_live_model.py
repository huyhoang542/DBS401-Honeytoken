"""Train and evaluate Demo B from captured local MySQL query telemetry.

Labels are scenario-script ground truth. Feature values are collected from
actual bounded SELECT statements executed against the local employee DB.
"""

import csv
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GroupKFold, cross_val_predict

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MODEL_PATH = ROOT / "models" / "random_forest_live_sim.joblib"
METADATA_PATH = ROOT / "models" / "live_sim_model_metadata.json"
INPUT_PATH = RESULTS / "live_attack_query_results.csv"
FEATURES = [
    "result_count",
    "hour",
    "target_table_count",
    "query_frequency",
    "query_duration_ms",
    "is_department_query",
]
MAX_CALIBRATION_FPR = 0.10


def metrics(actual, predicted, count_name="queries"):
    tn, fp, fn, tp = confusion_matrix(actual, predicted, labels=[0, 1]).ravel()
    return {
        count_name: int(len(actual)),
        "TP": int(tp),
        "TN": int(tn),
        "FP": int(fp),
        "FN": int(fn),
        "accuracy": float(accuracy_score(actual, predicted)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
    }


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No rows to write to {path}")
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def choose_threshold(y, scores, session_groups):
    """Choose the highest-recall threshold whose OOF session FPR is <= cap."""
    grouped = {}
    for label, score, session in zip(y, scores, session_groups):
        item = grouped.setdefault(session, {"label": int(label), "scores": []})
        item["scores"].append(float(score))
    session_y = np.asarray([item["label"] for item in grouped.values()])
    session_scores = np.asarray([max(item["scores"]) for item in grouped.values()])
    candidates = sorted(set([0.0, 1.0, *session_scores.tolist()]))
    valid = []
    for threshold in candidates:
        predicted = (session_scores >= threshold).astype(int)
        result = metrics(session_y, predicted, count_name="sessions")
        if result["false_positive_rate"] <= MAX_CALIBRATION_FPR:
            valid.append((result["recall"], result["f1"], -threshold, threshold, result))
    if not valid:
        raise SystemExit("No threshold meets the configured false-positive-rate target.")
    _, _, _, threshold, selected_metrics = max(valid)
    return float(threshold), selected_metrics


def main():
    if not INPUT_PATH.exists():
        raise SystemExit(
            "Missing captured telemetry. Run "
            "python evaluation/run_live_attack_simulation.py --capture-only first."
        )
    with INPUT_PATH.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    b_rows = [row for row in rows if row["demo"] == "Demo B"]
    if len(b_rows) < 20:
        raise SystemExit("Too few Demo B rows. Capture a fresh attack-scenario run first.")

    x = np.asarray(
        [[float(row[name]) for name in FEATURES] for row in b_rows], dtype=float
    )
    y = np.asarray([int(row["actual_label"]) for row in b_rows], dtype=int)
    # Hold out complete sessions while keeping each scenario family represented
    # in training. This lets the detector learn that known bulk report shapes
    # can be legitimate, while still preventing query-row leakage across a run.
    groups = np.asarray([row["session_id"] for row in b_rows])
    folds = len(set(groups))
    if folds < 2 or len(set(y)) < 2:
        raise SystemExit("Training needs at least two labeled session groups and both labels.")

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        class_weight="balanced",
        random_state=401,
        n_jobs=-1,
    )
    # Nested validation: choose the threshold using only four repeats, then
    # evaluate it on the untouched fifth repeat. Rotate the held-out repeat.
    # This prevents using the same sessions both to tune and report the cutoff.
    repeats = np.asarray([int(row["repeat"]) for row in b_rows])
    eval_scores = np.zeros(len(y), dtype=float)
    eval_predictions = np.zeros(len(y), dtype=int)
    repeat_thresholds = {}
    for repeat in sorted(set(repeats)):
        train_idx = np.flatnonzero(repeats != repeat)
        test_idx = np.flatnonzero(repeats == repeat)
        train_groups = groups[train_idx]
        inner_folds = min(5, len(set(train_groups)))
        inner_scores = cross_val_predict(
            model, x[train_idx], y[train_idx], groups=train_groups,
            cv=GroupKFold(n_splits=inner_folds), method="predict_proba", n_jobs=1,
        )[:, 1]
        cutoff, _ = choose_threshold(y[train_idx], inner_scores, train_groups)
        fold_model = RandomForestClassifier(
            n_estimators=200, max_depth=8, class_weight="balanced",
            random_state=401, n_jobs=-1,
        )
        fold_model.fit(x[train_idx], y[train_idx])
        eval_scores[test_idx] = fold_model.predict_proba(x[test_idx])[:, 1]
        eval_predictions[test_idx] = (eval_scores[test_idx] >= cutoff).astype(int)
        repeat_thresholds[str(int(repeat))] = float(cutoff)

    # Independently derive the deployment cutoff from all session-held-out
    # scores; the dashboard identifies these as calibration results.
    folds = min(5, len(set(groups)))
    deployment_oof_scores = cross_val_predict(
        model, x, y, groups=groups, cv=GroupKFold(n_splits=folds),
        method="predict_proba", n_jobs=1,
    )[:, 1]
    threshold, calibration_session_metrics = choose_threshold(y, deployment_oof_scores, groups)
    predictions = eval_predictions
    for row, score, prediction in zip(b_rows, eval_scores, eval_predictions):
        row["risk_score"] = float(score)
        row["ml_predicted_label"] = int(prediction)

    # Fit the deployable demo model after the held-out evaluation is complete.
    model.fit(x, y)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    metadata = {
        "model": "RandomForestClassifier",
        "training_source": "SELECT telemetry captured from local MySQL employee database",
        "labels": "controlled scenario ground truth assigned by the simulator; not production incident labels",
        "rows": int(len(y)),
        "sessions": int(len({row['session_id'] for row in b_rows})),
        "scenario_families": int(len(set(row["scenario_type"] for row in b_rows))),
        "features": FEATURES,
        "threshold": threshold,
        "threshold_selection": "OOF session scores; maximize recall/F1 subject to session FPR <= 10%",
        "calibration_session_metrics": calibration_session_metrics,
        "evaluation": "Nested validation: threshold tuned on four repeats, evaluated on untouched fifth repeat; rotated across five repeats",
        "evaluation_thresholds_by_repeat": repeat_thresholds,
        "scenarios": sorted({row["scenario_type"] for row in b_rows}),
        "warning": "Controlled lab evidence only. Do not claim real-world attack efficacy.",
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    a_rows = [row for row in rows if row["demo"] == "Demo A"]
    query_summary = {
        "Demo A static honeytoken": metrics(
            np.asarray([int(row["actual_label"]) for row in a_rows]),
            np.asarray([int(row["static_honeytoken_hit"]) for row in a_rows]),
        ),
        "Demo B live-telemetry Random Forest": metrics(y, predictions),
        "Demo B Random Forest OR token hit": metrics(
            y,
            np.logical_or(
                predictions,
                np.asarray([int(row["static_honeytoken_hit"]) for row in b_rows]),
            ).astype(int),
        ),
    }

    session_rows = []
    keys = sorted({(row["demo"], row["session_id"]) for row in rows})
    for demo, session_id in keys:
        entries = [
            row for row in rows if row["demo"] == demo and row["session_id"] == session_id
        ]
        is_a = demo == "Demo A"
        session_rows.append(
            {
                "demo": demo,
                "session_id": session_id,
                "scenario_type": entries[0]["scenario_type"],
                "actual_label": int(entries[0]["actual_label"]),
                "A_static_alert": int(any(int(row["static_honeytoken_hit"]) for row in entries)) if is_a else "",
                "B_ml_alert": int(any(int(row.get("ml_predicted_label") or 0) for row in entries)) if not is_a else "",
                "B_ml_or_token_alert": int(any(int(row.get("ml_predicted_label") or 0) or int(row["static_honeytoken_hit"]) for row in entries)) if not is_a else "",
                "query_count": len(entries),
            }
        )

    session_summary = {}
    for demo, name, column in (
        ("Demo A", "Demo A static honeytoken", "A_static_alert"),
        ("Demo B", "Demo B live-telemetry Random Forest", "B_ml_alert"),
        ("Demo B", "Demo B Random Forest OR token hit", "B_ml_or_token_alert"),
    ):
        selected = [
            row for row in session_rows if row["demo"] == demo and row[column] != ""
        ]
        session_summary[name] = metrics(
            np.asarray([int(row["actual_label"]) for row in selected]),
            np.asarray([int(row[column]) for row in selected]),
            count_name="sessions",
        )

    scenario_rows = []
    families = sorted({(row["demo"], row["scenario_type"]) for row in session_rows})
    detectors = (
        ("A_static_alert", "static"),
        ("B_ml_alert", "ml"),
        ("B_ml_or_token_alert", "ml_or_token"),
    )
    for demo, family in families:
        sessions = [
            row for row in session_rows
            if row["demo"] == demo and row["scenario_type"] == family
        ]
        for column, detector in detectors:
            values = [int(row[column]) for row in sessions if row[column] != ""]
            if values:
                scenario_rows.append(
                    {
                        "demo": demo,
                        "scenario_type": family,
                        "actual_label": int(sessions[0]["actual_label"]),
                        "detector": detector,
                        "sessions": len(values),
                        "session_alert_rate": float(np.mean(values)),
                    }
                )

    # Keep Demo A rows and append cross-validated Demo B predictions for audit.
    for row in rows:
        if row["demo"] == "Demo A":
            row.setdefault("risk_score", "")
            row.setdefault("ml_predicted_label", "")
    write_csv(INPUT_PATH, rows)
    session_path = RESULTS / "live_attack_session_results.csv"
    scenario_path = RESULTS / "live_attack_scenario_metrics.csv"
    write_csv(session_path, session_rows)
    write_csv(scenario_path, scenario_rows)

    result = {
        "source": "actual read-only MySQL SELECT telemetry from localhost",
        "shared_dataset": "employee",
        "sessions": int(len(session_rows)),
        "scenario_families": metadata["scenarios"],
        "label_policy": "scenario script labels attack-like sessions as 1 and control sessions as 0",
        "ml_evaluation": "Demo B telemetry; nested held-out repeat evaluation; threshold tuned only on other repeats; not production incident labels",
        "threshold": threshold,
        "threshold_calibration_fpr_cap": MAX_CALIBRATION_FPR,
        "threshold_calibration_session_metrics": calibration_session_metrics,
        "query_level_metrics": query_summary,
        "session_level_metrics": session_summary,
        "query_results_csv": str(INPUT_PATH),
        "session_results_csv": str(session_path),
        "scenario_metrics_csv": str(scenario_path),
        "model_artifact": str(MODEL_PATH),
    }
    metrics_path = RESULTS / "live_attack_metrics.json"
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(session_summary, indent=2))
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved comparison: {metrics_path}")


if __name__ == "__main__":
    main()
