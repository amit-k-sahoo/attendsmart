"""Group assessment portal — sign in with Google, rate Groups 1–10 on five parameters (1–5)."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

st.set_page_config(page_title="Group Assessment Portal", page_icon="⭐", layout="centered")

LABELS = {1: "1 – Poor", 2: "2 – Fair", 3: "3 – Good", 4: "4 – Very good", 5: "5 – Excellent"}


def admin_emails() -> set:
    try:
        raw = st.secrets.get("admin_emails", [])
    except Exception:  # no secrets file configured
        raw = []
    if isinstance(raw, str):
        raw = raw.split(",")
    return {e.strip().lower() for e in raw if e.strip()}


def login_screen():
    st.title("Group Assessment Portal")
    st.write("Sign in with your Google account to assess Groups 1–10 on ideation, features, "
             "look and feel, governance and presentation.")
    if st.button("Sign in with Google", type="primary", icon=":material/login:"):
        st.login("google")


def rate_tab(email: str, name: str):
    done = db.rated_groups(email)
    group = st.selectbox(
        "Group to assess", db.GROUPS,
        format_func=lambda g: f"Group {g}" + (" ✓" if g in done else ""),
    )
    st.caption(f"You have completed {len(done)} of {len(db.GROUPS)} groups. "
               "Re-submitting a group replaces your earlier scores.")
    prior = db.my_scores(email, group)
    with st.form(f"rate_{group}"):
        scores = {}
        for key, label in db.PARAMETERS.items():
            scores[key] = st.select_slider(
                label, options=[1, 2, 3, 4, 5], value=prior.get(key, 3),
                format_func=LABELS.get, key=f"{group}_{key}",
            )
        if st.form_submit_button(f"Submit ratings for Group {group}", type="primary"):
            db.save_scores(email, name, group, scores)
            st.success(f"Saved your ratings for Group {group}.")
            st.rerun()


def mine_tab(email: str):
    rows = [r for r in db.all_ratings() if r[0] == email]
    if not rows:
        st.info("You haven't rated any group yet.")
        return
    df = pd.DataFrame(rows, columns=["email", "name", "group", "parameter", "score", "updated"])
    pivot = df.pivot(index="group", columns="parameter", values="score").reindex(columns=list(db.PARAMETERS))
    pivot.columns = [db.PARAMETERS[c] for c in pivot.columns]
    pivot.index = [f"Group {g}" for g in pivot.index]
    st.dataframe(pivot, width="stretch")


def results_tab(is_admin: bool):
    rows = db.all_ratings()
    if not rows:
        st.info("No ratings yet.")
        return
    df = pd.DataFrame(rows, columns=["email", "name", "group", "parameter", "score", "updated"])
    cols = list(db.PARAMETERS)
    avg = df.pivot_table(index="group", columns="parameter", values="score", aggfunc="mean") \
            .reindex(index=db.GROUPS, columns=cols)
    avg["overall"] = avg.mean(axis=1)
    avg["reviewers"] = df.groupby("group")["email"].nunique().reindex(db.GROUPS).fillna(0).astype(int)
    avg = avg.sort_values("overall", ascending=False, na_position="last")

    c1, c2 = st.columns(2)
    c1.metric("Reviewers", df["email"].nunique())
    if avg["overall"].notna().any():
        c2.metric("Top group", f"Group {avg['overall'].idxmax()}", f"{avg['overall'].max():.2f} / 5")

    st.subheader("Ranking")
    table = avg.rename(columns={**db.PARAMETERS, "overall": "Overall", "reviewers": "Reviewers"})
    table.index = [f"Group {g}" for g in table.index]
    cfg = {c: st.column_config.ProgressColumn(c, min_value=0, max_value=5, format="%.2f")
           for c in [*db.PARAMETERS.values(), "Overall"]}
    st.dataframe(table, column_config=cfg, width="stretch")
    st.subheader("Average by parameter")
    chart = avg[cols].rename(columns=db.PARAMETERS)
    chart.index = [f"Group {g}" for g in chart.index]
    st.bar_chart(chart)

    if is_admin:
        st.subheader("Admin")
        st.download_button("Download every individual rating (CSV)", df.to_csv(index=False),
                           "ratings.csv", "text/csv")


def main():
    if not st.user.get("is_logged_in", False):
        login_screen()
        return

    email = (st.user.get("email") or "").lower()
    name = st.user.get("name") or email
    with st.sidebar:
        st.write(f"Signed in as **{name}**")
        st.caption(email)
        st.button("Sign out", on_click=st.logout)

    st.title("Group Assessment Portal")
    is_admin = email in admin_emails()
    tabs = st.tabs(["Rate a group", "My ratings", "Results"])
    with tabs[0]:
        rate_tab(email, name)
    with tabs[1]:
        mine_tab(email)
    with tabs[2]:
        results_tab(is_admin)


main()
