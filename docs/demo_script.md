# AttendSmart — 15-Minute Demo Script (Group 9)

## Timing
| Segment | Time |
|---|---|
| Problem, user, solution | 2 min |
| Live walkthrough: dashboard | 4 min |
| Live walkthrough: Azure ML + explainability | 3 min |
| Live walkthrough: chatbot + Dialogflow | 3 min |
| Value, deployment, key learning | 3 min |

## 1. Problem, target user, proposed solution (2 min)
"Group 9 was assigned **AttendSmart — attendance risk prediction**. Our
target user is a course advisor who wants an early warning — by the
mid-point of a term, not the end — about which participants are drifting
toward an attendance problem, so they can intervene while it's still
fixable. We built this around [X] real participants from [context], with
fully synthetic attendance/engagement data behind their names."

## 2. Accounts + dashboard walkthrough (4 min)
- Start signed out. Show the **Create account** tab: participants claim their
  roster record with a student ID and give consent. Advisors can't self-register.
- Sign in as the **advisor** (credentials in `instance/demo_credentials.txt`).
  Point out the role-based navigation, the synthetic-data labels and the
  cohort KPIs, including "Reviewed by advisor" and "Open help requests".
- Under **Needs attention**, open a High-risk participant. Show the attendance
  line crossing 75%, the factor-contribution chart and the weekly quiz scores.
- **Record a decision**, e.g. "Confirm at-risk — will reach out", with a reason.
  This is the human in the loop.
- Sign out and sign in as that **student**. They see only their own record,
  plus the advisor's decision and tailored advice. Try `/participant` in the
  URL: the page doesn't exist for them. That's RBAC enforced server-side.

## 3. Azure ML + explainability (3 min)
- Point to the badge under each page title: **"Scored live by Azure ML
  endpoint · N ms"**. As admin, the **System status** page shows the active
  backend, latency and last error.
- In ML Studio, show the training job (LOO-CV metrics logged via MLflow), the
  registered model, and the endpoint's *Test* tab.
- Explain the fallback: if the endpoint is down, the app scores locally with
  the same model and says so on screen.
- **Model card** page: the time-split design (no leakage), honest LOO-CV
  numbers, and why contributions sum exactly to the model's log-odds.

## 4. Chatbot + Dialogflow (3 min)
- **Assistant** page as the student: "Am I at risk?", "Why am I flagged?",
  "What should I do?", then "Can I talk to my advisor?". This opens a
  ticket.
- Ask "Who's at risk?" and get refused. The webhook enforces this, not
  just the UI.
- Sign in as the advisor. The ticket is in the **Advisor queue**. Resolve it.
  Ask "Who's at risk?" and "How is Suyash doing?"
- Each answer shows the matched Dialogflow intent and confidence. Switch to
  the Dialogflow console to show the intents, the `@student_name` entity and
  the webhook config.
- Close on **Governance & audit**: every view, lookup, decision and ticket
  above is in the audit log, with who did it and when.

## 5. Value, deployment considerations, key learning (3 min)
- **Value:** advisors get a weekly, explainable early-warning list instead
  of discovering attendance problems at the end of term; students get a
  private nudge and concrete suggestions before it becomes a bigger issue.
- **Deployment considerations:** summarize 2-3 points from
  `docs/cdaio_qna.md` (data needed, DPDP-aligned consent, human-in-the-loop
  by design — never automated action).
- **Key learning:** name one honest limitation (e.g., "with only 39 training
  rows, several of our model's coefficients are still unstable — we
  documented that rather than overselling accuracy, and we deliberately
  time-split features vs. label to avoid a leakage trap that's easy to fall
  into on a task like this").

## Fallback if live demo breaks
Have `/tmp` screenshots or a short screen recording of the working app as
backup, and narrate over `docs/cdaio_qna.md` + `ml/model_card.md` if live
software fails — the reasoning is the deliverable that can't crash.
