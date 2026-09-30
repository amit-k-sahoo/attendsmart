"""Shared UI pieces: charts, badges, data loaders."""

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import scoring
from core.config import ROOT, settings

# --- dataviz palette (status colours + one sequential hue) -------------------
STATUS = {"Low": "#0ca30c", "Medium": "#d98e04", "High": "#d03b3b", "Unknown": "#898781"}
SEQ_BLUE = "#2a78d6"
DIVERGE_POS = "#d03b3b"   # risk-raising factor
DIVERGE_NEG = "#0ca30c"   # risk-lowering factor
MUTED = "#898781"

FEATURE_LABELS = {
    "consecutive_absences_early": "Longest absence streak",
    "attendance_trend_early": "Attendance trend",
    "late_arrival_pct_early": "Late arrivals",
    "avg_quiz_score_early": "Avg quiz score",
    "assignment_submission_rate_early": "Assignment submission rate",
    "avg_lms_logins_early": "Weekly LMS logins",
    "avg_forum_posts_early": "Weekly forum posts",
}


@st.cache_data
def course_meta():
    return json.loads((ROOT / "data" / "course_meta.json").read_text())


@st.cache_data
def model_meta():
    return json.loads((ROOT / "ml" / "model_metadata.json").read_text())


@st.cache_data
def attendance_df():
    return pd.read_csv(ROOT / "data" / "attendance.csv")


@st.cache_data
def engagement_df():
    return pd.read_csv(ROOT / "data" / "engagement_weekly.csv")


def _layout(fig, title, height=320):
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, margin=dict(l=10, r=10, t=48, b=10), showlegend=False,
    )
    fig.update_xaxes(gridcolor="rgba(137,135,129,0.25)", zerolinecolor=MUTED)
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)")
    return fig


def risk_badge(tier):
    color = STATUS.get(tier, STATUS["Unknown"])
    return (f"<span style='background:{color}22;color:{color};border:1px solid {color}66;"
            f"padding:2px 10px;border-radius:12px;font-weight:600;font-size:0.85em'>{tier}</span>")


def backend_badge():
    if scoring.status.backend == "azureml":
        latency = f" · {scoring.status.last_latency_ms:.0f} ms" if scoring.status.last_latency_ms else ""
        return f"☁️ Scored live by **Azure ML endpoint**{latency}"
    if settings.azureml_enabled:
        return "⚠️ Azure ML endpoint unreachable — showing **local model** fallback"
    return "💻 Scored by the **local model** (Azure ML endpoint not configured)"


def possessive(name):
    return "Your" if name == "you" else f"{name}'s"


def factor_chart(factors, name):
    factors = sorted(factors, key=lambda f: f["contribution"])
    labels = [FEATURE_LABELS.get(f["feature"], f["feature"]) for f in factors]
    values = [f["contribution"] for f in factors]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=[DIVERGE_POS if v > 0 else DIVERGE_NEG for v in values],
        customdata=[f["value"] for f in factors],
        hovertemplate="%{y}<br>value %{customdata}<br>contribution %{x:+.2f}<extra></extra>",
    ))
    fig.update_xaxes(title="← lowers risk · raises risk →")
    return _layout(fig, f"What's driving {possessive(name).lower() if name == 'you' else possessive(name)} risk score")


def attendance_chart(student_id, name):
    att = attendance_df()
    sub = att[att.student_id == student_id].sort_values("session_index").copy()
    sub["present_like"] = sub["status"].isin(["Present", "Late"]).astype(int)
    sub["rolling_pct"] = sub["present_like"].expanding().mean() * 100
    fig = go.Figure(go.Scatter(
        x=sub["session_index"], y=sub["rolling_pct"], mode="lines+markers",
        line=dict(color=SEQ_BLUE, width=2), marker=dict(size=7),
        hovertemplate="Session %{x}: %{y:.0f}% cumulative attendance<extra></extra>",
    ))
    fig.add_hline(y=75, line_dash="dash", line_color=STATUS["High"],
                  annotation_text="75% threshold", annotation_position="bottom right")
    fig.add_vline(x=12.5, line_dash="dot", line_color=MUTED,
                  annotation_text="prediction point", annotation_position="top")
    fig.update_xaxes(title="Session")
    fig.update_yaxes(title="Cumulative attendance %", range=[0, 105])
    return _layout(fig, f"{possessive(name)} attendance over the term")


def engagement_chart(student_id, name):
    eng = engagement_df()
    sub = eng[eng.student_id == student_id].sort_values("week_number")
    fig = go.Figure(go.Bar(
        x=sub["week_number"], y=sub["quiz_score"], marker_color=SEQ_BLUE,
        hovertemplate="Week %{x}: quiz %{y:.0f}<extra></extra>",
    ))
    fig.update_xaxes(title="Week", dtick=1)
    fig.update_yaxes(title="Quiz score", range=[0, 100])
    return _layout(fig, f"{possessive(name)} weekly quiz scores", height=280)


def risk_tier_bar(df):
    counts = df["Tier"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
    fig = go.Figure(go.Bar(
        x=counts.index, y=counts.values, marker_color=[STATUS[t] for t in counts.index],
        text=counts.values.astype(int), textposition="outside",
        hovertemplate="%{x}: %{y} participants<extra></extra>",
    ))
    fig.update_yaxes(title="Participants")
    return _layout(fig, "Cohort risk tiers", height=300)


def synthetic_banner():
    st.caption("⚠️ **Synthetic demo data.** Only participant names are real — all attendance, "
               "quiz, engagement and risk figures are generated for this prototype.")
