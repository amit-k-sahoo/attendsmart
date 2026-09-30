import time

import streamlit as st

from auth_state import current_user, require_admin
from core import scoring
from core.audit import log_event
from core.config import settings


def render():
    user = current_user()
    require_admin(user)
    st.title("⚙️ System status")

    if settings.secret_key.startswith("dev-only"):
        st.warning("`ATTENDSMART_SECRET_KEY` is using the development default. Set a random "
                   "value in `.env` before deploying (it signs chatbot identity tokens).")

    st.markdown("#### Azure ML scoring")
    if settings.azureml_enabled:
        st.write(f"Endpoint: `{settings.azureml_endpoint_url}`")
        if settings.azureml_deployment:
            st.write(f"Pinned deployment: `{settings.azureml_deployment}`")
    else:
        st.info("Not configured — using the local model. Run the scripts in `azure_ml/` "
                "(see docs/deployment_guide.md) to deploy a managed online endpoint.")
    s = scoring.status
    c1, c2, c3 = st.columns(3)
    c1.metric("Active backend", s.backend)
    c2.metric("Last latency", f"{s.last_latency_ms:.0f} ms" if s.last_latency_ms else "—")
    c3.metric("Last scored", time.strftime("%H:%M:%S", time.localtime(s.scored_at)))
    if s.last_error:
        st.error(f"Last Azure ML error: {s.last_error}")
    if st.button("Re-score cohort now"):
        scoring.clear_cache()
        scoring.predict_all()
        log_event(user, "manual_rescore", details=f"backend={scoring.status.backend}")
        st.rerun()

    st.markdown("#### Dialogflow ES")
    if settings.dialogflow_enabled:
        st.write(f"Project: `{settings.dialogflow_project_id}` · language "
                 f"`{settings.dialogflow_language}`")
        auth_ok = settings.dialogflow_webhook_user and settings.dialogflow_webhook_password
        (st.success if auth_ok else st.warning)(
            "Webhook basic auth " + ("configured." if auth_ok else "NOT configured."))
    else:
        st.info("Not configured — the assistant uses the local intent engine. Set "
                "`DIALOGFLOW_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS`.")

    st.markdown("#### Storage")
    st.write(f"Database: `{settings.db_path}`")
    st.write(f"Self-registration: {'enabled' if settings.allow_self_signup else 'disabled'}")
