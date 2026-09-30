"""
AttendSmart — local intent matcher (offline stand-in for Dialogflow NLU).

Maps a free-text message to the same intent names and `student_name`
parameter that the Dialogflow ES agent produces, so chatbot/fulfillment.py
can answer identically whichever NLU matched the message. Used when
Dialogflow isn't configured or can't be reached.
"""

import re
from typing import Optional, Tuple

from core import scoring


def find_student_name(text: str) -> Tuple[Optional[str], bool]:
    """Returns (full_name, ambiguous). Full-name match wins; otherwise a unique
    first/last-name token match; several equally good matches => ambiguous."""
    text_l = text.lower()
    words = set(re.findall(r"[a-z]+", text_l))
    best, best_score, tie = None, 0, False
    for name in scoring.roster().values():
        if name.lower() in text_l:
            return name, False
        tokens = [t.lower() for t in name.split() if len(t) > 3]
        score = sum(1 for t in tokens if t in words)
        if score > best_score:
            best, best_score, tie = name, score, False
        elif score and score == best_score:
            tie = True
    if best_score == 0:
        return None, False
    return best, tie


PATTERNS = [
    ("Welcome", r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b"),
    ("Goodbye", r"\b(bye|goodbye|thanks|thank you|that.?s all)\b"),
    ("DataPrivacy", r"\b(privacy|data protection|gdpr|dpdp|consent|my data|data safe)\b"),
    ("EscalateToAdvisor", r"\b(talk to|speak (to|with)|escalate|connect me|a human|"
                          r"counsel|need help|my advisor)\b"),
    ("ListAtRiskStudents", r"(\bwho\b.*\b(at risk|flagged|need.*attention)\b)|"
                           r"(\b(list|show)\b.*\b(risk|flagged)\b)|risk roster"),
    ("ExplainModel", r"\b(how does|how do you|which model|what model|algorithm|"
                     r"how is risk calculated|prediction work)\b"),
    ("WhatShouldIDo", r"\b(what should i do|how (can|do) i improve|help me improve|"
                      r"fix (this|my)|back on track)\b"),
]


def detect_intent(message: str) -> Tuple[str, dict]:
    msg = message.strip().lower()
    for intent, pattern in PATTERNS[:3]:
        if re.search(pattern, msg):
            return intent, {}

    name, ambiguous = find_student_name(message)
    params = {"student_name": name} if name and not ambiguous else {}

    for intent, pattern in PATTERNS[3:]:
        if re.search(pattern, msg):
            return intent, params

    if re.search(r"\bwhy\b", msg) or re.search(r"\bexplain\b.*\b(risk|score|flag)", msg):
        return "WhyFlagged", params

    if name and re.search(r"\b(risk|attendance|status|flagged|doing|check)\b", msg):
        if ambiguous:
            return "Clarify", {"candidate": name}
        return "CheckStudentRisk", params

    if re.search(r"\b(my\b.*\brisk|am i at risk|am i flagged|risk score|eligib)", msg):
        return "CheckMyRisk", {}

    if re.search(r"\b(my attendance|how many (classes|sessions)|missed|attendance percent)", msg):
        return "CheckMyAttendance", {}

    return "Default Fallback Intent", {}
