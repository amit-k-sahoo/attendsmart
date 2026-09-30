"""
AttendSmart — Dialogflow ES agent specification (single source of truth).

Consumed by:
  chatbot/build_dialogflow_agent.py   -> importable agent zip (console "Restore from zip")
  chatbot/sync_dialogflow_agent.py    -> pushes the same agent via the Dialogflow API
                                         (recommended: no zip-schema drift)

Training phrases use "@entity:param" markup for annotated entity slots.
Intent names must match chatbot/fulfillment.py HANDLERS.
"""

INTENTS = [
    dict(
        name="Welcome",
        phrases=["hi", "hello", "hey", "good morning", "good afternoon",
                 "hi there", "hello AttendSmart"],
        response="Hi! I'm the AttendSmart assistant. I can tell you about attendance "
                 "risk, explain why someone was flagged, or connect you to an advisor.",
    ),
    dict(
        name="CheckMyAttendance",
        phrases=["what's my attendance", "how many classes have I missed",
                 "what is my attendance percentage", "show my attendance",
                 "how am I doing on attendance", "have I missed many sessions"],
        response="Let me pull up your attendance record.",
    ),
    dict(
        name="CheckMyRisk",
        phrases=["am I at risk", "am I flagged", "what's my risk score",
                 "will I lose eligibility", "is my attendance a problem",
                 "am I in danger of falling below 75 percent",
                 "what's my attendance risk", "what is my attendance risk",
                 "what is my risk", "check my risk", "my risk level",
                 "how risky is my attendance", "am I at risk of losing eligibility",
                 "what's my risk of falling short"],
        response="Let me check your current risk prediction.",
    ),
    dict(
        name="WhyFlagged",
        phrases=["why am I flagged", "why was I flagged", "why is my risk high",
                 "what factors caused this", "why am I at risk",
                 "explain my risk score",
                 "why is @student_name:student_name flagged",
                 "why is @student_name:student_name at risk",
                 "explain @student_name:student_name's risk score"],
        response="Here's a breakdown of the top factors behind the risk score.",
        parameters=[{
            "required": False, "dataType": "@student_name",
            "name": "student_name", "value": "$student_name", "isList": False, "prompts": [],
        }],
    ),
    dict(
        name="WhatShouldIDo",
        phrases=["what should I do", "how can I improve my attendance",
                 "help me improve", "what can I do to fix this",
                 "how do I get back on track"],
        response="Here are a couple of suggestions based on your profile.",
    ),
    dict(
        name="CheckStudentRisk",
        phrases=["what is @student_name:student_name's risk status",
                 "check @student_name:student_name",
                 "how is @student_name:student_name doing",
                 "is @student_name:student_name at risk",
                 "show me @student_name:student_name's attendance"],
        response="Looking up that participant's risk status. (Advisor access required.)",
        parameters=[{
            "required": True, "dataType": "@student_name",
            "name": "student_name", "value": "$student_name",
            "isList": False,
            "prompts": [{"lang": "en", "value": "Which participant would you like to check?"}],
        }],
    ),
    dict(
        name="ListAtRiskStudents",
        phrases=["who is at risk", "show me the at risk list",
                 "which students need attention", "who's flagged",
                 "give me the risk roster", "list at-risk participants"],
        response="Here's the current at-risk list. (Advisor access required.)",
    ),
    dict(
        name="ExplainModel",
        phrases=["how does the prediction work", "what model do you use",
                 "how is risk calculated", "explain the algorithm",
                 "what data does the model use"],
        response="I use a logistic regression model trained on early-term attendance, "
                 "quiz scores, LMS logins and engagement to predict late-term risk.",
    ),
    dict(
        name="DataPrivacy",
        phrases=["is my data safe", "what data do you collect", "how is my data protected",
                 "data privacy", "is this DPDP compliant"],
        response="All figures in this demo are synthetic. In production this data would "
                 "be governed under the DPDP Act 2023 with role-based access and consent.",
    ),
    dict(
        name="EscalateToAdvisor",
        phrases=["talk to a human", "connect me to my advisor", "I need help",
                 "escalate this", "can I speak to someone", "get me a counselor"],
        response="I've logged your request to speak with an advisor.",
    ),
    dict(
        name="Goodbye",
        phrases=["bye", "goodbye", "thanks", "thank you", "that's all", "see you"],
        response="You're welcome! Reach out anytime you have attendance questions.",
    ),
]

# Example values substituted into annotated slots so Dialogflow learns the pattern.
SLOT_EXAMPLES = ["Suyash Jain", "Abhijit Wagh", "Manoj Kumar", "Kumar Kanishka"]


def phrase_parts(phrase, example_index=0):
    """Splits "is @student_name:student_name at risk" into parts:
    [("is ", None, None), ("Suyash Jain", "@student_name", "student_name"), (" at risk", None, None)]
    """
    import re
    parts, pos = [], 0
    for m in re.finditer(r"@(\w+):(\w+)", phrase):
        if m.start() > pos:
            parts.append((phrase[pos:m.start()], None, None))
        example = SLOT_EXAMPLES[example_index % len(SLOT_EXAMPLES)]
        parts.append((example, f"@{m.group(1)}", m.group(2)))
        pos = m.end()
    if pos < len(phrase):
        parts.append((phrase[pos:], None, None))
    return parts
