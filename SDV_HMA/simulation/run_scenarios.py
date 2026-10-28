
import csv
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
GATEWAY = ROOT / "monitoring" / "query_monitor.py"
OUTPUT = ROOT / "results" / "static_baseline_results.csv"

def main():
    # 50 employees from the original dataset
    normal_ids = list(range(10001, 10051))

    # 50 deployed honeytokens
    manifest_path = ROOT / "database" / "hma_artifacts" / "manifest.json"
    if manifest_path.exists():
        token_start = int(json.loads(manifest_path.read_text(encoding="utf-8"))["token_start"])
    else:
        token_start = int(os.getenv("HONEYTOKEN_START", "910001"))
    honeytoken_ids = list(range(token_start, token_start + 50))

    scenarios = (
        [(emp_no, 0) for emp_no in normal_ids]
        + [(emp_no, 1) for emp_no in honeytoken_ids]
    )

    random.Random(SEED).shuffle(scenarios)
    results = []

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    for index, (emp_no, actual_label) in enumerate(scenarios, 1):
        start = time.perf_counter()

        process = subprocess.run(
            [sys.executable, str(GATEWAY), str(emp_no)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        latency_ms = round(
            (time.perf_counter() - start) * 1000, 2
        )

        output = process.stdout

        if process.returncode != 0:
            print(f"ERROR at employee {emp_no}")
            print(process.stderr)
            raise RuntimeError(
                "Experiment stopped. Failed requests "
                "are not counted as negative predictions."
            )

        if "ALERT: Honeytoken accessed!" in output:
            predicted_label = 1
        elif "No honeytoken detected." in output:
            predicted_label = 0
        else:
            raise RuntimeError(
                f"Unexpected gateway output for {emp_no}"
            )

        results.append({
            "emp_no": emp_no,
            "actual_label": actual_label,
            "predicted_label": predicted_label,
            "latency_ms": latency_ms,
        })

        print(
            f"[{index:03d}/100] "
            f"emp_no={emp_no} "
            f"actual={actual_label} "
            f"predicted={predicted_label}"
        )

    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "emp_no",
                "actual_label",
                "predicted_label",
                "latency_ms",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print("\nExperiment completed.")
    print(f"Total scenarios: {len(results)}")
    print(f"Results saved to: {OUTPUT}")


if __name__ == "__main__":
    main()

