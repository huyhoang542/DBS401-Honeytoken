from pathlib import Path
import json
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.risk_model import score_behavior  # noqa: E402
from monitoring.behavior_store import latest_events  # noqa: E402

st.set_page_config(page_title="Adaptive Honeytoken — Demo B", layout="wide")
st.title("Adaptive Honeytoken — Demo B")
st.caption("Controlled-lab MySQL telemetry, supervised risk scoring, and adaptive placement")

st.subheader("Live MySQL attack-scenario comparison")
live_metrics_path = ROOT / "results" / "live_attack_metrics.json"
live_sessions_path = ROOT / "results" / "live_attack_session_results.csv"
live_scenarios_path = ROOT / "results" / "live_attack_scenario_metrics.csv"
if live_metrics_path.exists() and live_sessions_path.exists():
    live = json.loads(live_metrics_path.read_text(encoding="utf-8"))
    summary = live.get("session_level_metrics", {})
    if summary:
        order = [
            "Demo A static honeytoken",
            "Demo B live-telemetry Random Forest",
            "Demo B Random Forest OR token hit",
        ]
        rows = []
        for method in order:
            if method in summary:
                row = {"Method": method, **summary[method]}
                rows.append(row)
        comparison = pd.DataFrame(rows).rename(columns={
            "sessions": "Sessions", "accuracy": "Accuracy", "precision": "Precision",
            "recall": "Recall", "f1": "F1", "false_positive_rate": "False positive rate",
            "TP": "TP", "TN": "TN", "FP": "FP", "FN": "FN",
        })
        st.dataframe(comparison.style.format({
            "Accuracy": "{:.1%}", "Precision": "{:.1%}", "Recall": "{:.1%}",
            "F1": "{:.3f}", "False positive rate": "{:.1%}",
        }), use_container_width=True, hide_index=True)
    st.caption(
        f"Source: {live.get('source', 'unknown')}. "
        f"Labels: {live.get('label_policy', 'scenario labels')}. "
        "Demo B features come from executed MySQL SELECTs; labels come from the controlled scenario script, not real incident reports."
    )
    if live_scenarios_path.exists():
        by_scenario = pd.read_csv(live_scenarios_path)
        if not by_scenario.empty:
            by_scenario["Detector"] = by_scenario.apply(
                lambda row: f"{row['demo']} — {row['detector']}", axis=1
            )
            family_table = by_scenario.pivot_table(
                index="scenario_type", columns="Detector",
                values="session_alert_rate", aggfunc="first",
            )
            st.markdown("**Alert rate by scenario family**")
            st.dataframe(family_table.style.format("{:.0%}"), use_container_width=True)
            st.bar_chart(family_table)
    if live_sessions_path.exists():
        st.download_button(
            "Download session comparison CSV",
            data=live_sessions_path.read_bytes(),
            file_name="live_attack_session_results.csv",
            mime="text/csv",
        )
else:
    st.info(
        "Run `python evaluation/run_live_attack_simulation.py --capture-only`, "
        "then `python evaluation/train_live_model.py` to build this live comparison."
    )
st.caption("This is controlled-lab evidence; the rates do not estimate production performance.")

st.subheader("A/B benchmark comparison")
metrics_path = ROOT / "results" / "ab_metrics.csv"
if metrics_path.exists():
    comparison = pd.read_csv(metrics_path)
    comparison = comparison.rename(columns={
        "model": "Method", "accuracy": "Accuracy", "precision": "Precision",
        "recall": "Recall", "f1_score": "F1", "false_positive_rate": "FPR",
        "mean_prediction_latency_ms": "Mean latency (ms)"})
    st.dataframe(comparison.style.format({
        "Accuracy": "{:.1%}", "Precision": "{:.1%}", "Recall": "{:.1%}",
        "F1": "{:.3f}", "FPR": "{:.1%}", "Mean latency (ms)": "{:.4f}"
    }), use_container_width=True, hide_index=True)
    st.caption("Five held-out runs on the same seeded scenario cases. These are synthetic behavior scenarios; see comparison/RESULTS.md for details.")
    scenario_path = ROOT / "results" / "ab_scenario_metrics.csv"
    if scenario_path.exists():
        with st.expander("Results by test scenario"):
            by_scenario = pd.read_csv(scenario_path).rename(columns={
                "scenario_type": "Scenario", "model": "Method",
                "scenario_count": "Cases", "actual_label": "Suspicious (1)",
                "alert_rate": "Alert rate", "correct_rate": "Correct rate"})
            st.dataframe(by_scenario.style.format({"Alert rate": "{:.1%}", "Correct rate": "{:.1%}"}),
                         use_container_width=True, hide_index=True)
else:
    st.info("Run python evaluation/run_common_scenarios.py to generate the shared A/B scenario tables.")
left, right = st.columns(2)
with left:
    st.subheader("Behavior risk scorer")
    count = st.slider("Rows returned", 1, 500, 25)
    hour = st.slider("Access hour", 0, 23, 14)
    tables = st.slider("Tables touched", 1, 5, 2)
    freq = st.slider("Recent query frequency", 1, 300, 20)
    duration = st.slider("Query duration (ms)", 1, 1000, 80)
    dept_query = st.checkbox("Department query", value=True)
    features = {"result_count": count, "hour": hour, "target_table_count": tables,
                "query_frequency": freq, "query_duration_ms": duration,
                "is_department_query": int(dept_query)}
    result = score_behavior(features)
    st.metric("Model risk", f"{result['score']:.1%}", result["label"])
    model_metadata_path = ROOT / "models" / "live_sim_model_metadata.json"
    if model_metadata_path.exists():
        model_metadata = json.loads(model_metadata_path.read_text(encoding="utf-8"))
        st.caption(
            f"Loaded model: {model_metadata.get('model', 'unknown')} · "
            f"{model_metadata.get('rows', 0)} lab query rows · "
            f"{model_metadata.get('sessions', 0)} sessions · calibrated threshold {model_metadata.get('threshold', 0.65):.2f} · "
            f"calibration FPR {model_metadata.get('calibration_session_metrics', {}).get('false_positive_rate', 0):.1%}"
        )
        st.info("The features are captured from local MySQL queries. Training labels are controlled scenario labels; this score is not a validated attack probability.")
    else:
        st.info("No live-trained model metadata found. The fallback score is only a preview; run the capture and training commands above.")
with right:
    st.subheader("Recent gateway predictions")
    recent = latest_events(50)
    if recent:
        st.dataframe(pd.DataFrame(recent), use_container_width=True)
    else:
        st.info("No gateway events recorded yet.")
    st.subheader("Placement update history")
    history = ROOT / "results" / "placement_history.csv"
    if history.exists():
        df = pd.read_csv(history)
        st.metric("Recorded moves", len(df))
        st.dataframe(df.tail(100), use_container_width=True)
    else:
        st.info("No applied placement updates yet. Run adaptive/placement.py --dry-run to review a recommendation.")
