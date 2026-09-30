import pandas as pd
import streamlit as st

from auth_state import audit_once, current_user, require_staff
from components import backend_badge, model_meta, risk_tier_bar, synthetic_banner
from core import scoring
from core.audit import latest_overrides_by_student, log_event, read_escalations


def predictions_frame():
    overrides = latest_overrides_by_student()
    rows = []
    for p in scoring.predict_all():
        ov = overrides.get(p["student_id"])
        rows.append({
            "Student ID": p["student_id"],
            "Name": p["name"],
            "Tier": p["risk_tier"],
            "Risk %": round(p["risk_probability"] * 100),
            "Prediction": "At risk" if p["risk_label"] == 1 else "On track",
            "Top factor": p["top_factors"][0]["feature"].replace("_early", "").replace("_", " "),
            "Advisor decision": ov["override_decision"] if ov else "—",
        })
    return pd.DataFrame(rows).sort_values("Risk %", ascending=False)


def render():
    user = current_user()
    require_staff(user)
    df = predictions_frame()
    n_at_risk = int((df["Prediction"] == "At risk").sum())
    audit_once(user, "viewed_cohort_dashboard", details=f"{n_at_risk} at risk shown")

    st.title("Cohort overview")
    st.caption(backend_badge())

    open_tickets = len(read_escalations(status="open"))
    reviewed = int((df["Advisor decision"] != "—").sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Participants", len(df))
    c2.metric("Predicted at risk", n_at_risk)
    c3.metric("Reviewed by advisor", f"{reviewed}/{n_at_risk if n_at_risk else len(df)}")
    c4.metric("Open help requests", open_tickets)
    c5.metric("Model ROC-AUC (LOO-CV)", model_meta()["loo_cv_metrics"]["roc_auc"])

    left, right = st.columns([1, 1.6])
    with left:
        st.plotly_chart(risk_tier_bar(df), use_container_width=True)
        st.caption("Tier = model risk probability: Low < 40%, Medium 40–75%, High ≥ 75%.")
    with right:
        st.markdown("#### Needs attention")
        todo = df[(df["Prediction"] == "At risk") & (df["Advisor decision"] == "—")].head(8)
        if todo.empty:
            st.success("Every at-risk participant has an advisor decision on record.")
        for _, r in todo.iterrows():
            a, b = st.columns([3, 1])
            a.markdown(f"**{r['Name']}** · {r['Risk %']}% · driven by *{r['Top factor']}*")
            if b.button("Open", key=f"open_{r['Student ID']}"):
                st.session_state.detail_student = r["Student ID"]
                st.switch_page(st.session_state.pages["participant"])

    st.markdown("### Roster")
    f1, f2 = st.columns([1, 2])
    tiers = f1.multiselect("Tier", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    query = f2.text_input("Search by name", placeholder="Type to filter…")
    view = df[df["Tier"].isin(tiers)]
    if query:
        view = view[view["Name"].str.contains(query, case=False)]
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={"Risk %": st.column_config.ProgressColumn(
            "Risk %", min_value=0, max_value=100, format="%d%%")},
    )
    if st.download_button("Export roster (CSV)", view.to_csv(index=False).encode(),
                          "attendsmart_roster.csv", "text/csv"):
        log_event(user, "exported_roster_csv", details=f"{len(view)} rows")
    synthetic_banner()
