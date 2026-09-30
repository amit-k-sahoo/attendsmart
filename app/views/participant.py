import streamlit as st

from auth_state import audit_once, current_user, require_staff
from components import (attendance_chart, attendance_df, backend_badge, engagement_chart,
                        factor_chart, risk_badge, synthetic_banner)
from core import scoring
from core.audit import log_override, read_escalations, read_overrides_log

DECISIONS = [
    "Confirm at-risk — will reach out",
    "Override — not actually at risk",
    "Needs more information",
    "Intervention completed",
]


def render():
    user = current_user()
    require_staff(user)
    roster = scoring.roster()
    ids = list(roster)
    default = st.session_state.get("detail_student", ids[0])

    st.title("Participant detail")
    sid = st.selectbox("Participant", ids, index=ids.index(default) if default in ids else 0,
                       format_func=lambda s: f"{roster[s]} ({s})")
    st.session_state.detail_student = sid
    pred = scoring.predict_student(sid)
    name = pred["name"]
    audit_once(user, "viewed_individual_prediction", sid, name,
               f"probability={pred['risk_probability']} backend={pred['backend']}")
    st.caption(backend_badge())

    row = scoring.get_features_df().set_index("student_id").loc[sid]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(f"**Tier**<br>{risk_badge(pred['risk_tier'])}", unsafe_allow_html=True)
    c2.metric("Risk probability", f"{pred['risk_probability']*100:.0f}%")
    c3.metric("Attendance (1–12)", f"{row['attendance_pct_early']*100:.0f}%")
    c4.metric("Longest absence streak", int(row["consecutive_absences_early"]))
    c5.metric("City", row["city"])

    left, right = st.columns(2)
    left.plotly_chart(attendance_chart(sid, name), use_container_width=True)
    right.plotly_chart(factor_chart(pred["all_factors"], name), use_container_width=True)

    left, right = st.columns([1.2, 1])
    with left:
        st.plotly_chart(engagement_chart(sid, name), use_container_width=True)
    with right:
        st.markdown("#### Record advisor decision")
        with st.form("override_form", clear_on_submit=True):
            st.write(f"Model says **{'At risk' if pred['risk_label'] else 'On track'}** "
                     f"({pred['risk_probability']*100:.0f}%).")
            decision = st.selectbox("Decision", DECISIONS)
            reason = st.text_area("Reason (required for the audit trail)", max_chars=500)
            if st.form_submit_button("Record decision", type="primary"):
                if not reason.strip():
                    st.error("A reason is required — decisions must be justified.")
                else:
                    log_override(user, sid, name,
                                 "At risk" if pred["risk_label"] else "On track",
                                 pred["risk_probability"], decision, reason.strip())
                    st.toast(f"Recorded: {decision}")
                    st.rerun()

    st.markdown("#### Decision history")
    hist = read_overrides_log()
    hist = hist[hist.subject_student_id == sid] if not hist.empty else hist
    if hist.empty:
        st.caption("No advisor decisions recorded yet.")
    else:
        st.dataframe(hist[["timestamp_utc", "advisor_name", "model_prediction",
                           "override_decision", "reason"]],
                     use_container_width=True, hide_index=True)

    tickets = read_escalations(student_id=sid)
    if not tickets.empty:
        st.markdown("#### Help requests")
        st.dataframe(tickets[["id", "created_at", "status", "message", "resolution_note"]],
                     use_container_width=True, hide_index=True)

    with st.expander("Session-by-session attendance"):
        att = attendance_df()
        st.dataframe(att[att.student_id == sid][["session_index", "week_number", "status",
                                                 "check_in_delay_min"]],
                     use_container_width=True, hide_index=True)
    synthetic_banner()
