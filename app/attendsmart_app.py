"""
AttendSmart — Streamlit application entry point.

    streamlit run app/attendsmart_app.py

Unauthenticated visitors see only the sign-in / registration page. After
sign-in, the navigation is built from the user's role:
  student  -> My dashboard, Assistant, Governance, Model card, My account
  advisor  -> Cohort, Participant detail, Advisor queue, Assistant, Governance, ...
  admin    -> advisor pages + User management, System status
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from auth_state import current_user, sign_out, sync_cookie  # noqa: E402
from components import course_meta  # noqa: E402
from core.config import settings  # noqa: E402
from core.seed import ensure_seeded  # noqa: E402
from views import (account, assistant, cohort, governance, login, model_card,  # noqa: E402
                   participant, queue, student_home, system, users)

STATIC = Path(__file__).resolve().parent / "static"

st.set_page_config(page_title="AttendSmart · IIT Kanpur",
                   page_icon=str(STATIC / "iitk_emblem.png"), layout="wide")
st.logo(str(STATIC / "iitk_logo.png"), icon_image=str(STATIC / "iitk_emblem.png"), size="large")


@st.cache_resource
def _bootstrap():
    ensure_seeded()  # creates the DB + demo accounts on the very first run
    return True


_bootstrap()
user = current_user()
sync_cookie()  # persist / clear the login cookie set by sign-in or sign-out

if user is None:
    nav = st.navigation([st.Page(login.render, title="Sign in", icon="🔐", url_path="login")],
                        position="hidden")
    nav.run()
    st.stop()

pages = {
    "participant": st.Page(participant.render, title="Participant detail", icon="🔎",
                           url_path="participant"),
}
common = [
    st.Page(assistant.render, title="Assistant", icon="💬", url_path="assistant"),
    st.Page(governance.render, title="Governance & audit", icon="🛡️", url_path="governance"),
    st.Page(model_card.render, title="Model card", icon="📄", url_path="model-card"),
    st.Page(account.render, title="My account", icon="👤", url_path="account"),
]
if user.is_staff:
    sections = {
        "Advising": [
            st.Page(cohort.render, title="Cohort overview", icon="📊", url_path="cohort",
                    default=True),
            pages["participant"],
            st.Page(queue.render, title="Advisor queue", icon="📥", url_path="queue"),
        ],
        "General": common,
    }
    if user.is_admin:
        sections["Administration"] = [
            st.Page(users.render, title="User management", icon="👥", url_path="users"),
            st.Page(system.render, title="System status", icon="⚙️", url_path="system"),
        ]
else:
    sections = {"": [st.Page(student_home.render, title="My dashboard", icon="📊",
                             url_path="home", default=True)] + common}
st.session_state.pages = pages

with st.sidebar:
    st.markdown("### AttendSmart")
    st.caption(course_meta()["course_name"])
    st.markdown(f"**{user.full_name}**  \n`{user.role}`"
                + (f" · {user.student_id}" if user.student_id else ""))
    if st.button("Sign out", use_container_width=True):
        sign_out()
        st.rerun()
    st.markdown("---")
    st.caption(("☁️ Azure ML endpoint" if settings.azureml_enabled else "💻 Local model")
               + " · "
               + ("🤖 Dialogflow ES" if settings.dialogflow_enabled else "🤖 Local NLU"))

st.navigation(sections).run()
