"""
AttendSmart — create the database and demo accounts.

  python -m core.seed            # idempotent; only creates what's missing
  python -m core.seed --reset    # wipe the database first (fresh demo)

Creates one admin, one advisor and three student accounts (one per risk
tier, so every dashboard state can be demoed). The remaining roster
participants are left unclaimed so self-registration can be shown live.

Passwords come from ATTENDSMART_DEMO_PASSWORD if set, otherwise a random
one is generated per account. Either way they are written to
instance/demo_credentials.txt (gitignored) — never committed.
"""

import argparse
import os
import secrets

from core import auth, scoring
from core.config import settings
from core.db import init_db

CREDENTIALS_FILE = settings.db_path.parent / "demo_credentials.txt"
DEMO_DOMAIN = "attendsmart.demo"


def _email_for(name):
    parts = [p.lower() for p in name.split() if p.isalpha() and len(p) > 1]
    return f"{parts[0]}.{parts[-1]}@{DEMO_DOMAIN}" if len(parts) > 1 else f"{parts[0]}@{DEMO_DOMAIN}"


def _password():
    return os.environ.get("ATTENDSMART_DEMO_PASSWORD") or (secrets.token_urlsafe(10) + "-7")


def _pick_students_by_tier():
    preds = sorted(scoring.predict_all(), key=lambda p: -p["risk_probability"])
    picks = {}
    for p in preds:
        picks.setdefault(p["risk_tier"], p)
    return [picks[t] for t in ("High", "Medium", "Low") if t in picks]


def seed(reset=False) -> list:
    if reset and settings.db_path.exists():
        for suffix in ("", "-wal", "-shm"):
            path = settings.db_path.with_name(settings.db_path.name + suffix)
            if path.exists():
                path.unlink()
    init_db()

    existing = {u.email for u in auth.list_users()}
    accounts = [
        ("admin", f"admin@{DEMO_DOMAIN}", "AttendSmart Admin", None),
        ("advisor", f"r.menon@{DEMO_DOMAIN}", "Prof. R. Menon", None),
    ]
    claimed = auth.claimed_student_ids()
    for p in _pick_students_by_tier():
        if p["student_id"] not in claimed:
            accounts.append(("student", _email_for(p["name"]), p["name"], p["student_id"]))

    created = []
    for role, email, name, sid in accounts:
        if email in existing:
            continue
        password = _password()
        auth.create_user(email, name, password, role=role, student_id=sid)
        created.append((role, email, password, sid))

    if created:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CREDENTIALS_FILE, "a") as f:
            for role, email, password, sid in created:
                f.write(f"{role:8s} {email:40s} {password}" + (f"   ({sid})" if sid else "") + "\n")
        os.chmod(CREDENTIALS_FILE, 0o600)
    return created


def ensure_seeded():
    """Called by the app on start-up: seed only if there are no users at all."""
    init_db()
    if not auth.list_users():
        seed()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="Delete the database first")
    args = ap.parse_args()
    if args.reset and CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
    created = seed(reset=args.reset)
    print(f"Database: {settings.db_path}")
    if created:
        print(f"Created {len(created)} account(s): " + ", ".join(f"{r} {e}" for r, e, _, _ in created))
        print(f"Passwords saved to {CREDENTIALS_FILE}")
    else:
        print("All demo accounts already exist.")


if __name__ == "__main__":
    main()
