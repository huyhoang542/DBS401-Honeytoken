
import os

import mysql.connector
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Honeytoken HMA — Demo A",
    page_icon="🛡️",
    layout="wide",
)

st.title("Demo A — Honeytoken theo SDV/HMA")
st.caption("Mốc tham chiếu theo bài báo: HMA sinh dữ liệu quan hệ; cảnh báo được tạo khi bản ghi token được truy cập. Bộ giám sát A dùng quy tắc token-hit, không dùng bộ phân loại hành vi ML.")


def connect_monitor():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["MONITOR_USER"],
        password=os.environ["MONITOR_PASSWORD"],
        database="honeytoken_security",
    )


def load_data():
    conn = connect_monitor()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM honeytoken_registry "
            "WHERE is_active = TRUE"
        )
        token_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM access_events")
        event_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM access_events WHERE honeytoken_hit = TRUE")
        hit_event_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM security_alerts")
        alert_count = cursor.fetchone()[0]

        cursor.close()

        events_cursor = conn.cursor(dictionary=True)
        events_cursor.execute("""
            SELECT
                event_id,
                username,
                query_type,
                target_table,
                returned_rows,
                honeytoken_hit,
                event_time
            FROM access_events
            ORDER BY event_id DESC
            LIMIT 500
        """)
        events = pd.DataFrame(events_cursor.fetchall())
        events_cursor.close()

        alerts_cursor = conn.cursor(dictionary=True)
        alerts_cursor.execute("""
            SELECT
                a.alert_id,
                a.event_id,
                a.severity,
                a.message,
                e.event_time
            FROM security_alerts AS a
            LEFT JOIN access_events AS e ON e.event_id = a.event_id
            ORDER BY a.alert_id DESC
            LIMIT 500
        """)
        alerts = pd.DataFrame(alerts_cursor.fetchall())
        alerts_cursor.close()

        return token_count, event_count, hit_event_count, alert_count, events, alerts

    finally:
        conn.close()


if st.button("Refresh data"):
    st.rerun()

try:
    tokens, events_count, hit_event_count, alerts_count, events, alerts = load_data()

except (mysql.connector.Error, KeyError) as exc:
    st.error("Unable to load monitoring data. Check database credentials.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)

col1.metric("Token đang hoạt động (token)", tokens)
col2.metric("Sự kiện truy cập (sự kiện)", events_count)
col3.metric("Sự kiện có token hit (sự kiện)", hit_event_count)
col4.metric("Cảnh báo đã tạo (cảnh báo)", alerts_count)
st.caption(f"Tỷ lệ sự kiện token-hit: {hit_event_count / events_count:.1%}" if events_count else "Chưa có sự kiện để tính tỷ lệ token-hit.")

st.divider()

st.subheader("Log truy cập")

if events.empty:
    st.info("No access events recorded.")
else:
    events = events.rename(columns={"event_id": "ID sự kiện", "username": "Tài khoản", "query_type": "Loại truy vấn", "target_table": "Bảng đích", "returned_rows": "Số dòng trả về (dòng)", "honeytoken_hit": "Token hit (0/1)", "event_time": "Thời điểm"})
    st.dataframe(events, use_container_width=True, hide_index=True)

    st.subheader("Phân tích hit và cảnh báo")

    hit_counts = (
        events["Token hit (0/1)"]
        .value_counts()
        .rename(index={0: "Không hit token", 1: "Có hit token"})
    )

    st.bar_chart(hit_counts)
    st.caption("Đồ thị đếm trong tối đa 500 sự kiện gần nhất; chỉ số phía trên dùng tổng số ghi nhận trong database.")

st.divider()

st.subheader("Log cảnh báo")

if alerts.empty:
    st.success("Chưa ghi nhận cảnh báo.")
else:
    alerts = alerts.rename(columns={"alert_id": "ID cảnh báo", "event_id": "ID sự kiện", "severity": "Mức độ", "message": "Nội dung", "alert_time": "Thời điểm"})
    st.dataframe(alerts, use_container_width=True, hide_index=True)
    st.warning(f"Đã ghi nhận {alerts_count} cảnh báo. Trong Demo A, cảnh báo được kích hoạt khi token được truy cập.")

