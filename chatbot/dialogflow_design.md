# AttendSmart — Dialogflow Chatbot Design

## Two personas
- **Student/participant** — checks their own attendance/risk, asks why they
  were flagged, asks what to do.
- **Faculty/advisor** — looks up any participant by name, or lists everyone
  currently at risk.

## Intents (12, incl. Welcome + Fallback)

| Intent | Sample training phrases | Entities | Fulfillment |
|---|---|---|---|
| `Welcome` | "hi", "hello", "hey" | — | Static greeting |
| `CheckMyAttendance` | "what's my attendance", "how many classes have I missed" | — | Webhook → `/predict/{student_id}` for the logged-in user |
| `CheckMyRisk` | "am I at risk", "will I lose eligibility" | — | Webhook → risk label + probability |
| `WhyFlagged` | "why am I flagged", "explain my risk score" | — | Webhook → top contributing factors |
| `WhatShouldIDo` | "what should I do", "how can I improve" | — | Webhook → advice mapped to top risk-raising factor |
| `CheckStudentRisk` | "what is @student_name's risk status", "is @student_name at risk" | `@student_name` (required, prompts if missing) | Webhook → looks up that student; **advisor-role check** |
| `ListAtRiskStudents` | "who is at risk", "show me the at-risk list" | — | Webhook → full flagged roster; **advisor-role check** |
| `ExplainModel` | "how does the prediction work", "what model do you use" | — | Static explainer, links to Model Card |
| `DataPrivacy` | "is my data safe", "is this DPDP compliant" | — | Static privacy/governance note |
| `EscalateToAdvisor` | "talk to a human", "connect me to my advisor" | — | Webhook → writes an entry to the audit log |
| `Goodbye` | "bye", "thanks" | — | Static closing |
| `Default Fallback Intent` | (auto) | — | Re-prompts with example questions |

## Entity: `@student_name`
A custom **enum entity** seeded with all 39 real roster names (plus first
name as a synonym, e.g. "Amit Kumar Sahoo" ↔ "Amit"), so advisors can ask
about any participant by first name.

## Minimum integration flow (as required by the brief)

```
USER → VIBE-CODED APP (Streamlit chat panel)
         → Dialogflow ES detectIntent (+ signed identity token)
         → webhook (api/main.py) → fulfillment.py → AZURE ML endpoint (or local fallback)
         → RESULT rendered back in the chat + on the dashboard
              ↕
       DIALOGFLOW CHATBOT (intent/entity matching, webhook fulfillment)
```

## How it's delivered
- `chatbot/agent_spec.py` is the single source for intents and training
  phrases.
- `python -m chatbot.sync_dialogflow_agent --webhook-url …` pushes the agent
  through the Dialogflow API. It covers the entity, the intents, the webhook
  and training, and is the recommended path.
- `AttendSmart_dialogflow_agent.zip` is an alternative that can be restored
  from the console.
- `chatbot/fulfillment.py` is the webhook's logic, served by
  `api/main.py` at `/dialogflow/webhook`. The same code runs behind the app's
  offline engine (`rule_based_bot.py`) when Dialogflow isn't configured.
- See `docs/deployment_guide.md` Part B for credentials, hosting the
  webhook, and how signed identity tokens carry RBAC through Dialogflow.
