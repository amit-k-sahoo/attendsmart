import streamlit as st

from auth_state import current_user
from core import auth
from core.audit import log_event, read_escalations


def render():
    user = current_user()
    st.title("👤 My account")
    st.markdown(f"**{user.full_name}**  \n{user.email}  \nRole: `{user.role}`"
                + (f"  \nRoster record: `{user.student_id}`" if user.student_id else ""))
    st.caption(f"Member since {user.created_at[:10]}")

    st.markdown("#### Change password")
    with st.form("change_pw", clear_on_submit=True):
        cur = st.text_input("Current password", type="password", autocomplete="current-password")
        new1 = st.text_input("New password", type="password", autocomplete="new-password")
        new2 = st.text_input("Confirm new password", type="password", autocomplete="new-password")
        if st.form_submit_button("Update password"):
            if new1 != new2:
                st.error("New passwords don't match.")
            else:
                try:
                    auth.change_password(user.id, cur, new1,
                                         keep_token=st.session_state.get("session_token"))
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    log_event(user, "password_changed")
                    st.success("Password updated. Your other sessions have been signed out.")

    if user.student_id:
        st.markdown("#### My help requests")
        mine = read_escalations(student_id=user.student_id)
        if mine.empty:
            st.caption("You haven't raised any help requests.")
        else:
            st.dataframe(mine[["id", "created_at", "channel", "message", "status",
                               "resolution_note"]], use_container_width=True, hide_index=True)
