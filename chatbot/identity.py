"""
AttendSmart — signed chatbot identity tokens.

Dialogflow sits between the app and our fulfillment webhook, so the webhook
can't see the Streamlit session. Instead, the app attaches a short-lived,
HMAC-signed identity token to every detectIntent call
(QueryParameters.payload), Dialogflow forwards it untouched in
originalDetectIntentRequest.payload, and the webhook verifies it before
answering anything personal. Without a valid token the webhook treats the
caller as anonymous (e.g. the Dialogflow console simulator), so RBAC can't
be bypassed by talking to the agent directly.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from core.config import settings

TOKEN_TTL_S = 300


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())


def identity_from_user(user) -> dict:
    return {"user_id": user.id, "role": user.role, "name": user.full_name,
            "student_id": user.student_id}


def issue_token(identity: dict, ttl_s: int = TOKEN_TTL_S) -> str:
    claims = dict(identity, exp=int(time.time()) + ttl_s)
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


def verify_token(token: Optional[str]) -> Optional[dict]:
    """Returns the identity dict, or None if the token is missing/forged/expired."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        claims = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if claims.get("exp", 0) < time.time():
        return None
    claims.pop("exp", None)
    return claims
