"""Session helpers: who is signed in, persistent login cookie, view-once audit logging.

Streamlit keeps st.session_state per browser connection, so a refresh would
normally sign the user out. Instead, sign-in creates a server-side session
(core.auth.create_session) and stores its opaque token in a SameSite=Strict
cookie; on a fresh connection the token is read back from the request
cookies and re-validated against the database on every run, so sign-out,
deactivation and idle timeout take effect immediately.
"""

import json

import streamlit as st

from core import auth
from core.audit import log_event

COOKIE = "attendsmart_session"


def _write_cookie(value: str, max_age: int):
    st.html(
        "<script>"
        f"document.cookie = {json.dumps(COOKIE)} + '=' + {json.dumps(value)} + "
        f"'; path=/; max-age={max_age}; SameSite=Strict' + "
        "(location.protocol === 'https:' ? '; Secure' : '');"
        "</script>",
        unsafe_allow_javascript=True,
    )


def sync_cookie():
    """Emit any pending cookie change. Call once per run, after the page renders."""
    pending = st.session_state.pop("_cookie", None)
    if pending == "clear":
        _write_cookie("", 0)
    elif pending:
        _write_cookie(pending, auth.SESSION_MAX_HOURS * 3600)


def sign_in(user):
    token = auth.create_session(user.id)
    st.session_state.clear()
    st.session_state.session_token = token
    st.session_state._cookie = token
    log_event(user, "login_success")


def sign_out(reason="logout", flash=None):
    user = current_user()
    if user:
        log_event(user, reason)
    auth.revoke_session(st.session_state.get("session_token"))
    st.session_state.clear()
    st.session_state._cookie = "clear"
    st.session_state._signed_out = True  # don't resurrect from the stale cookie this connection
    if flash:
        st.session_state.flash = flash


def current_user():
    token = st.session_state.get("session_token")
    if token is None and not st.session_state.get("_signed_out"):
        token = st.context.cookies.get(COOKIE)
        if token:
            st.session_state.session_token = token
    if not token:
        return None
    user = auth.session_user(token)
    if user is None:
        st.session_state.clear()
        st.session_state._cookie = "clear"
        st.session_state._signed_out = True
        st.session_state.flash = "Your session has ended — please sign in again."
    return user


def require_staff(user):
    if not user or not user.is_staff:
        st.error("This page is only available to advisors and administrators.")
        st.stop()


def require_admin(user):
    if not user or not user.is_admin:
        st.error("This page is only available to administrators.")
        st.stop()


def audit_once(user, event_type, subject_student_id="", subject_name="", details=""):
    """Log a view event once per session per subject (Streamlit reruns on every click)."""
    seen = st.session_state.setdefault("_audited", set())
    key = (event_type, subject_student_id)
    if key in seen:
        return
    seen.add(key)
    log_event(user, event_type, subject_student_id, subject_name, details)
