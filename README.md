# AttendSmart — Attendance-Risk Early Warning

AttendSmart predicts, halfway through a course, which participants are likely
to fall below 75% attendance in the second half, explains *why*, and gives
advisors a workflow to act on it. Participants get a private view of their
own risk and next steps.

- **Accounts & RBAC:** email/password sign-in and self-registration, with
  student, advisor and admin roles enforced server-side. Sessions persist and
  can be revoked.
- **Azure ML:** a model trained and deployed with the Azure ML SDK v2 to a
  managed online endpoint. The app scores live against it and falls back
  automatically to the local copy of the model.
- **Dialogflow ES chatbot:** a real agent, synced by API, answering through
  a secured fulfillment webhook. The webhook trusts identity only from a
  signed token, so the chatbot honours the same RBAC as the dashboard.
- **Governance:** audit trail of every prediction viewed, human-in-the-loop
  advisor decisions, help-request tickets, consent at registration, and
  synthetic-data labelling throughout.

Built for the IIT Kanpur CDAIO Smart Classroom AI Challenge (Group 9) around the real
participant roster. **All attendance, engagement and risk data is 100%
synthetic.** Only names are real.

## Architecture

```
                    ┌────────────────────── Streamlit app (app/) ───────────────────────┐
 Browser ──login──▶ │  auth (core/auth.py) ─ sessions ─ RBAC-built navigation           │
                    │  dashboards ─────────────▶ core/scoring.py ──HTTPS──▶ Azure ML      │
                    │                                  │ (fallback)          online       │
                    │                                  ▼                     endpoint     │
                    │                            ml/model.joblib        (ml/azure_score) │
                    │  assistant ─▶ chatbot/engine.py ──detectIntent + signed identity──┐ │
                    └───────────────────────────────────────────────────────────────────┼─┘
                                                                                        ▼
                                  FastAPI (api/) ◀── fulfillment webhook ── Dialogflow ES agent
                                  /dialogflow/webhook  → chatbot/fulfillment.py (same RBAC)
                                  /score               → Azure-ML-compatible scoring
                    SQLite (instance/attendsmart.db): users · sessions · audit_log · overrides · escalations
```

`ml/inference.py` is the single scoring and explanation implementation. It is
shared by the app, the webhook and the Azure ML endpoint, so none of them can
drift. `chatbot/fulfillment.py` is the single implementation of every intent,
used by both the Dialogflow webhook and the offline intent engine.

## Quick start (local, no cloud needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then set ATTENDSMART_SECRET_KEY
streamlit run app/attendsmart_app.py
```

The first run creates `instance/attendsmart.db` with an admin, an advisor and
one student account per roster participant. Student logins are the roster ID
as an email (`s001@attendsmart.demo` … `s039@attendsmart.demo`) with the shared
demo password `password123` (override with `ATTENDSMART_STUDENT_PASSWORD`).
Staff passwords come from `ATTENDSMART_DEMO_PASSWORD`, or are random and written
to `instance/demo_credentials.txt`, which is gitignored. Use a real password
for anything beyond a demo.

Reset to a clean demo at any time:

```bash
python -m core.seed --reset
```

Run the backend API (the Dialogflow webhook plus `/score`):

```bash
uvicorn api.main:app --port 8000
```

Or run both services with Docker:

```bash
docker compose up --build
```

Run the tests:

```bash
python -m pytest
```

## Going live on Azure ML and Dialogflow

Both integrations switch on from `.env`. Nothing in the code changes. See
[docs/deployment_guide.md](docs/deployment_guide.md) for the full walkthrough.

| Integration | Commands | Result |
|---|---|---|
| Azure ML | `python azure_ml/register_data.py` → `python azure_ml/train.py` → `python azure_ml/deploy_endpoint.py --write-env` → `python azure_ml/smoke_test.py` | Dashboards show "Scored live by Azure ML endpoint", with local fallback if it's unreachable |
| Dialogflow ES | `python -m chatbot.sync_dialogflow_agent --webhook-url https://<api-host>/dialogflow/webhook` | Assistant shows "Powered by Dialogflow ES" plus the matched intent and confidence |

Remember to run `python azure_ml/teardown.py` after demoing, because a managed
endpoint bills for every hour it exists.

## Project layout

```
app/                  Streamlit UI
  attendsmart_app.py    entry point: auth gate + role-based navigation
  auth_state.py         session cookie, current user, audit-once helper
  components.py         charts, badges, cached data loaders
  views/                one module per page (login, cohort, participant, queue, users, ...)
core/                 shared backend logic
  config.py             env-driven settings (.env)
  db.py                 SQLite schema
  auth.py               hashing, lockout, sessions, user admin
  audit.py              audit log, overrides, escalation tickets
  scoring.py            Azure ML client + local fallback + cache
  seed.py               DB bootstrap + demo accounts
api/main.py           FastAPI: Dialogflow webhook, /score, /health
chatbot/
  fulfillment.py        intent handlers (the one implementation, RBAC enforced here)
  engine.py             routes chat to Dialogflow or the local engine
  dialogflow_client.py  detectIntent with signed identity payload
  identity.py           HMAC-signed short-lived identity tokens
  rule_based_bot.py     offline intent matcher (Dialogflow stand-in)
  agent_spec.py         intents + training phrases (single source)
  sync_dialogflow_agent.py   push agent to Dialogflow via API
  build_dialogflow_agent.py  build importable agent zip (alternative)
azure_ml/             Azure ML SDK v2: register data, train job, deploy endpoint, smoke test, teardown
ml/
  train_model.py        training (runs locally AND as the Azure ML job)
  inference.py          scoring + explanations (shared everywhere)
  azure_score.py        managed online endpoint entry script
  model_card.md         model documentation
data/                 roster (real names) + synthetic dataset generator
tests/                pytest suite (auth, sessions, RBAC, webhook, scoring, Azure contract)
docs/                 deployment guide, demo script, CDAIO Q&A
```

## How the risk prediction works

At session 12 of 20, a logistic regression estimates the probability that a
participant falls below 75% attendance over sessions 13–20. It uses seven
features from weeks 1–6 only:

- longest absence streak
- attendance trend
- late-arrival share
- average quiz score
- assignment submission rate
- weekly LMS logins
- weekly forum posts

The training label comes from the held-out second half of the term, so the
model genuinely forecasts rather than restating data it has already seen.
Each feature's contribution is its z-score × its coefficient. These
contributions sum, with the intercept, to the model's log-odds. That is what
the "why flagged" chart shows, and a test checks the equality. Tiers are
**High** (≥ 75%), **Medium** (40–75%) and **Low** (< 40%). The model is
evaluated with leave-one-out cross-validation because there are only 39 rows.
See [ml/model_card.md](ml/model_card.md) for the details.

## Security notes

- Passwords use salted PBKDF2-SHA256 with 600k iterations. Accounts lock
  after 5 failed attempts, and login errors are generic.
- Sessions use an opaque cookie token; only its SHA-256 hash is stored. They
  expire after 30 idle minutes or 12 hours, and are revoked on sign-out,
  password change or deactivation.
- The Dialogflow webhook uses basic auth, and personal answers require an
  HMAC-signed identity token that expires in 5 minutes. Calls from the
  Dialogflow console simulator are treated as anonymous.
- The last active admin can't be demoted or deactivated.
- Set `ATTENDSMART_SECRET_KEY` before any shared deployment. The System
  status page warns while the development default is in use.

## Known limitations

- The data is synthetic and has only 39 training rows (see the Model Card),
  so treat the model as a demonstration of the pipeline, not a validated
  predictor.
- SQLite suits a single host. For multi-instance hosting, move to Azure
  Database for PostgreSQL; the schema is plain SQL.
- Streamlit can't set HttpOnly cookies, so the session cookie is readable by
  page scripts. It's `SameSite=Strict` and `Secure` over HTTPS. For a
  production system, front the app with Entra ID / App Service
  authentication.
