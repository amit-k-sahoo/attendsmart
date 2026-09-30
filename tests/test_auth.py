import pytest

from conftest import PASSWORD
from core import auth, scoring
from core.db import get_conn


def test_password_hash_roundtrip():
    h = auth.hash_password("s3cret-password")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("s3cret-password", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "garbage")


def test_passwords_are_salted():
    assert auth.hash_password("same-pass-1") != auth.hash_password("same-pass-1")


@pytest.mark.parametrize("pw", ["short1!", "onlyletterslong", "1234567890123"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(auth.AuthError):
        auth.validate_password(pw)


def test_authenticate_success_updates_last_login(student):
    user = auth.authenticate("STUDENT@example.com ", PASSWORD)
    assert user.id == student.id and user.last_login_at


def test_authenticate_generic_error_for_unknown_email():
    with pytest.raises(auth.AuthError, match="Incorrect email or password"):
        auth.authenticate("nobody@example.com", PASSWORD)


def test_lockout_after_repeated_failures(student):
    for _ in range(3):  # ATTENDSMART_MAX_FAILED_LOGINS=3 in tests
        with pytest.raises(auth.AuthError):
            auth.authenticate(student.email, "wrong-password-1")
    with pytest.raises(auth.AuthError, match="locked"):
        auth.authenticate(student.email, PASSWORD)  # even the right password


def test_deactivated_user_cannot_log_in(student, admin):
    auth.set_active(student.id, False)
    with pytest.raises(auth.AuthError, match="deactivated"):
        auth.authenticate(student.email, PASSWORD)


def test_register_student_claims_roster_record_once():
    sid, name = list(scoring.roster().items())[5]
    user = auth.register_student("new@example.com", PASSWORD, sid.lower(), scoring.roster())
    assert user.student_id == sid and user.full_name == name and user.role == "student"
    with pytest.raises(auth.AuthError, match="already been claimed"):
        auth.register_student("again@example.com", PASSWORD, sid, scoring.roster())


def test_register_rejects_unknown_student_id():
    with pytest.raises(auth.AuthError, match="roster"):
        auth.register_student("x@example.com", PASSWORD, "S999", scoring.roster())


def test_duplicate_email_rejected(student):
    with pytest.raises(auth.AuthError, match="already exists"):
        auth.create_user(student.email, "Someone", PASSWORD, "advisor")


def test_cannot_remove_last_admin(admin):
    with pytest.raises(auth.AuthError, match="last active administrator"):
        auth.set_role(admin.id, "advisor")
    with pytest.raises(auth.AuthError, match="last active administrator"):
        auth.set_active(admin.id, False)


def test_staff_without_roster_link_cannot_become_student(advisor):
    with pytest.raises(auth.AuthError):
        auth.set_role(advisor.id, "student")


def test_change_and_reset_password(student):
    auth.change_password(student.id, PASSWORD, "brand-new-pass-2")
    assert auth.authenticate(student.email, "brand-new-pass-2")
    temp = auth.admin_reset_password(student.id)
    assert auth.authenticate(student.email, temp)


def test_passwords_never_stored_in_plaintext(student):
    with get_conn() as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE id=?",
                              (student.id,)).fetchone()[0]
    assert PASSWORD not in stored


def test_session_roundtrip_and_revoke(student):
    token = auth.create_session(student.id)
    assert auth.session_user(token).id == student.id
    auth.revoke_session(token)
    assert auth.session_user(token) is None
    assert auth.session_user("not-a-token") is None


def test_sessions_revoked_on_deactivate_and_password_change(student, admin):
    keep, other = auth.create_session(student.id), auth.create_session(student.id)
    auth.change_password(student.id, PASSWORD, "brand-new-pass-3", keep_token=keep)
    assert auth.session_user(keep) and auth.session_user(other) is None
    auth.set_active(student.id, False)
    assert auth.session_user(keep) is None


def test_idle_session_expires(student):
    from datetime import datetime, timedelta, timezone
    token = auth.create_session(student.id)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=auth.SESSION_IDLE_MINUTES + 1))
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET last_seen_at = ?", (stale.isoformat(),))
    assert auth.session_user(token) is None


def test_only_token_hash_is_stored(student):
    token = auth.create_session(student.id)
    with get_conn() as conn:
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert token not in stored
