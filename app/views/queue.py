import streamlit as st

from auth_state import current_user, require_staff
from core.audit import read_escalations, resolve_escalation


def render():
    user = current_user()
    require_staff(user)
    st.title("📥 Advisor queue")
    st.caption("Help requests raised by participants from the chatbot or their dashboard.")

    open_df = read_escalations(status="open")
    if open_df.empty:
        st.success("No open help requests. 🎉")
    for _, t in open_df.iterrows():
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**#{t['id']} · {t['requester_name']}** "
                       f"({t['student_id'] or 'no roster link'}) · via {t['channel']} · "
                       f"{t['created_at'][:16].replace('T', ' ')} UTC")
            a.write(t["message"] or "_(no message)_")
            if t["student_id"] and b.button("Open participant", key=f"p{t['id']}"):
                st.session_state.detail_student = t["student_id"]
                st.switch_page(st.session_state.pages["participant"])
            with st.form(f"resolve_{t['id']}", clear_on_submit=True, border=False):
                note = st.text_input("Resolution note", key=f"n{t['id']}")
                if st.form_submit_button("Mark resolved"):
                    if not note.strip():
                        st.error("Add a short note on what was done.")
                    else:
                        resolve_escalation(int(t["id"]), user, note.strip())
                        st.rerun()

    with st.expander("Resolved requests"):
        done = read_escalations(status="resolved")
        st.dataframe(done, use_container_width=True, hide_index=True)
