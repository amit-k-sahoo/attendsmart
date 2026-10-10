"""SQLite storage for ratings. One row per (reviewer, group, parameter); re-rating overwrites."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("REVIEW_PORTAL_DB", Path(__file__).resolve().parent.parent / "instance" / "review_portal.db"))

PARAMETERS = {
    "ideation": "Ideation",
    "features": "Features",
    "look_feel": "Look and feel",
    "governance": "Governance",
    "presentation": "Presentation",
}
GROUPS = list(range(1, 11))


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS ratings (
                   reviewer_email TEXT NOT NULL,
                   reviewer_name  TEXT,
                   group_no       INTEGER NOT NULL CHECK (group_no BETWEEN 1 AND 10),
                   parameter      TEXT NOT NULL,
                   score          INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                   updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                   PRIMARY KEY (reviewer_email, group_no, parameter))"""
        )
        yield c
        c.commit()
    finally:
        c.close()


def my_scores(email: str, group_no: int) -> dict:
    with conn() as c:
        rows = c.execute(
            "SELECT parameter, score FROM ratings WHERE reviewer_email=? AND group_no=?",
            (email, group_no),
        ).fetchall()
    return dict(rows)


def save_scores(email: str, name: str, group_no: int, scores: dict) -> None:
    with conn() as c:
        for param, score in scores.items():
            if param not in PARAMETERS or not 1 <= int(score) <= 5:
                raise ValueError("invalid rating")
            c.execute(
                """INSERT INTO ratings (reviewer_email, reviewer_name, group_no, parameter, score)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(reviewer_email, group_no, parameter)
                   DO UPDATE SET score=excluded.score, reviewer_name=excluded.reviewer_name,
                                 updated_at=CURRENT_TIMESTAMP""",
                (email, name, group_no, param, int(score)),
            )


def rated_groups(email: str) -> set:
    with conn() as c:
        rows = c.execute(
            "SELECT group_no FROM ratings WHERE reviewer_email=? GROUP BY group_no HAVING COUNT(*)=?",
            (email, len(PARAMETERS)),
        ).fetchall()
    return {r[0] for r in rows}


def all_ratings():
    with conn() as c:
        return c.execute(
            "SELECT reviewer_email, reviewer_name, group_no, parameter, score, updated_at FROM ratings"
        ).fetchall()
