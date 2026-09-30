import streamlit as st

from auth_state import audit_once, current_user
from components import (attendance_chart, backend_badge, engagement_chart, factor_chart,
                        risk_badge, synthetic_banner)
from chatbot.fulfillment import ADVICE_BY_FACTOR
from core import scoring
from core.audit import create_escalation, get_latest_override


def render():
    user = current_user()
    pred = scoring.predict_student(user.student_id)
    if pred is None:
        st.error("Your account isn't linked to a roster record. Contact an administrator.")
        return
    audit_once(user, "viewed_own_dashboard", user.student_id, user.full_name,
               f"probability={pred['risk_probability']} backend={pred['backend']}")

    st.title(f"Welcome, {user.full_name.split()[0]}")
    st.caption(backend_badge())

    row = scoring.get_features_df().set_index("student_id").loc[user.student_id]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Risk tier", pred["risk_tier"])
    c2.metric("Risk probability", f"{pred['risk_probability']*100:.0f}%")
    c3.metric("Attendance (sessions 1–12)", f"{row['attendance_pct_early']*100:.0f}%")
    c4.metric("Avg quiz score", f"{row['avg_quiz_score_early']:.0f}")
    st.markdown(risk_badge(pred["risk_tier"]), unsafe_allow_html=True)

    override = get_latest_override(user.student_id)
    if override:
        st.info(f"Your advisor reviewed this prediction on {override['timestamp_utc'][:10]} "
                f"and recorded: **{override['override_decision']}** — “{override['reason']}”")

    left, right = st.columns(2)
    left.plotly_chart(attendance_chart(user.student_id, "you"), use_container_width=True)
    right.plotly_chart(factor_chart(pred["all_factors"], "you"), use_container_width=True)

    st.subheader("What you can do")
    risky = [f for f in pred["top_factors"] if f["contribution"] > 0]
    if risky:
        for f in risky[:3]:
            st.markdown(f"- {ADVICE_BY_FACTOR.get(f['feature'], '')}")
    else:
        st.success("No significant risk factors right now — keep it up!")

    with st.expander("Ask my advisor for help"):
        with st.form("student_escalate", clear_on_submit=True):
            msg = st.text_area("What would you like help with?", max_chars=500)
            if st.form_submit_button("Send to advisor"):
                ticket = create_escalation(
                    {"user_id": user.id, "role": user.role, "name": user.full_name},
                    user.student_id, msg.strip(), channel="dashboard")
                st.success(f"Ticket #{ticket} created — your advisor will follow up.")

    st.plotly_chart(engagement_chart(user.student_id, "you"), use_container_width=True)
    synthetic_banner()
