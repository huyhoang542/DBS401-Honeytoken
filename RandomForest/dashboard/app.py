"""Vietnamese dashboard for the Demo B upgrade and its A baseline."""
from pathlib import Path
import json
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Honeytoken thích nghi — Demo B", layout="wide")
st.title("Honeytoken thích nghi — Demo B")
st.caption(
    "Demo A là baseline tham chiếu theo bài báo; Demo B là phần nâng cấp của đồ án. "
    "Chọn tab để không trộn kết quả từ các nguồn dữ liệu khác nhau."
)

SCENARIO_VI = {
    "routine_point_lookup": "Tra cứu ID thông thường",
    "legitimate_bulk_report": "Báo cáo hàng loạt hợp lệ",
    "maintenance_read": "Đọc dữ liệu bảo trì",
    "rapid_id_enumeration": "Dò ID nhanh",
    "department_sweep": "Quét phòng ban",
    "broad_employee_collection": "Thu thập rộng dữ liệu nhân viên",
    "low_and_slow_targeting": "Dò tìm chậm (low-and-slow)",
    "token_probe_validation": "Kiểm tra token canary",
    "target_department": "Mục tiêu phòng ban",
    "afterhours_bulk_access": "Truy cập hàng loạt ngoài giờ",
    "offhours_maintenance": "Bảo trì ngoài giờ",
}
DETECTOR_VI = {
    "static": "A — cảnh báo theo token-hit",
    "ml": "B — Random Forest",
    "ml_or_token": "B — Random Forest kết hợp token",
    "A_static_honeytoken": "A — HMA, cảnh báo token-hit",
    "B_random_forest": "B — Random Forest",
    "B_random_forest_plus_honeytoken": "B — Random Forest kết hợp token",
}
METRIC_VI = {
    "sessions": "Số phiên (phiên)",
    "queries": "Số truy vấn (truy vấn)",
    "accuracy": "Tỷ lệ phân loại đúng — Accuracy (%)",
    "precision": "Độ chính xác cảnh báo — Precision (%)",
    "recall": "Tỷ lệ phát hiện — Recall (%)",
    "f1": "Điểm F1 (0–1)",
    "f1_score": "Điểm F1 (0–1)",
    "false_positive_rate": "Tỷ lệ báo động giả (%)",
    "TP": "TP — phát hiện đúng (phiên)",
    "TN": "TN — loại đúng (phiên)",
    "FP": "FP — báo nhầm (phiên)",
    "FN": "FN — bỏ sót (phiên)",
}


def scenario_name(value):
    if isinstance(value, str) and value.startswith("target_department_"):
        parts = value.split("_")
        dept = parts[2] if len(parts) > 2 else "không rõ"
        if value.endswith("_sample_25"):
            return f"Phòng ban {dept}: lấy mẫu có thứ tự giả ngẫu nhiên, 25 dòng"
        if value.endswith("_early_hire_25"):
            return f"Phòng ban {dept}: 25 nhân viên có ngày tuyển dụng sớm nhất"
        if value.endswith("_latest_250"):
            return f"Phòng ban {dept}: 250 ID cao nhất (chẩn đoán bão hòa)"
        return "Mục tiêu cụ thể: phòng ban " + value.removeprefix("target_department_")
    return SCENARIO_VI.get(value, value)


def method_name(value):
    return DETECTOR_VI.get(value, value)


def label_name(value):
    try:
        return "Đáng ngờ mô phỏng" if int(value) == 1 else "Bình thường"
    except (TypeError, ValueError):
        return value


def translated_columns(frame, mapping):
    return frame.rename(columns={key: value for key, value in mapping.items() if key in frame.columns})


def show_metric_table(summary, methods, count_key):
    rows = []
    for key in methods:
        if key not in summary:
            continue
        metric = summary[key]
        rows.append({
            "Phương pháp": method_name(key),
            f"Số mẫu ({'phiên' if count_key == 'sessions' else 'truy vấn'})": metric.get(count_key, 0),
            "TP — phát hiện đúng (phiên)": metric.get("TP", 0),
            "TN — loại đúng (phiên)": metric.get("TN", 0),
            "FP — báo nhầm (phiên)": metric.get("FP", 0),
            "FN — bỏ sót (phiên)": metric.get("FN", 0),
            METRIC_VI["accuracy"]: metric.get("accuracy", 0),
            METRIC_VI["precision"]: metric.get("precision", 0),
            METRIC_VI["recall"]: metric.get("recall", 0),
            METRIC_VI["f1"]: metric.get("f1", metric.get("f1_score", 0)),
            "Tỷ lệ báo động giả (%)": metric.get("false_positive_rate", 0),
        })
    if rows:
        frame = pd.DataFrame(rows)
        pct = [METRIC_VI["accuracy"], METRIC_VI["precision"], METRIC_VI["recall"], "Tỷ lệ báo động giả (%)"]
        st.dataframe(frame.style.format({**{column: "{:.1%}" for column in pct}, METRIC_VI["f1"]: "{:.3f}"}),
                     use_container_width=True, hide_index=True)
        st.caption("TP/TN/FP/FN và số mẫu được tính theo phiên hoặc truy vấn theo tên cột. F1 là điểm từ 0 đến 1.")


def load_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


tab_placement, tab_live, tab_synth = st.tabs([
    "1. Hiệu quả vị trí honeytoken",
    "2. Cảnh báo và phát hiện hành vi ML",
    "3. Benchmark tổng hợp",
])

with tab_placement:
    st.header("So sánh vị trí sinh/đặt honeytoken")
    st.write("Demo A là mốc HMA/SDV theo bài báo: HMA sinh nội dung và quan hệ, vị trí phòng ban giữ theo dữ liệu quan hệ HMA sinh ra. Demo B giữ nguyên nội dung, dùng Random Forest phân bổ vị trí theo rủi ro phòng ban. Kịch bản placement chính lấy mẫu có seed tối đa 25 dòng và đọc 25 nhân viên có ngày tuyển dụng sớm nhất tại từng phòng ban; truy vấn 250 ID cao nhất chỉ là chẩn đoán bão hòa. Cảnh báo ML được đánh giá riêng ở tab 2.")
    placement = ROOT / "results" / "live_attack_metrics.json"
    placement_sessions_path = ROOT / "results" / "live_attack_placement_session_results.csv"
    placement_scenarios_path = ROOT / "results" / "live_attack_placement_scenario_metrics.csv"
    if placement.exists() and placement_sessions_path.exists() and placement_scenarios_path.exists():
        data = json.loads(placement.read_text(encoding="utf-8"))
        experiment = data.get("placement_evaluation", {})
        summary = experiment.get("session_level_metrics", {})
        families_present = set(data.get("scenario_families", []))
        has_updated_protocol = (
            any(name.endswith("_sample_25") for name in families_present)
            and any(name.endswith("_early_hire_25") for name in families_present)
            and int(data.get("repeats", 0)) >= 5
        )
        if not has_updated_protocol:
            if any(name.endswith("_sample_25") for name in families_present) and any(name.endswith("_early_hire_25") for name in families_present):
                st.warning(f"Đã có kết quả kịch bản mục tiêu mới với {data.get('repeats', 0)} lần lặp. Đây là kết quả sơ bộ; nên chạy ít nhất 5 lần để so sánh ổn định hơn.")
            else:
                st.warning("Các số liệu đang hiển thị được tạo theo giao thức cũ (truy vấn 250 ID cao nhất), có thể bị bão hòa. Chưa có kết quả của bộ kịch bản mới; hãy chạy capture/train thủ công theo README trước khi kết luận.")
        if summary:
            rows = []
            for demo, label in (("Demo A", "A — SDV/HMA (vị trí HMA)"), ("Demo B", "B — SDV/HMA + Random Forest (vị trí theo rủi ro)")):
                metric = summary.get(demo, {})
                rows.append({
                    "Phương pháp": label,
                    "Phiên tấn công (phiên)": metric.get("attack_sessions", 0),
                    "Phiên có token hit (phiên)": metric.get("token_hit_sessions", 0),
                    "Tỷ lệ phiên có hit (%)": metric.get("session_hit_rate", 0),
                    "Truy vấn tấn công (truy vấn)": metric.get("attack_queries", 0),
                    "Truy vấn trả token (truy vấn)": metric.get("token_hit_queries", 0),
                    "Tỷ lệ truy vấn có hit (%)": metric.get("query_hit_rate", 0),
                    "Số dòng token trả về (lượt)": metric.get("token_rows_returned", 0),
                })
            st.dataframe(pd.DataFrame(rows).style.format({"Tỷ lệ phiên có hit (%)": "{:.1%}", "Tỷ lệ truy vấn có hit (%)": "{:.1%}"}), use_container_width=True, hide_index=True)
            st.caption("Đơn vị: phiên, truy vấn, lượt xuất hiện token và tỷ lệ %. Tổng chính loại truy vấn 250 ID cao nhất vì dễ làm bão hòa hit; kịch bản này vẫn được liệt kê riêng để chẩn đoán.")
            st.info("Để kết luận có ý nghĩa, cần cùng database, cùng số lượng token, cùng kịch bản/lượt chạy, và token A/B phải được nạp từ candidate mới. Đây là kết quả lab mô phỏng.")
        else:
            st.warning("Các file hiện có được tạo trước khi có phép đo riêng cho vị trí token. Chạy lại capture và huấn luyện sau khi nạp candidates A/B mới.")
        scenarios = load_csv(placement_scenarios_path)
        if not scenarios.empty:
            core = scenarios[scenarios["scenario_type"] != "token_probe_validation"].copy()
            core["Kịch bản"] = core["scenario_type"].map(scenario_name)
            core["Phương pháp"] = core["demo"].map({"Demo A": "A — SDV/HMA", "Demo B": "B — RF chọn vị trí"})
            core["Phiên (phiên)"] = core["sessions"]
            core["Phiên có hit (phiên)"] = core["token_hit_sessions"]
            core["Tỷ lệ phiên có hit (%)"] = core["session_hit_rate"]
            core["Truy vấn trả token (truy vấn)"] = core["token_hit_queries"]
            core["Truy vấn (truy vấn)"] = core["query_count"]
            core["Số dòng token trả về (lượt)"] = core.get("token_rows_returned", 0)
            st.subheader("Kết quả theo từng mục tiêu và cách truy vấn")
            st.dataframe(core[["Kịch bản", "Phương pháp", "Phiên (phiên)", "Phiên có hit (phiên)", "Tỷ lệ phiên có hit (%)", "Truy vấn trả token (truy vấn)", "Truy vấn (truy vấn)", "Số dòng token trả về (lượt)"]].style.format({"Tỷ lệ phiên có hit (%)": "{:.1%}"}), use_container_width=True, hide_index=True)
        session_logs = load_csv(placement_sessions_path)
        if not session_logs.empty:
            st.subheader("Log kết quả từng kịch bản/lượt")
            if "token_rows_returned" not in session_logs.columns:
                session_logs["token_rows_returned"] = 0
            session_logs["Kịch bản"] = session_logs["scenario_type"].map(scenario_name)
            session_logs = session_logs.rename(columns={"demo": "Demo", "session_id": "ID phiên", "actual_label": "Nhãn (0=bình thường, 1=đáng ngờ)", "query_count": "Truy vấn (truy vấn)", "token_hit_queries": "Truy vấn có token hit (truy vấn)", "token_rows_returned": "Số dòng token trả về (lượt)", "token_hit_session": "Phiên có hit (0/1)", "query_hit_rate": "Tỷ lệ truy vấn có hit (%)", "is_core_attack": "Thuộc tổng tấn công chính (0/1)"})
            st.dataframe(session_logs[["Demo", "ID phiên", "Kịch bản", "Nhãn (0=bình thường, 1=đáng ngờ)", "Truy vấn (truy vấn)", "Truy vấn có token hit (truy vấn)", "Số dòng token trả về (lượt)", "Phiên có hit (0/1)", "Tỷ lệ truy vấn có hit (%)", "Thuộc tổng tấn công chính (0/1)"]], use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có log đo token hit riêng. Nạp candidates A/B theo README Demo A/B, sau đó chạy lại capture và train để tạo kết quả vị trí.")

with tab_live:
    st.header("Cảnh báo và phát hiện hành vi bằng Random Forest")
    st.write("Các chỉ số ở tab này đánh giá khả năng phân loại hành vi. Chúng không đo hiệu quả vị trí honeytoken; xem tab 1 để so sánh token hit.")
    live_metrics_path = ROOT / "results" / "live_attack_metrics.json"
    live_sessions_path = ROOT / "results" / "live_attack_session_results.csv"
    live_scenarios_path = ROOT / "results" / "live_attack_scenario_metrics.csv"
    live_queries_path = ROOT / "results" / "live_attack_query_results.csv"
    if live_metrics_path.exists() and live_sessions_path.exists():
        live = json.loads(live_metrics_path.read_text(encoding="utf-8"))
        if live.get("ml_evaluation_status") == "NOT_UPDATED":
            st.warning(live.get("ml_evaluation_message", "Kết quả ML chưa được cập nhật cho capture mới nhất."))
        summary = live.get("session_level_metrics", {})
        show_metric_table(summary, [
            "Demo A static honeytoken",
            "Demo B live-telemetry Random Forest",
        ], "sessions")
        st.caption(
            f"Nguồn telemetry: {live.get('source', 'MySQL cục bộ')}; "
            f"database dùng chung: {live.get('shared_dataset', 'employee')}. "
            "Nhãn do script kịch bản gán, không phải nhãn sự cố thực tế."
        )
        st.info("Kết quả chỉ phản ánh kịch bản lab đã chạy; không dùng các tỷ lệ này làm ước lượng hiệu quả trong môi trường sản xuất.")

        scenario_df = load_csv(live_scenarios_path)
        if not scenario_df.empty:
            main_scenarios = scenario_df[scenario_df["detector"].isin(["static", "ml"])].copy()
            main_scenarios["Kịch bản"] = main_scenarios["scenario_type"].map(scenario_name)
            main_scenarios["Nhãn kiểm thử"] = main_scenarios["actual_label"].map(label_name)
            main_scenarios["Phương pháp"] = main_scenarios["detector"].map(method_name)
            main_scenarios["Số phiên (phiên)"] = main_scenarios["sessions"]
            main_scenarios["Tỷ lệ cảnh báo (%)"] = main_scenarios["session_alert_rate"]
            table = main_scenarios.pivot(index=["Kịch bản", "Nhãn kiểm thử", "Số phiên (phiên)"],
                                         columns="Phương pháp", values="Tỷ lệ cảnh báo (%)").reset_index()
            table.columns.name = None
            st.subheader("Kết quả theo từng kịch bản")
            st.dataframe(table.style.format({column: "{:.1%}" for column in table.columns if column.startswith("A —") or column.startswith("B —")}),
                         use_container_width=True, hide_index=True)
            st.caption("Với kịch bản bình thường, tỷ lệ cảnh báo là tỷ lệ báo động giả; với kịch bản đáng ngờ, đó là tỷ lệ phát hiện. Số phiên mỗi kịch bản được ghi ngay trong bảng.")

        with st.expander("Thử nghiệm phụ: B kết hợp Random Forest với token hit"):
            if summary.get("Demo B Random Forest OR token hit"):
                show_metric_table(summary, ["Demo B Random Forest OR token hit"], "sessions")
                st.caption("Đây là ablation phụ; bảng so sánh chính phía trên chỉ giữ baseline A và mô hình nâng cấp B.")
            else:
                st.info("Chưa có metric cho biến thể kết hợp token.")

        session_df = load_csv(live_sessions_path)
        if not session_df.empty:
            st.subheader("Log kết quả từng phiên/kịch bản")
            family_values = sorted(session_df["scenario_type"].dropna().unique())
            selected_family = st.selectbox("Lọc kịch bản", ["Tất cả"] + family_values,
                                          format_func=lambda value: "Tất cả kịch bản" if value == "Tất cả" else scenario_name(value),
                                          key="live_family")
            filtered = session_df.copy()
            if selected_family != "Tất cả":
                filtered = filtered[filtered["scenario_type"] == selected_family]
            filtered["Lượt"] = filtered["session_id"].str.extract(r"^r(\d+)-", expand=False).astype(int)
            paired = filtered.pivot(index=["Lượt", "scenario_type", "actual_label"], columns="demo",
                                    values=["query_count", "A_static_alert", "B_ml_alert", "B_ml_or_token_alert"])
            paired.columns = [f"{value} — {demo}" for value, demo in paired.columns]
            paired = paired.reset_index().rename(columns={
                "scenario_type": "Kịch bản", "actual_label": "Nhãn kiểm thử (0=bình thường, 1=đáng ngờ)",
                "query_count — Demo A": "Số truy vấn A (truy vấn)",
                "query_count — Demo B": "Số truy vấn B (truy vấn)",
                "A_static_alert — Demo A": "A cảnh báo (0/1)",
                "B_ml_alert — Demo B": "B cảnh báo (0/1)",
                "B_ml_or_token_alert — Demo B": "B + token cảnh báo (0/1)",
            })
            paired["Kịch bản"] = paired["Kịch bản"].map(scenario_name)
            paired["Nhãn kiểm thử (0=bình thường, 1=đáng ngờ)"] = paired["Nhãn kiểm thử (0=bình thường, 1=đáng ngờ)"].map(label_name)
            columns = ["Lượt", "Kịch bản", "Nhãn kiểm thử (0=bình thường, 1=đáng ngờ)",
                       "Số truy vấn A (truy vấn)", "A cảnh báo (0/1)",
                       "Số truy vấn B (truy vấn)", "B cảnh báo (0/1)", "B + token cảnh báo (0/1)"]
            st.dataframe(paired[[column for column in columns if column in paired]],
                         use_container_width=True, hide_index=True)
            st.caption("Mỗi dòng ghép cùng kịch bản và lượt lặp giữa hai demo. Cột B + token là phân tích phụ; 0 nghĩa là không cảnh báo, 1 là có cảnh báo.")
            st.download_button("Tải log phiên đã ghép A/B (CSV)", paired[columns].to_csv(index=False).encode("utf-8-sig"),
                               file_name="log_phien_mysql_lab_da_ghep.csv", mime="text/csv", key="dl_live_sessions")

        query_df = load_csv(live_queries_path)
        if not query_df.empty:
            with st.expander("Log telemetry từng truy vấn SELECT"):
                q_family_values = sorted(query_df["scenario_type"].dropna().unique())
                q_family = st.selectbox("Kịch bản trong log truy vấn", ["Tất cả"] + q_family_values,
                                        format_func=lambda value: "Tất cả kịch bản" if value == "Tất cả" else scenario_name(value),
                                        key="live_query_family")
                q_demo = st.selectbox("Demo trong log truy vấn", ["Tất cả", "Demo A", "Demo B"], key="live_query_demo")
                q_repeat = st.selectbox("Lượt lặp", ["Tất cả"] + sorted(query_df["repeat"].unique().tolist()), key="live_query_repeat")
                q_filtered = query_df.copy()
                if q_family != "Tất cả":
                    q_filtered = q_filtered[q_filtered["scenario_type"] == q_family]
                if q_demo != "Tất cả":
                    q_filtered = q_filtered[q_filtered["demo"] == q_demo]
                if q_repeat != "Tất cả":
                    q_filtered = q_filtered[q_filtered["repeat"] == q_repeat]
                q_filtered["scenario_type"] = q_filtered["scenario_type"].map(scenario_name)
                q_filtered["actual_label"] = q_filtered["actual_label"].map(label_name)
                q_filtered = translated_columns(q_filtered, {
                    "demo": "Demo", "repeat": "Lượt lặp", "session_id": "ID phiên",
                    "scenario_type": "Kịch bản", "actual_label": "Nhãn kiểm thử",
                    "scenario_id": "ID truy vấn", "result_count": "Số dòng trả về (dòng)",
                    "hour": "Giờ tại máy (0–23)", "target_table_count": "Số bảng mục tiêu (bảng)",
                    "query_frequency": "Thứ tự truy vấn trong phiên (truy vấn)",
                    "query_duration_ms": "Thời lượng (ms)",
                    "is_department_query": "Truy vấn phòng ban (0/1)",
                    "static_honeytoken_hit": "Token hit (0/1)", "hit_count": "Số token hit (token)",
                    "query_type": "Loại truy vấn", "risk_score": "Điểm rủi ro (0–1)",
                    "ml_predicted_label": "Dự đoán ML theo truy vấn (0/1)",
                })
                st.dataframe(q_filtered, use_container_width=True, hide_index=True)
                st.download_button("Tải log truy vấn đang lọc (CSV)", q_filtered.to_csv(index=False).encode("utf-8-sig"),
                                   file_name="log_truy_van_mysql_lab.csv", mime="text/csv", key="dl_live_queries")
                st.caption("Đơn vị thời lượng là mili giây (ms); giờ là giờ tại máy khi chạy. Nếu log có cột dự đoán ML, đó là dự đoán giữ lại ngoài fold (out-of-fold); nếu không có, mô hình chỉ được báo cáo ở mức phiên.")
    else:
        st.info("Chưa có kết quả MySQL lab. Từ thư mục RandomForest chạy: `python evaluation\\run_live_attack_simulation.py --capture-only`, sau đó `python evaluation\\train_live_model.py`.")

with tab_synth:
    st.header("Benchmark hành vi tổng hợp")
    st.write("Tab này dùng các mẫu hành vi do NumPy tạo để so sánh thuật toán; không đọc log truy vấn MySQL thật. Không gộp số liệu ở tab này với tab MySQL lab.")
    metrics_path = ROOT / "results" / "ab_metrics.csv"
    scenario_path = ROOT / "results" / "ab_scenario_metrics.csv"
    query_path = ROOT / "results" / "ab_query_results.csv"
    if metrics_path.exists():
        synthetic_metrics = pd.read_csv(metrics_path)
        main_methods = synthetic_metrics[synthetic_metrics["model"].isin(["A_static_honeytoken", "B_random_forest"])].copy()
        main_methods["Phương pháp"] = main_methods["model"].map(method_name)
        main_methods = main_methods.rename(columns={
            "accuracy": METRIC_VI["accuracy"], "precision": METRIC_VI["precision"], "recall": METRIC_VI["recall"],
            "f1_score": METRIC_VI["f1_score"], "false_positive_rate": "Tỷ lệ báo động giả (%)",
            "mean_prediction_latency_ms": "Thời gian chấm điểm trung bình (ms/truy vấn)",
        })
        display_columns = ["Phương pháp", METRIC_VI["accuracy"], METRIC_VI["precision"], METRIC_VI["recall"], METRIC_VI["f1_score"],
                           "Tỷ lệ báo động giả (%)", "Thời gian chấm điểm trung bình (ms/truy vấn)"]
        st.dataframe(main_methods[[column for column in display_columns if column in main_methods]].style.format({
            METRIC_VI["accuracy"]: "{:.1%}", METRIC_VI["precision"]: "{:.1%}", METRIC_VI["recall"]: "{:.1%}",
            METRIC_VI["f1_score"]: "{:.3f}", "Tỷ lệ báo động giả (%)": "{:.1%}",
            "Thời gian chấm điểm trung bình (ms/truy vấn)": "{:.4f}",
        }), use_container_width=True, hide_index=True)
        st.caption("Năm lần chia train/test; mỗi lần đánh giá trên 600 mẫu giữ lại. Độ trễ là thời gian suy luận trong tiến trình, đơn vị ms/truy vấn; không gồm thời gian MySQL.")
        st.warning("Các đặc trưng, nhãn và tỷ lệ token hit của benchmark này đều được sinh/mô phỏng bằng chương trình; đây không phải kết quả trên traffic thực.")

        synth_scenarios = load_csv(scenario_path)
        if not synth_scenarios.empty:
            main_scenarios = synth_scenarios[synth_scenarios["model"].isin(["A_static_honeytoken", "B_random_forest"])].copy()
            main_scenarios["Kịch bản"] = main_scenarios["scenario_type"].map(scenario_name)
            main_scenarios["Nhãn"] = main_scenarios["actual_label"].map(label_name)
            main_scenarios["Phương pháp"] = main_scenarios["model"].map(method_name)
            main_scenarios["Số mẫu (mẫu)"] = main_scenarios["scenario_count"]
            main_scenarios["Tỷ lệ cảnh báo (%)"] = main_scenarios["alert_rate"]
            table = main_scenarios.pivot(index=["Kịch bản", "Nhãn", "Số mẫu (mẫu)"], columns="Phương pháp",
                                         values="Tỷ lệ cảnh báo (%)").reset_index()
            table.columns.name = None
            st.subheader("Kết quả theo từng kịch bản tổng hợp")
            st.dataframe(table.style.format({column: "{:.1%}" for column in table.columns if column.startswith("A —") or column.startswith("B —")}),
                         use_container_width=True, hide_index=True)
            st.caption("Mỗi kịch bản tổng hợp có số mẫu ghi trong bảng. Với nhãn bình thường, tỷ lệ cảnh báo là báo động giả; với nhãn đáng ngờ, là tỷ lệ phát hiện.")

        with st.expander("Thử nghiệm phụ: Random Forest kết hợp honeytoken"):
            optional = synthetic_metrics[synthetic_metrics["model"] == "B_random_forest_plus_honeytoken"].copy()
            if not optional.empty:
                optional["Phương pháp"] = optional["model"].map(method_name)
                optional = optional.rename(columns={
                    "accuracy": METRIC_VI["accuracy"], "precision": METRIC_VI["precision"], "recall": METRIC_VI["recall"],
                    "f1_score": METRIC_VI["f1_score"], "false_positive_rate": "Tỷ lệ báo động giả (%)",
                    "mean_prediction_latency_ms": "Thời gian chấm điểm trung bình (ms/truy vấn)",
                })
                st.dataframe(optional[[column for column in display_columns if column in optional]].style.format({
                    METRIC_VI["accuracy"]: "{:.1%}", METRIC_VI["precision"]: "{:.1%}", METRIC_VI["recall"]: "{:.1%}",
                    METRIC_VI["f1_score"]: "{:.3f}", "Tỷ lệ báo động giả (%)": "{:.1%}",
                    "Thời gian chấm điểm trung bình (ms/truy vấn)": "{:.4f}",
                }), use_container_width=True, hide_index=True)
                st.caption("Đây là phân tích phụ, không phải phương pháp chính được dùng để tuyên bố Demo B nâng cấp.")
            else:
                st.info("Không tìm thấy dòng kết quả cho biến thể phụ.")

        query_df = load_csv(query_path)
        if not query_df.empty:
            st.subheader("Log dự đoán từng mẫu trong từng kịch bản")
            families = sorted(query_df["scenario_type"].dropna().unique())
            family = st.selectbox("Lọc kịch bản tổng hợp", ["Tất cả"] + families,
                                  format_func=lambda value: "Tất cả kịch bản" if value == "Tất cả" else scenario_name(value),
                                  key="synth_family")
            model_choices = ["A_static_honeytoken", "B_random_forest"]
            if "B_random_forest_plus_honeytoken" in set(query_df["model"]):
                model_choices.append("B_random_forest_plus_honeytoken")
            selected_model = st.selectbox("Phương pháp trong log", model_choices, format_func=method_name, key="synth_model")
            repeat = st.selectbox("Lượt benchmark", ["Tất cả"] + sorted(query_df["repeat"].unique().tolist()), key="synth_repeat")
            filtered = query_df[query_df["model"] == selected_model].copy()
            if family != "Tất cả":
                filtered = filtered[filtered["scenario_type"] == family]
            if repeat != "Tất cả":
                filtered = filtered[filtered["repeat"] == repeat]
            filtered["scenario_type"] = filtered["scenario_type"].map(scenario_name)
            filtered["actual_label"] = filtered["actual_label"].map(label_name)
            filtered["predicted_label"] = filtered["predicted_label"].map(label_name)
            filtered = translated_columns(filtered, {
                "repeat": "Lượt", "scenario_id": "ID mẫu", "scenario_type": "Kịch bản",
                "subject_emp_no": "ID nhân viên mẫu", "actual_label": "Nhãn thực tế",
                "static_honeytoken_hit": "Token hit (0/1)", "result_count": "Số dòng trả về (dòng)",
                "hour": "Giờ (0–23)", "target_table_count": "Số bảng (bảng)",
                "query_frequency": "Tần suất trong phiên (truy vấn)", "query_duration_ms": "Thời lượng (ms)",
                "is_department_query": "Truy vấn phòng ban (0/1)", "model": "Phương pháp",
                "predicted_label": "Dự đoán (0/1)", "risk_score": "Điểm rủi ro (0–1)",
                "latency_ms": "Độ trễ chấm điểm (ms/truy vấn)",
            })
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            st.download_button("Tải log mẫu đang lọc (CSV)", filtered.to_csv(index=False).encode("utf-8-sig"),
                               file_name="log_benchmark_tong_hop.csv", mime="text/csv", key="dl_synth")
    else:
        st.info("Chưa có benchmark. Từ thư mục RandomForest chạy: `python evaluation\\run_common_scenarios.py`.")
