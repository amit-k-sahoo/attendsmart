"""
AttendSmart — SQLite persistence.

One small database file holds user accounts, the audit trail, human
overrides and escalation tickets. SQLite keeps the project zero-setup; the
schema is plain SQL so moving to Azure Database for PostgreSQL later is a
connection-string change plus minor dialect tweaks.
"""

import sqlite3
from contextlib import contextmanager

from core.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name       TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('student', 'advisor', 'admin')),
    student_id      TEXT UNIQUE,
    is_active       INTEGER NOT NULL DEFAULT 1,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash      TEXT NOT NULL UNIQUE,
    user_id         INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc       TEXT NOT NULL,
    actor_user_id       INTEGER,
    actor_role          TEXT NOT NULL,
    actor_name          TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    subject_student_id  TEXT NOT NULL DEFAULT '',
    subject_name        TEXT NOT NULL DEFAULT '',
    details             TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (timestamp_utc);

CREATE TABLE IF NOT EXISTS overrides (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc       TEXT NOT NULL,
    advisor_user_id     INTEGER,
    advisor_name        TEXT NOT NULL,
    subject_student_id  TEXT NOT NULL,
    subject_name        TEXT NOT NULL,
    model_prediction    TEXT NOT NULL,
    model_probability   REAL,
    override_decision   TEXT NOT NULL,
    reason              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_overrides_subject ON overrides (subject_student_id);

CREATE TABLE IF NOT EXISTS escalations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL,
    requester_user_id   INTEGER,
    requester_name      TEXT NOT NULL,
    student_id          TEXT NOT NULL DEFAULT '',
    message             TEXT NOT NULL DEFAULT '',
    channel             TEXT NOT NULL DEFAULT 'chatbot',
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolved_by         TEXT,
    resolved_at         TEXT,
    resolution_note     TEXT
);
"""


def connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # Streamlit + webhook API share the file
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
