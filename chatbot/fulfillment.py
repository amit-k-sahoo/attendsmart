"""
AttendSmart — chatbot fulfillment (intent handlers).

This is the ONE implementation of what each intent does. It runs:
  - behind the Dialogflow ES webhook (api/main.py), after Dialogflow's NLU
    has matched the intent and extracted @student_name; and
  - inside the app directly, after the local regex NLU in rule_based_bot.py,
    when Dialogflow isn't configured or is unreachable.

`identity` is None (anonymous) or {"user_id", "role", "name", "student_id"}
taken from the authenticated session / verified identity token. RBAC is
enforced here, not in the UI, so every channel gets the same rules.
"""

from typing import Optional

from core import scoring
from core.audit import create_escalation, get_latest_override, log_event
from core.config import settings

ADVICE_BY_FACTOR = {
    "consecutive_absences_early": "Try to break the streak of missed sessions — even joining "
                                   "partway or catching the recording helps signal engagement.",
    "attendance_trend_early": "Your attendance has been trending down — blocking the session "
                               "times on your calendar in advance tends to help.",
    "avg_quiz_score_early": "Revisit the recorded sessions or notes before the next quiz; "
                             "reach out to the faculty for a quick concept refresher.",
    "assignment_submission_rate_early": "Submit pending assignments, even late — it materially "
                                         "improves your standing and shows engagement.",
    "avg_lms_logins_early": "Log into the LMS a couple of times a week, even outside class, "
                             "to stay on top of materials and announcements.",
    "avg_forum_posts_early": "Post a question or comment on the course forum — participation "
                              "signals engagement beyond just attendance.",
    "late_arrival_pct_early": "Try joining a few minutes early to avoid being marked late.",
}

FEATURE_LABELS = {
    "consecutive_absences_early": "longest run of missed sessions",
    "attendance_trend_early": "attendance trend",
    "late_arrival_pct_early": "late arrivals",
    "avg_quiz_score_early": "average quiz score",
    "assignment_submission_rate_early": "assignment submission rate",
    "avg_lms_logins_early": "weekly LMS logins",
    "avg_forum_posts_early": "weekly forum posts",
}

EXAMPLES = ("You can ask things like \"What's my attendance risk?\", \"Why am I flagged?\", "
            "\"What should I do?\", or — as an advisor — \"Who's at risk?\" and "
            "\"How is <name> doing?\"")


def _reply(intent, text, data=None):
    return {"intent": intent, "text": text, "data": data}


def _is_staff(identity):
    return bool(identity) and identity.get("role") in ("advisor", "admin")


def _needs_login(intent):
    return _reply(intent, "Please sign in to AttendSmart so I know whose record to look up.")


def _denied(intent, what):
    return _reply("PermissionDenied",
                  f"{what} is only available to advisors and faculty. As a participant you can "
                  "ask about your own attendance, risk and next steps.")


def resolve_student(name: Optional[str]) -> Optional[str]:
    """Maps a (Dialogflow-resolved or free-text) name to a student_id."""
    if not name:
        return None
    name_l = name.strip().lower()
    for sid, full in scoring.roster().items():
        if full.lower() == name_l:
            return sid
    return None


def fulfill(intent: str, params: Optional[dict], identity: Optional[dict],
            query_text: str = "") -> dict:
    params = params or {}
    handler = HANDLERS.get(intent, _fallback)
    return handler(params, identity, query_text)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _welcome(params, identity, _q):
    who = f", {identity['name'].split()[0]}" if identity else ""
    extra = (" As an advisor you can also ask who's at risk or look anyone up by name."
             if _is_staff(identity) else "")
    return _reply("Welcome",
                  f"Hi{who}! I'm the AttendSmart assistant. I can tell you about attendance "
                  f"risk, explain why someone was flagged, or connect you to an advisor.{extra}")


def _own_student_id(identity):
    return identity.get("student_id") if identity else None


def _check_my_attendance(params, identity, _q):
    sid = _own_student_id(identity)
    if not sid:
        if _is_staff(identity):
            return _reply("CheckMyAttendance", "Your account isn't linked to a participant "
                          "record. Ask about a participant by name instead, e.g. "
                          "\"How is Suyash doing?\"")
        return _needs_login("CheckMyAttendance")
    df = scoring.get_features_df()
    row = df[df.student_id == sid].iloc[0]
    log_event(identity, "chatbot_check_own_attendance", sid, row["name"])
    return _reply("CheckMyAttendance",
                  f"Your attendance over sessions 1–12 is **{row['attendance_pct_early']*100:.0f}%**. "
                  f"Longest run of missed sessions: {int(row['consecutive_absences_early'])}. "
                  f"Late arrivals: {row['late_arrival_pct_early']*100:.0f}% of sessions.",
                  {"student_id": sid})


def _check_my_risk(params, identity, _q):
    sid = _own_student_id(identity)
    if not sid:
        return _needs_login("CheckMyRisk") if not identity else _check_my_attendance(params, identity, _q)
    r = scoring.predict_student(sid)
    level = ("at risk of falling below 75% attendance" if r["risk_label"] == 1 else "on track")
    text = (f"You're currently predicted to be **{level}** for the rest of the term "
            f"(risk probability {r['risk_probability']*100:.0f}%, tier **{r['risk_tier']}**). "
            "This is an early-warning signal to help you and your advisor — not a grade.")
    override = get_latest_override(sid)
    if override:
        text += (f"\n\nYour advisor reviewed this on {override['timestamp_utc'][:10]}: "
                 f"*{override['override_decision']}*.")
    log_event(identity, "chatbot_check_own_risk", sid, r["name"],
              f"probability={r['risk_probability']} backend={r['backend']}")
    return _reply("CheckMyRisk", text, r)


def _why_flagged(params, identity, _q):
    if not identity:
        return _needs_login("WhyFlagged")
    target = resolve_student(params.get("student_name"))
    own = _own_student_id(identity)
    if target and target != own and not _is_staff(identity):
        return _denied("WhyFlagged", "Looking at another participant's risk factors")
    sid = target or own
    if not sid:
        return _reply("WhyFlagged", "Which participant do you mean? Try \"Why is <name> flagged?\"")
    r = scoring.predict_student(sid)
    subject = "your" if sid == own else f"{r['name']}'s"
    lines = []
    for f in r["top_factors"]:
        direction = "↑ raising" if f["contribution"] > 0 else "↓ lowering"
        lines.append(f"- {FEATURE_LABELS.get(f['feature'], f['feature'])}: {direction} risk "
                     f"({f['contribution']:+.2f})")
    log_event(identity, "chatbot_explain_prediction", sid, r["name"],
              f"probability={r['risk_probability']}")
    return _reply("WhyFlagged",
                  f"Top factors behind {subject} risk score "
                  f"({r['risk_probability']*100:.0f}%):\n" + "\n".join(lines), r)


def _what_should_i_do(params, identity, _q):
    sid = _own_student_id(identity)
    if not sid:
        return _needs_login("WhatShouldIDo") if not identity else _reply(
            "WhatShouldIDo", "This one's for participants — it tailors advice to their own record.")
    r = scoring.predict_student(sid)
    risky = [f for f in r["top_factors"] if f["contribution"] > 0]
    if not risky:
        text = "You're not showing significant risk factors right now — keep it up!"
    else:
        tips = [ADVICE_BY_FACTOR[f["feature"]] for f in risky[:2] if f["feature"] in ADVICE_BY_FACTOR]
        text = "A couple of suggestions based on your record:\n- " + "\n- ".join(tips)
        text += "\n\nWant me to connect you with your advisor? Just say \"talk to an advisor\"."
    log_event(identity, "chatbot_advice", sid, r["name"])
    return _reply("WhatShouldIDo", text, r)


def _check_student(params, identity, _q):
    if not _is_staff(identity):
        return _denied("CheckStudentRisk", "Looking up another participant")
    name = params.get("student_name")
    sid = resolve_student(name)
    if not sid:
        return _reply("NotFound", f"I couldn't find a participant named {name or 'that'}.")
    r = scoring.predict_student(sid)
    level = "**AT RISK**" if r["risk_label"] == 1 else "on track"
    text = (f"{r['name']}: {level} — {r['risk_probability']*100:.0f}% risk probability "
            f"(tier {r['risk_tier']}).")
    override = get_latest_override(sid)
    if override:
        text += f" Latest advisor decision: *{override['override_decision']}*."
    log_event(identity, "chatbot_advisor_lookup", sid, r["name"],
              f"probability={r['risk_probability']}")
    return _reply("CheckStudentRisk", text, r)


def _list_at_risk(params, identity, _q):
    if not _is_staff(identity):
        return _denied("ListAtRiskStudents", "The cohort at-risk list")
    at_risk = sorted([r for r in scoring.predict_all() if r["risk_label"] == 1],
                     key=lambda r: -r["risk_probability"])
    if not at_risk:
        text = "No participants are currently flagged as at-risk."
    else:
        lines = [f"- {r['name']} ({r['risk_probability']*100:.0f}%, {r['risk_tier']})"
                 for r in at_risk]
        text = f"{len(at_risk)} participant(s) currently flagged:\n" + "\n".join(lines)
    log_event(identity, "chatbot_list_at_risk", details=f"{len(at_risk)} flagged")
    return _reply("ListAtRiskStudents", text, {"at_risk": at_risk})


def _explain_model(params, identity, _q):
    backend = "an Azure ML managed online endpoint" if settings.azureml_enabled \
        else "the local copy of the model"
    return _reply("ExplainModel",
                  "I use a logistic regression model trained on early-term signals — "
                  "attendance streaks and trend, late arrivals, quiz scores, assignment "
                  "submissions, LMS logins and forum activity — to predict whether attendance "
                  "will drop below 75% in the second half of the term. Predictions are served "
                  f"by {backend}. The Model Card page has performance numbers and limitations.")


def _data_privacy(params, identity, _q):
    return _reply("DataPrivacy",
                  "All attendance, quiz and engagement figures here are synthetic — only "
                  "participant names are real. Access is role-based: participants see only "
                  "their own record, and every prediction viewed or overridden is written to "
                  "an audit log. A production rollout would follow the DPDP Act 2023: minimal "
                  "collection, explicit consent and retention limits.")


def _escalate(params, identity, query_text):
    if not identity:
        return _needs_login("EscalateToAdvisor")
    ticket = create_escalation(identity, identity.get("student_id") or "",
                               query_text[:500], channel="chatbot")
    return _reply("EscalateToAdvisor",
                  f"Done — I've opened support ticket **#{ticket}** for your advisor. They'll "
                  "see it in their Advisor queue and follow up with you.",
                  {"ticket_id": ticket})


def _goodbye(params, identity, _q):
    return _reply("Goodbye", "You're welcome! Reach out anytime you have attendance or "
                             "engagement questions.")


def _fallback(params, identity, _q):
    return _reply("Fallback", "I didn't quite catch that. " + EXAMPLES)


HANDLERS = {
    "Welcome": _welcome,
    "Default Welcome Intent": _welcome,  # reused by sync_dialogflow_agent.py
    "CheckMyAttendance": _check_my_attendance,
    "CheckMyRisk": _check_my_risk,
    "WhyFlagged": _why_flagged,
    "WhatShouldIDo": _what_should_i_do,
    "CheckStudentRisk": _check_student,
    "ListAtRiskStudents": _list_at_risk,
    "ExplainModel": _explain_model,
    "DataPrivacy": _data_privacy,
    "EscalateToAdvisor": _escalate,
    "Goodbye": _goodbye,
    "Default Fallback Intent": _fallback,
}
