"""
AttendSmart — Dialogflow ES detectIntent client.

Sends the user's message to the real Dialogflow agent together with a
signed identity token (see chatbot/identity.py). Dialogflow matches the
intent, extracts @student_name, calls our webhook (api/main.py) for
fulfillment, and returns the final text here.

Auth uses Google Application Default Credentials: set
GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON key with the
"Dialogflow API Client" role (see docs/deployment_guide.md). On hosts without a filesystem for the key,
set GOOGLE_CREDENTIALS_JSON to the key's JSON contents instead.
"""

import json
import os
import uuid

from core.config import settings
from chatbot.identity import issue_token

_sessions_client = None


def _client():
    global _sessions_client
    if _sessions_client is None:
        from google.cloud import dialogflow  # imported lazily; optional dependency
        blob = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if blob:  # hosted (e.g. Streamlit Cloud): key supplied as a secret, not a file
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_info(json.loads(blob))
            _sessions_client = dialogflow.SessionsClient(credentials=creds)
        else:
            _sessions_client = dialogflow.SessionsClient()
    return _sessions_client


def new_session_id(user_id) -> str:
    return f"u{user_id}-{uuid.uuid4().hex[:12]}"


def detect_intent(text: str, session_id: str, identity: dict) -> dict:
    from google.cloud import dialogflow
    from google.protobuf import struct_pb2

    session = _client().session_path(settings.dialogflow_project_id, session_id)
    payload = struct_pb2.Struct()
    payload.update({"attendsmart_token": issue_token(identity)})

    response = _client().detect_intent(
        request={
            "session": session,
            "query_input": dialogflow.QueryInput(
                text=dialogflow.TextInput(text=text[:256],
                                          language_code=settings.dialogflow_language)),
            "query_params": dialogflow.QueryParameters(payload=payload),
        },
        timeout=15,
    )
    qr = response.query_result
    webhook_ok = response.webhook_status.code == 0 if response.webhook_status else True
    return {
        "intent": qr.intent.display_name or "Default Fallback Intent",
        "confidence": round(qr.intent_detection_confidence, 3),
        "text": qr.fulfillment_text or "Sorry, I don't have an answer for that.",
        "parameters": dict(qr.parameters) if qr.parameters else {},
        "params_complete": qr.all_required_params_present,
        "webhook_ok": webhook_ok,
        "webhook_message": response.webhook_status.message if response.webhook_status else "",
    }
