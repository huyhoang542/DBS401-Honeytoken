"""Local persistent feature and prediction history for Demo B gateway traffic."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "results" / "behavior_events.sqlite3"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS behavior_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_time_utc TEXT NOT NULL,
        username TEXT NOT NULL,
        query_type TEXT NOT NULL,
        result_count INTEGER NOT NULL,
        hour INTEGER NOT NULL,
        target_table_count INTEGER NOT NULL,
        query_frequency INTEGER NOT NULL,
        query_duration_ms REAL NOT NULL,
        is_department_query INTEGER NOT NULL,
        department_no TEXT,
        risk_score REAL NOT NULL,
        predicted_label TEXT NOT NULL,
        honeytoken_hit INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_behavior_user_time ON behavior_events(username,event_time_utc)")
    columns = {row[1] for row in db.execute("PRAGMA table_info(behavior_events)")}
    if "department_no" not in columns:
        db.execute("ALTER TABLE behavior_events ADD COLUMN department_no TEXT")
    return db


def recent_frequency(username, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=1)).isoformat()
    with connect() as db:
        row = db.execute("SELECT COUNT(*) FROM behavior_events WHERE username=? AND event_time_utc>=?",
                         (username, cutoff)).fetchone()
    return int(row[0]) + 1


def save_event(username, query_type, features, score, label, honeytoken_hit, department_no=None, now=None):
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    with connect() as db:
        db.execute("""INSERT INTO behavior_events
            (event_time_utc,username,query_type,result_count,hour,target_table_count,
             query_frequency,query_duration_ms,is_department_query,department_no,risk_score,predicted_label,honeytoken_hit)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (timestamp, username, query_type, int(features["result_count"]), int(features["hour"]),
             int(features["target_table_count"]), int(features["query_frequency"]),
             float(features["query_duration_ms"]), int(features["is_department_query"]), department_no,
             float(score), label, int(bool(honeytoken_hit))))


def latest_events(limit=100):
    with connect() as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM behavior_events ORDER BY event_id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]
