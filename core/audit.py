"""
AttendSmart — governance: audit trail, human overrides, escalations.

Every view of a prediction, chatbot risk query, login, account change and
human override is recorded here with the authenticated user who did it —
the "who saw/acted on which AI output, when, and why" trail the
Enterprise Governance brief asks for.
"""

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from core.db import get_conn


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(actor, event_type: str, subject_student_id: str = "",
              subject_name: str = "", details: str = ""):
    """`actor` is an auth.User, an identity dict from the chatbot, or None (anonymous)."""
    actor_id, role, name = _actor_fields(actor)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp_utc, actor_user_id, actor_role, actor_name, "
            "event_type, subject_student_id, subject_name, details) VALUES (?,?,?,?,?,?,?,?)",
            (_now(), actor_id, role, name, event_type, subject_student_id or "",
             subject_name or "", details or ""),
        )


def _actor_fields(actor):
    if actor is None:
        return None, "anonymous", "anonymous"
    if isinstance(actor, dict):
        return actor.get("user_id"), actor.get("role", "anonymous"), actor.get("name", "anonymous")
    return actor.id, actor.role, actor.full_name


def log_override(advisor, subject_student_id, subject_name, model_prediction,
                 model_probability, override_decision, reason):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO overrides (timestamp_utc, advisor_user_id, advisor_name, "
            "subject_student_id, subject_name, model_prediction, model_probability, "
            "override_decision, reason) VALUES (?,?,?,?,?,?,?,?,?)",
            (_now(), advisor.id, advisor.full_name, subject_student_id, subject_name,
             model_prediction, model_probability, override_decision, reason),
        )
    log_event(advisor, "human_override_recorded", subject_student_id, subject_name,
              f"{override_decision} — {reason}")


def create_escalation(requester, student_id: str, message: str, channel="chatbot") -> int:
    actor_id, _, name = _actor_fields(requester)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO escalations (created_at, requester_user_id, requester_name, student_id, "
            "message, channel) VALUES (?,?,?,?,?,?)",
            (_now(), actor_id, name, student_id or "", message or "", channel),
        )
        ticket_id = cur.lastrowid
    log_event(requester, "escalation_requested", student_id or "", name if student_id else "",
              f"ticket #{ticket_id} via {channel}")
    return ticket_id


def resolve_escalation(ticket_id: int, advisor, note: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE escalations SET status='resolved', resolved_by=?, resolved_at=?, "
            "resolution_note=? WHERE id=?",
            (advisor.full_name, _now(), note, ticket_id),
        )
    log_event(advisor, "escalation_resolved", details=f"ticket #{ticket_id}: {note}")


def _query_df(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return pd.DataFrame([dict(r) for r in rows], columns=cols)


def read_audit_log(limit: int = 1000) -> pd.DataFrame:
    return _query_df(
        "SELECT timestamp_utc, actor_role, actor_name, event_type, subject_student_id, "
        "subject_name, details FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


def read_overrides_log() -> pd.DataFrame:
    return _query_df(
        "SELECT timestamp_utc, advisor_name, subject_student_id, subject_name, "
        "model_prediction, model_probability, override_decision, reason "
        "FROM overrides ORDER BY id DESC")


def read_escalations(status: Optional[str] = None, student_id: Optional[str] = None) -> pd.DataFrame:
    sql = ("SELECT id, created_at, requester_name, student_id, message, channel, status, "
           "resolved_by, resolved_at, resolution_note FROM escalations WHERE 1=1")
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if student_id:
        sql += " AND student_id = ?"
        params.append(student_id)
    return _query_df(sql + " ORDER BY id DESC", tuple(params))


def get_latest_override(student_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM overrides WHERE subject_student_id = ? ORDER BY id DESC LIMIT 1",
            (student_id,)).fetchone()
    return dict(row) if row else None


def latest_overrides_by_student() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT o.* FROM overrides o JOIN (SELECT subject_student_id, MAX(id) AS max_id "
            "FROM overrides GROUP BY subject_student_id) m ON o.id = m.max_id").fetchall()
    return {r["subject_student_id"]: dict(r) for r in rows}
