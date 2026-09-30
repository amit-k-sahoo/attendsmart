import pandas as pd
import streamlit as st

from auth_state import current_user, require_admin
from core import auth, scoring
from core.audit import log_event


def render():
    admin = current_user()
    require_admin(admin)
    st.title("👥 User management")

    users = auth.list_users()
    roster = scoring.roster()
    claimed = auth.claimed_student_ids()
    c1, c2, c3 = st.columns(3)
    c1.metric("Accounts", len(users))
    c2.metric("Staff", sum(u.is_staff for u in users))
    c3.metric("Unclaimed roster records", len(set(roster) - claimed))

    st.dataframe(pd.DataFrame([{
        "ID": u.id, "Name": u.full_name, "Email": u.email, "Role": u.role,
        "Student ID": u.student_id or "", "Active": u.is_active,
        "Last login (UTC)": (u.last_login_at or "")[:16].replace("T", " "),
    } for u in users]), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Create staff account")
        with st.form("create_staff", clear_on_submit=True):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            role = st.selectbox("Role", ["advisor", "admin"])
            if st.form_submit_button("Create", type="primary"):
                temp = auth.generate_temp_password()
                try:
                    u = auth.create_user(email, name, temp, role=role)
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    log_event(admin, "user_created", details=f"{u.email} as {role}")
                    st.success(f"Created {u.email}. Temporary password (shown once): `{temp}`")

    with right:
        st.markdown("#### Manage an account")
        options = {u.id: f"{u.full_name} · {u.email} ({u.role})" for u in users}
        uid = st.selectbox("Account", list(options), format_func=options.get)
        target = next(u for u in users if u.id == uid)
        a, b, c = st.columns(3)
        new_role = a.selectbox("Role", auth.ROLES, index=auth.ROLES.index(target.role),
                               key=f"role_{uid}")
        if a.button("Apply role"):
            _run(admin, lambda: auth.set_role(uid, new_role), "role_changed",
                 f"{target.email}: {target.role} → {new_role}")
        label = "Deactivate" if target.is_active else "Reactivate"
        if b.button(label, disabled=target.id == admin.id):
            _run(admin, lambda: auth.set_active(uid, not target.is_active),
                 "account_deactivated" if target.is_active else "account_reactivated",
                 target.email)
        if c.button("Reset password"):
            temp = auth.admin_reset_password(uid)
            log_event(admin, "password_reset_by_admin", details=target.email)
            st.success(f"Temporary password for {target.email} (shown once): `{temp}`")


def _run(admin, action, event, details):
    try:
        action()
    except auth.AuthError as exc:
        st.error(str(exc))
        return
    log_event(admin, event, details=details)
    st.rerun()
