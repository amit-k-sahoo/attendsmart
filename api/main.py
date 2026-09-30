"""
AttendSmart — backend API (Dialogflow webhook + scoring).

Routes:
  GET  /health                 liveness + which integrations are active
  POST /dialogflow/webhook     Dialogflow ES fulfillment webhook
  POST /score                  Azure-ML-compatible scoring (feature rows in, risk out)

Run locally:   uvicorn api.main:app --port 8000
Expose for Dialogflow during development:  ngrok http 8000  (or deploy the
Docker image — see docs/deployment_guide.md).
"""

import logging
import secrets
from contextlib import asynccontextmanager
from typing import List, Optional

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from chatbot import fulfillment
from chatbot.identity import verify_token
from core import scoring
from core.config import settings
from core.db import init_db
from ml.inference import FEATURES

log = logging.getLogger("attendsmart.api")
basic = HTTPBasic(auto_error=False)


@asynccontextmanager
async def lifespan(_app):
    init_db()
    if not (settings.dialogflow_webhook_user and settings.dialogflow_webhook_password):
        log.warning("Dialogflow webhook basic auth is not configured "
                    "(DIALOGFLOW_WEBHOOK_USER / DIALOGFLOW_WEBHOOK_PASSWORD).")
    yield


app = FastAPI(title="AttendSmart API", version="2.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "scoring_backend": "azureml" if settings.azureml_enabled else "local",
        "dialogflow_project": settings.dialogflow_project_id or None,
        "model_features": FEATURES,
    }


# ---------------------------------------------------------------------------
# Dialogflow ES webhook
# ---------------------------------------------------------------------------

def _check_webhook_auth(creds: Optional[HTTPBasicCredentials] = Depends(basic)):
    user, pwd = settings.dialogflow_webhook_user, settings.dialogflow_webhook_password
    if not (user and pwd):
        return  # auth not configured (local dev) — personal data still needs a signed token
    ok = creds is not None and \
        secrets.compare_digest(creds.username, user) and \
        secrets.compare_digest(creds.password, pwd)
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook credentials",
                            headers={"WWW-Authenticate": "Basic"})


@app.post("/dialogflow/webhook", dependencies=[Depends(_check_webhook_auth)])
async def dialogflow_webhook(request: Request):
    body = await request.json()
    qr = body.get("queryResult", {})
    intent = qr.get("intent", {}).get("displayName", "Default Fallback Intent")
    params = qr.get("parameters", {}) or {}
    payload = (body.get("originalDetectIntentRequest") or {}).get("payload") or {}
    identity = verify_token(payload.get("attendsmart_token"))

    try:
        result = fulfillment.fulfill(intent, params, identity, qr.get("queryText", ""))
        text = result["text"]
    except Exception:
        log.exception("Fulfillment failed for intent %s", intent)
        text = "Sorry — something went wrong on our side. Please try again in a moment."

    return {"fulfillmentText": text,
            "fulfillmentMessages": [{"text": {"text": [text]}}],
            "source": "attendsmart"}


# ---------------------------------------------------------------------------
# Scoring (same contract as the Azure ML endpoint; no PII in or out)
# ---------------------------------------------------------------------------

class AzureMLInputData(BaseModel):
    columns: List[str]
    data: List[List[float]]


class AzureMLScoreRequest(BaseModel):
    input_data: AzureMLInputData


def _check_api_key(x_api_key: Optional[str] = Header(default=None)):
    key = settings.api_key
    if key and not (x_api_key and secrets.compare_digest(x_api_key, key)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid X-API-Key")


@app.post("/score", dependencies=[Depends(_check_api_key)])
def score(req: AzureMLScoreRequest):
    df = pd.DataFrame(req.input_data.data, columns=req.input_data.columns)
    try:
        return scoring.score_rows(df)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
