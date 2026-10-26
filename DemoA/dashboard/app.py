
import os

import mysql.connector
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Static Honeytoken Dashboard",
    page_icon="🛡️",
    layout="wide",
)

st.title("Static Honeytoken Monitoring")
st.caption("DBS401 | Demo A - Static Baseline v1")


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
                a.created_at
            FROM security_alerts AS a
            ORDER BY a.alert_id DESC
            LIMIT 500
        """)
        alerts = pd.DataFrame(alerts_cursor.fetchall())
        alerts_cursor.close()

        return token_count, event_count, alert_count, events, alerts

    finally:
        conn.close()


if st.button("Refresh data"):
    st.rerun()

try:
    tokens, events_count, alerts_count, events, alerts = load_data()

except (mysql.connector.Error, KeyError) as exc:
    st.error("Unable to load monitoring data. Check database credentials.")
    st.stop()

col1, col2, col3 = st.columns(3)

col1.metric("Active Honeytokens", tokens)
col2.metric("Access Events", events_count)
col3.metric("Security Alerts", alerts_count)

st.divider()

st.subheader("Access Events")

if events.empty:
    st.info("No access events recorded.")
else:
    st.dataframe(events, use_container_width=True, hide_index=True)

    st.subheader("Honeytoken Hits")

    hit_counts = (
        events["honeytoken_hit"]
        .value_counts()
        .rename(index={0: "Normal", 1: "Honeytoken"})
    )

    st.bar_chart(hit_counts)

st.divider()

st.subheader("Security Alerts")

if alerts.empty:
    st.success("No security alerts recorded.")
else:
    st.dataframe(alerts, use_container_width=True, hide_index=True)
    st.warning(f"{alerts_count} security alert(s) recorded.")

