"""
AttendSmart — create the database and demo accounts.

  python -m core.seed            # idempotent; only creates what's missing
  python -m core.seed --reset    # wipe the database first (fresh demo)

Creates one admin, one advisor and one student account per roster
participant, with sample login IDs of the form s001@attendsmart.demo
(matching the roster student ID).

Staff passwords come from ATTENDSMART_DEMO_PASSWORD if set, otherwise a random
one is generated per account. Student accounts share the demo password
ATTENDSMART_STUDENT_PASSWORD (default "password123") — demo data only; change
it for anything shared beyond a demo. Credentials are written to
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


def _email_for(student_id):
    return f"{student_id.lower()}@{DEMO_DOMAIN}"


def _student_password():
    return os.environ.get("ATTENDSMART_STUDENT_PASSWORD") or "password123"


def _password():
    return os.environ.get("ATTENDSMART_DEMO_PASSWORD") or (secrets.token_urlsafe(10) + "-7")


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
    for sid, name in sorted(scoring.roster().items()):
        if sid not in claimed:
            accounts.append(("student", _email_for(sid), name, sid))

    created = []
    for role, email, name, sid in accounts:
        if email in existing:
            continue
        password = _student_password() if role == "student" else _password()
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
