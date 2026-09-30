from pathlib import Path

import streamlit as st

from auth_state import sign_in
from components import course_meta, synthetic_banner
from core import auth, scoring
from core.audit import log_event
from core.config import settings


def render():
    meta = course_meta()
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.image(str(Path(__file__).resolve().parent.parent / "static" / "iitk_logo.png"))
        st.markdown("## AttendSmart")
        st.caption(f"Attendance-risk early warning · {meta['course_name']}")
        if msg := st.session_state.pop("flash", None):
            st.info(msg)

        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("login", border=True):
                email = st.text_input("Email", autocomplete="username")
                password = st.text_input("Password", type="password",
                                         autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary",
                                                  use_container_width=True)
            if submitted:
                try:
                    user = auth.authenticate(email, password)
                except auth.AuthError as exc:
                    log_event(None, "login_failed", details=email.strip().lower()[:80])
                    st.error(str(exc))
                else:
                    sign_in(user)
                    st.rerun()
            st.caption("Demo student logins: `s001@attendsmart.demo` … `s039@attendsmart.demo` "
                       "(the ID matches the roster student ID).")

        with tab_up:
            if not settings.allow_self_signup:
                st.info("Self-registration is disabled. Ask an administrator for an account.")
            else:
                st.write("Participants: claim your roster record with the student ID from your "
                         "enrolment email. Advisor accounts are created by an administrator.")
                with st.form("signup", border=True):
                    sid = st.text_input("Student ID", placeholder="e.g. S012")
                    email = st.text_input("Email", key="su_email", autocomplete="email")
                    pw1 = st.text_input("Password", type="password", key="su_pw1",
                                        help=f"At least {auth.MIN_PASSWORD_LENGTH} characters, "
                                             "mixing letters with numbers or symbols.",
                                        autocomplete="new-password")
                    pw2 = st.text_input("Confirm password", type="password", key="su_pw2",
                                        autocomplete="new-password")
                    consent = st.checkbox("I consent to my attendance and engagement data being "
                                          "used to generate advisory risk predictions.")
                    created = st.form_submit_button("Create account", type="primary",
                                                    use_container_width=True)
                if created:
                    if pw1 != pw2:
                        st.error("Passwords don't match.")
                    elif not consent:
                        st.error("Consent is required to use AttendSmart.")
                    else:
                        try:
                            user = auth.register_student(email, pw1, sid, scoring.roster())
                        except auth.AuthError as exc:
                            st.error(str(exc))
                        else:
                            log_event(user, "account_created",
                                      user.student_id, user.full_name, "self-signup with consent")
                            sign_in(user)
                            st.rerun()
        synthetic_banner()
