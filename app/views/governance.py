import streamlit as st

from auth_state import current_user
from core.audit import read_audit_log, read_overrides_log


def render():
    user = current_user()
    st.title("🛡️ Governance & audit")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### Role-based access")
        st.markdown(
            f"You are signed in as **{user.full_name}** with role **{user.role}**.\n\n"
            "- **Student:** own attendance, risk score, explanation and help requests only.\n"
            "- **Advisor:** full roster, any participant, human-in-the-loop decisions, "
            "help-request queue.\n"
            "- **Admin:** advisor rights plus user management and system status.\n\n"
            "Rules are enforced server-side in the pages *and* in the chatbot fulfillment "
            "(the Dialogflow webhook verifies a signed identity token), not just hidden in the UI.")
        st.markdown("#### Account security")
        st.markdown("- Salted PBKDF2-SHA256 password hashing (600k iterations)\n"
                    "- Account lockout after repeated failed sign-ins\n"
                    "- 30-minute idle session timeout\n"
                    "- Consent captured at registration")
    with g2:
        st.markdown("#### Data lineage & consent")
        st.markdown("- Synthetic data is labelled on every screen.\n"
                    "- Only names are real; see `data/course_meta.json` and the Model Card.\n"
                    "- Production use would require explicit consent and DPDP Act 2023-aligned "
                    "handling: minimal collection, purpose limitation, retention limits.")
        st.markdown("#### What if the model is wrong?")
        st.markdown("Predictions are advisory only — nothing auto-penalises a participant. "
                    "Advisors record a justified decision on every flag, and participants see "
                    "that decision on their own dashboard.")

    if not user.is_staff:
        return

    st.markdown("---")
    st.markdown("### Audit log")
    audit = read_audit_log()
    if not audit.empty:
        types = sorted(audit["event_type"].unique())
        pick = st.multiselect("Event types", types, default=types)
        audit = audit[audit["event_type"].isin(pick)]
    st.dataframe(audit, use_container_width=True, hide_index=True, height=300)
    st.download_button("Export audit log (CSV)", audit.to_csv(index=False).encode(),
                       "attendsmart_audit_log.csv", "text/csv")

    st.markdown("### Advisor decisions (human overrides)")
    st.dataframe(read_overrides_log(), use_container_width=True, hide_index=True, height=220)
