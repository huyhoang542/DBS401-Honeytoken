"""Summarize observed honeytoken hits without fitting the ML classifier.

Useful for quick placement experiments with fewer than five repeats, where the
ML threshold calibration is intentionally too small to be reliable.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
QUERY_PATH = RESULTS / "live_attack_query_results.csv"


def write_csv(path, rows):
    if not rows:
        raise SystemExit(f"No rows to write: {path}")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not QUERY_PATH.exists():
        raise SystemExit("No captured query log. Run run_live_attack_simulation.py --capture-only first.")

    with QUERY_PATH.open(newline="", encoding="utf-8-sig") as file:
        queries = list(csv.DictReader(file))
    if not queries:
        raise SystemExit("Captured query log is empty.")

    groups = defaultdict(list)
    for row in queries:
        groups[(row["demo"], row["session_id"])].append(row)

    session_rows = []
    for (demo, session_id), entries in sorted(groups.items()):
        hits = sum(int(row["static_honeytoken_hit"]) for row in entries)
        scenario = entries[0]["scenario_type"]
        session_rows.append({
            "demo": demo,
            "session_id": session_id,
            "scenario_type": scenario,
            "actual_label": int(entries[0]["actual_label"]),
            "query_count": len(entries),
            "token_hit_queries": hits,
            "token_rows_returned": sum(int(row.get("hit_count", 0)) for row in entries),
            "token_hit_session": int(hits > 0),
            "query_hit_rate": hits / len(entries) if entries else 0.0,
            "is_core_attack": int(int(entries[0]["actual_label"]) == 1 and scenario != "token_probe_validation"),
            "is_primary_placement_attack": int(
                scenario.startswith("target_department_") and not scenario.endswith("_latest_250")
            ),
        })

    scenario_rows = []
    families = sorted({(row["demo"], row["scenario_type"]) for row in session_rows})
    for demo, family in families:
        entries = [row for row in session_rows if row["demo"] == demo and row["scenario_type"] == family]
        query_count = sum(row["query_count"] for row in entries)
        hit_queries = sum(row["token_hit_queries"] for row in entries)
        scenario_rows.append({
            "demo": demo,
            "scenario_type": family,
            "actual_label": entries[0]["actual_label"],
            "sessions": len(entries),
            "token_hit_sessions": sum(row["token_hit_session"] for row in entries),
            "session_hit_rate": sum(row["token_hit_session"] for row in entries) / len(entries),
            "query_count": query_count,
            "token_hit_queries": hit_queries,
            "token_rows_returned": sum(row["token_rows_returned"] for row in entries),
            "query_hit_rate": hit_queries / query_count if query_count else 0.0,
            "is_primary_placement_attack": int(
                family.startswith("target_department_") and not family.endswith("_latest_250")
            ),
        })

    placement_summary = {}
    for demo in ("Demo A", "Demo B"):
        entries = [row for row in session_rows if row["demo"] == demo and row["is_primary_placement_attack"]]
        query_count = sum(row["query_count"] for row in entries)
        hit_queries = sum(row["token_hit_queries"] for row in entries)
        placement_summary[demo] = {
            "attack_sessions": len(entries),
            "token_hit_sessions": sum(row["token_hit_session"] for row in entries),
            "session_hit_rate": sum(row["token_hit_session"] for row in entries) / len(entries) if entries else 0.0,
            "attack_queries": query_count,
            "token_hit_queries": hit_queries,
            "token_rows_returned": sum(row["token_rows_returned"] for row in entries),
            "query_hit_rate": hit_queries / query_count if query_count else 0.0,
        }

    write_csv(RESULTS / "live_attack_placement_session_results.csv", session_rows)
    write_csv(RESULTS / "live_attack_placement_scenario_metrics.csv", scenario_rows)

    metrics_path = RESULTS / "live_attack_metrics.json"
    result = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    repeats = sorted({int(row["repeat"]) for row in queries if row.get("repeat")})
    result.update({
        "source": "actual read-only SELECT telemetry from local MySQL employee database",
        "shared_dataset": "employee",
        "repeats": len(repeats),
        "scenario_families": sorted({row["scenario_type"] for row in queries}),
        "placement_evaluation": {
            "metric": "observed honeytoken hits; classifier alerts are excluded",
            "primary_scenario": "seeded sample of 25 and 25 earliest hire dates per department",
            "core_attack_policy": "latest-250 and explicit token_probe_validation are excluded from the primary placement headline",
            "session_level_metrics": placement_summary,
            "session_results_csv": str(RESULTS / "live_attack_placement_session_results.csv"),
            "scenario_metrics_csv": str(RESULTS / "live_attack_placement_scenario_metrics.csv"),
        },
        "ml_evaluation_status": "NOT_UPDATED",
        "ml_evaluation_message": "Hit statistics were refreshed from the latest capture; ML threshold training was not completed. Existing ML metrics may be from an earlier run.",
    })
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    for demo, stats in placement_summary.items():
        print(f"{demo}: {stats['token_hit_sessions']}/{stats['attack_sessions']} primary attack sessions hit a token "
              f"({stats['session_hit_rate']:.1%}); {stats['token_hit_queries']}/{stats['attack_queries']} queries hit.")
    print(f"Saved placement summary for {len(repeats)} repeat(s). ML metrics were not trained or changed.")


if __name__ == "__main__":
    main()
