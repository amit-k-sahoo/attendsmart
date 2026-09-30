"""
AttendSmart — chat engine used by the app.

Routes each message to Dialogflow ES when DIALOGFLOW_PROJECT_ID is set,
falling back to the local intent matcher if Dialogflow is not configured,
unreachable, or its webhook failed. Either way the answer comes from
chatbot/fulfillment.py, so behaviour and RBAC are identical.
"""

import logging

from core.config import settings
from chatbot import fulfillment
from chatbot.rule_based_bot import detect_intent as local_detect

log = logging.getLogger(__name__)


class ChatEngine:
    def __init__(self, identity: dict):
        self.identity = identity
        self.session_id = None
        if settings.dialogflow_enabled:
            from chatbot.dialogflow_client import new_session_id
            self.session_id = new_session_id(identity.get("user_id"))

    @property
    def mode(self) -> str:
        return "dialogflow" if settings.dialogflow_enabled else "local"

    def handle(self, message: str) -> dict:
        message = message.strip()[:500]
        if settings.dialogflow_enabled:
            try:
                from chatbot.dialogflow_client import detect_intent
                df = detect_intent(message, self.session_id, self.identity)
                if df["webhook_ok"]:
                    return {"intent": df["intent"], "text": df["text"], "source": "dialogflow",
                            "confidence": df["confidence"]}
                # NLU worked but our webhook didn't answer: fulfil locally with DF's intent.
                log.warning("Dialogflow webhook failed: %s", df["webhook_message"])
                res = fulfillment.fulfill(df["intent"], df["parameters"], self.identity, message)
                return dict(res, source="dialogflow-nlu+local-fulfillment",
                            confidence=df["confidence"])
            except Exception as exc:
                log.warning("Dialogflow unavailable, using local NLU: %s", exc)
                res = self._local(message)
                res["source"] = "local (Dialogflow unreachable)"
                return res
        return self._local(message)

    def _local(self, message: str) -> dict:
        intent, params = local_detect(message)
        if intent == "Clarify":
            first = params["candidate"].split()[0]
            return {"intent": "Clarify", "source": "local", "confidence": None,
                    "text": f"More than one participant matches \"{first}\". Could you use "
                            "their full name?"}
        res = fulfillment.fulfill(intent, params, self.identity, message)
        return dict(res, source="local", confidence=None)
