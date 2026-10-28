
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "static_baseline_results.csv"
OUTPUT = ROOT / "results" / "static_baseline_metrics.json"


def safe_divide(a, b):
    return a / b if b else 0.0


def main():
    df = pd.read_csv(INPUT)

    required = {
        "emp_no",
        "actual_label",
        "predicted_label",
        "latency_ms",
    }

    if not required.issubset(df.columns):
        raise ValueError("Missing required CSV columns")

    if df.empty:
        raise ValueError("Experiment results are empty")

    if df[["actual_label", "predicted_label",
           "latency_ms"]].isna().any().any():
        raise ValueError("Missing values found")

    for column in ["actual_label", "predicted_label"]:
        if not df[column].isin([0, 1]).all():
            raise ValueError(f"Invalid labels in {column}")

    if (df["latency_ms"] < 0).any():
        raise ValueError("Negative latency found")

    actual = df["actual_label"]
    predicted = df["predicted_label"]

    tp = int(((actual == 1) & (predicted == 1)).sum())
    tn = int(((actual == 0) & (predicted == 0)).sum())
    fp = int(((actual == 0) & (predicted == 1)).sum())
    fn = int(((actual == 1) & (predicted == 0)).sum())

    metrics = {
        "experiment": "Static Baseline v1",
        "total_queries": len(df),
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "accuracy": safe_divide(tp + tn, len(df)),
        "precision": safe_divide(tp, tp + fp),
        "recall": safe_divide(tp, tp + fn),
        "f1_score": safe_divide(2 * tp, 2 * tp + fp + fn),
        "false_positive_rate": safe_divide(fp, fp + tn),
        "latency_mean_ms": float(df["latency_ms"].mean()),
        "latency_median_ms": float(df["latency_ms"].median()),
        "latency_p95_ms": float(df["latency_ms"].quantile(0.95)),
    }

    print("\n=== STATIC HONEYTOKEN EVALUATION ===")

    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")

    OUTPUT.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()

