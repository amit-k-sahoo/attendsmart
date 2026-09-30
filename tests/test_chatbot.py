import time

import pytest

from chatbot import fulfillment, identity
from chatbot.engine import ChatEngine
from chatbot.identity import identity_from_user
from chatbot.rule_based_bot import detect_intent
from core import scoring
from core.audit import read_audit_log, read_escalations


@pytest.mark.parametrize("text,intent", [
    ("hi there", "Welcome"),
    ("what's my attendance risk?", "CheckMyRisk"),
    ("how many sessions have I missed", "CheckMyAttendance"),
    ("why am I flagged", "WhyFlagged"),
    ("what should I do", "WhatShouldIDo"),
    ("who's at risk?", "ListAtRiskStudents"),
    ("how does the prediction work", "ExplainModel"),
    ("is my data safe", "DataPrivacy"),
    ("talk to my advisor", "EscalateToAdvisor"),
    ("asdf qwerty", "Default Fallback Intent"),
])
def test_local_intent_detection(text, intent):
    assert detect_intent(text)[0] == intent


def test_name_lookup_extracts_student_param():
    intent, params = detect_intent("How is Suyash Jain doing?")
    assert intent == "CheckStudentRisk" and params["student_name"] == "Suyash Jain"


def test_student_sees_own_risk(student):
    res = ChatEngine(identity_from_user(student)).handle("am I at risk?")
    assert res["intent"] == "CheckMyRisk" and "%" in res["text"]
    assert "chatbot_check_own_risk" in set(read_audit_log()["event_type"])


def test_student_cannot_list_cohort(student):
    res = ChatEngine(identity_from_user(student)).handle("who is at risk?")
    assert res["intent"] == "PermissionDenied"


def test_student_cannot_look_up_other_student(student, other_student):
    other_name = other_student.full_name
    res = fulfillment.fulfill("CheckStudentRisk", {"student_name": other_name},
                              identity_from_user(student))
    assert res["intent"] == "PermissionDenied"
    res = fulfillment.fulfill("WhyFlagged", {"student_name": other_name},
                              identity_from_user(student))
    assert res["intent"] == "PermissionDenied"


def test_advisor_can_list_and_look_up(advisor):
    ident = identity_from_user(advisor)
    listed = fulfillment.fulfill("ListAtRiskStudents", {}, ident)
    assert listed["intent"] == "ListAtRiskStudents"
    name = scoring.predict_all()[0]["name"]
    looked = fulfillment.fulfill("CheckStudentRisk", {"student_name": name}, ident)
    assert looked["intent"] == "CheckStudentRisk" and name in looked["text"]


def test_anonymous_gets_no_personal_data():
    for intent in ("CheckMyRisk", "WhyFlagged", "EscalateToAdvisor"):
        assert "sign in" in fulfillment.fulfill(intent, {}, None)["text"].lower()
    assert fulfillment.fulfill("ListAtRiskStudents", {}, None)["intent"] == "PermissionDenied"


def test_escalation_creates_ticket(student):
    res = ChatEngine(identity_from_user(student)).handle("I need help, can I speak to someone")
    assert res["intent"] == "EscalateToAdvisor"
    tickets = read_escalations(status="open")
    assert len(tickets) == 1 and tickets.iloc[0]["student_id"] == student.student_id


def test_identity_token_roundtrip_and_tamper(student):
    ident = identity_from_user(student)
    token = identity.issue_token(ident)
    assert identity.verify_token(token) == ident
    body, sig = token.rsplit(".", 1)
    forged = identity._b64(b'{"user_id":1,"role":"admin","name":"x","student_id":null,'
                           b'"exp":9999999999}') + "." + sig
    assert identity.verify_token(forged) is None
    assert identity.verify_token(None) is None


def test_identity_token_expires(student):
    token = identity.issue_token(identity_from_user(student), ttl_s=-1)
    assert identity.verify_token(token) is None
