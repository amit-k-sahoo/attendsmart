"""
AttendSmart — user accounts and authentication.

- Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, OWASP-recommended
  600k iterations by default), salted per user, and compared in constant
  time. The iteration count is stored in each hash so it can be raised
  later without invalidating existing accounts.
- Repeated failed logins lock the account for a cooldown period.
- Roles: student (sees only their own record), advisor (whole cohort +
  overrides), admin (advisor rights + user management).
- Students self-register by claiming their roster student ID, so each
  account is tied to exactly one participant record.
"""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import settings
from core.db import get_conn

ROLES = ("student", "advisor", "admin")
SESSION_IDLE_MINUTES = 30
SESSION_MAX_HOURS = 12
MIN_PASSWORD_LENGTH = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Raised with a user-safe message when an auth operation fails."""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    full_name: str
    role: str
    student_id: Optional[str]
    is_active: bool
    created_at: str
    last_login_at: Optional[str]

    @property
    def is_staff(self) -> bool:
        return self.role in ("advisor", "admin")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _now():
    return datetime.now(timezone.utc)


def _row_to_user(row) -> User:
    return User(
        id=row["id"], email=row["email"], full_name=row["full_name"], role=row["role"],
        student_id=row["student_id"], is_active=bool(row["is_active"]),
        created_at=row["created_at"], last_login_at=row["last_login_at"],
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str, iterations: Optional[int] = None) -> str:
    iterations = iterations or settings.password_iterations
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(dk, expected)


def validate_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.isalpha() or password.isdigit():
        raise AuthError("Password must mix letters with numbers or symbols.")


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address.")
    return email


# ---------------------------------------------------------------------------
# Account lifecycle
# ---------------------------------------------------------------------------

def create_user(email: str, full_name: str, password: str, role: str = "student",
                student_id: Optional[str] = None) -> User:
    email = _validate_email(email)
    full_name = full_name.strip()
    if not full_name:
        raise AuthError("Name is required.")
    if role not in ROLES:
        raise AuthError(f"Unknown role: {role}")
    if role == "student" and not student_id:
        raise AuthError("Student accounts must be linked to a roster student ID.")
    validate_password(password)

    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AuthError("An account with that email already exists.")
        if student_id and conn.execute(
                "SELECT 1 FROM users WHERE student_id = ?", (student_id,)).fetchone():
            raise AuthError("That student ID has already been claimed by another account.")
        cur = conn.execute(
            "INSERT INTO users (email, full_name, password_hash, role, student_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email, full_name, hash_password(password), role, student_id,
             _now().isoformat(timespec="seconds")),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_user(row)


def register_student(email: str, password: str, student_id: str, roster: dict) -> User:
    """Self-service signup: a participant claims their roster record.

    `roster` maps student_id -> full name (the source of truth for names).
    """
    if not settings.allow_self_signup:
        raise AuthError("Self-registration is disabled. Ask an administrator for an account.")
    student_id = student_id.strip().upper()
    if student_id not in roster:
        raise AuthError("That student ID isn't on the course roster.")
    return create_user(email, roster[student_id], password, role="student", student_id=student_id)


def authenticate(email: str, password: str) -> User:
    """Returns the user or raises AuthError with a deliberately generic message."""
    generic = AuthError("Incorrect email or password.")
    try:
        email = _validate_email(email)
    except AuthError:
        raise generic

    # Errors are decided inside the transaction but raised after it commits —
    # raising inside get_conn() would roll back the failed-attempt counter.
    error = None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        now = _now()
        if row is None:
            # Burn comparable time so response timing doesn't reveal which emails exist.
            verify_password(password, hash_password("timing-equalizer"))
            error = generic
        elif row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
            error = AuthError("Too many failed attempts. This account is temporarily locked — "
                              "try again later.")
        elif not verify_password(password, row["password_hash"]):
            failed = row["failed_logins"] + 1
            locked_until = None
            if failed >= settings.max_failed_logins:
                locked_until = (now + timedelta(minutes=settings.lockout_minutes)).isoformat()
                failed = 0
            conn.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                         (failed, locked_until, row["id"]))
            error = generic
        elif not row["is_active"]:
            error = AuthError("This account has been deactivated. Contact an administrator.")
        else:
            conn.execute(
                "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ? "
                "WHERE id = ?", (now.isoformat(timespec="seconds"), row["id"]))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    if error:
        raise error
    return _row_to_user(row)


def get_user(user_id: int) -> Optional[User]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def list_users() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
    return [_row_to_user(r) for r in rows]


def claimed_student_ids() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT student_id FROM users WHERE student_id IS NOT NULL").fetchall()
    return {r["student_id"] for r in rows}


def change_password(user_id: int, current_password: str, new_password: str,
                    keep_token: Optional[str] = None):
    """Changes the password and signs out every other session of this user."""
    with get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            raise AuthError("Current password is incorrect.")
        validate_password(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(new_password), user_id))
    revoke_user_sessions(user_id, keep_token)


def generate_temp_password() -> str:
    return secrets.token_urlsafe(9) + "-1"  # always satisfies validate_password


def admin_reset_password(user_id: int) -> str:
    """Sets a random temporary password and returns it (shown once to the admin)."""
    temp = generate_temp_password()
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL "
                     "WHERE id = ?", (hash_password(temp), user_id))
    revoke_user_sessions(user_id)
    return temp


def set_role(user_id: int, role: str):
    if role not in ROLES:
        raise AuthError(f"Unknown role: {role}")
    with get_conn() as conn:
        row = conn.execute("SELECT student_id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("User not found.")
        if role == "student" and not row["student_id"]:
            raise AuthError("Only accounts linked to a roster student ID can hold the student role.")
        _guard_last_admin(conn, user_id, new_role=role)
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_active(user_id: int, active: bool):
    with get_conn() as conn:
        if not active:
            _guard_last_admin(conn, user_id, deactivating=True)
        conn.execute("UPDATE users SET is_active = ?, failed_logins = 0, locked_until = NULL "
                     "WHERE id = ?", (1 if active else 0, user_id))
    if not active:
        revoke_user_sessions(user_id)


def _guard_last_admin(conn, user_id, new_role=None, deactivating=False):
    row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["role"] != "admin":
        return
    if deactivating or (new_role and new_role != "admin"):
        n_admins = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1").fetchone()[0]
        if n_admins <= 1:
            raise AuthError("You can't remove the last active administrator.")


# ---------------------------------------------------------------------------
# Persistent sessions (survive a browser refresh)
# ---------------------------------------------------------------------------
# The browser holds an opaque random token in a cookie; only its SHA-256 is
# stored, so a leaked database can't be replayed as live sessions.

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), user_id, now.isoformat(),
             (now + timedelta(hours=SESSION_MAX_HOURS)).isoformat(), now.isoformat()))
    return token


def session_user(token: Optional[str]) -> Optional[User]:
    """Returns the active user for a session token, sliding its idle window.
    Expired/idle sessions and deactivated users return None."""
    if not token:
        return None
    now = _now()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT s.id AS sid, s.expires_at, s.last_seen_at, u.* FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_token_hash(token),)).fetchone()
        if row is None:
            return None
        idle_cutoff = now - timedelta(minutes=SESSION_IDLE_MINUTES)
        if (datetime.fromisoformat(row["expires_at"]) < now
                or datetime.fromisoformat(row["last_seen_at"]) < idle_cutoff
                or not row["is_active"]):
            conn.execute("DELETE FROM sessions WHERE id = ?", (row["sid"],))
            return None
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?",
                     (now.isoformat(), row["sid"]))
    return _row_to_user(row)


def revoke_session(token: Optional[str]):
    if token:
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def revoke_user_sessions(user_id: int, keep_token: Optional[str] = None):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                     (user_id, _token_hash(keep_token) if keep_token else ""))
