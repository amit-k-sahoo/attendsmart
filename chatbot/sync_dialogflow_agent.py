"""
AttendSmart — push the agent to Dialogflow ES via the API (recommended over zip import).

Creates or updates, idempotently:
  - the @student_name entity (all roster names + first-name synonyms)
  - every intent in chatbot/agent_spec.py (webhook fulfillment enabled)
  - optionally the agent's fulfillment webhook URL + basic-auth credentials
then trains the agent.

Prereqs: an existing Dialogflow ES agent in DIALOGFLOW_PROJECT_ID, and
GOOGLE_APPLICATION_CREDENTIALS pointing at a service-account key with the
"Dialogflow API Admin" role.

Usage:
  python -m chatbot.sync_dialogflow_agent
  python -m chatbot.sync_dialogflow_agent --webhook-url https://<host>/dialogflow/webhook
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import dialogflow  # noqa: E402

from chatbot.agent_spec import INTENTS, phrase_parts  # noqa: E402
from core.config import settings  # noqa: E402
from data.roster_names import ROSTER  # noqa: E402

# Dialogflow creates this intent in every new agent; we reuse it for "Welcome"
# rather than adding a competing greeting intent.
DEFAULT_WELCOME = "Default Welcome Intent"


def sync_entity(project):
    client = dialogflow.EntityTypesClient()
    parent = f"projects/{project}/agent"
    entities = [dialogflow.EntityType.Entity(value=n, synonyms=sorted({n, n.split()[0]}))
                for n in ROSTER]
    existing = {e.display_name: e for e in client.list_entity_types(parent=parent)}
    et = dialogflow.EntityType(
        display_name="student_name",
        kind=dialogflow.EntityType.Kind.KIND_MAP,
        entities=entities,
        enable_fuzzy_extraction=True,
    )
    if "student_name" in existing:
        et.name = existing["student_name"].name
        client.update_entity_type(entity_type=et)
        print("Updated entity @student_name")
    else:
        client.create_entity_type(parent=parent, entity_type=et)
        print("Created entity @student_name")


def build_intent(spec):
    phrases = []
    for i, phrase in enumerate(spec["phrases"]):
        parts = [dialogflow.Intent.TrainingPhrase.Part(
                    text=text, entity_type=entity or "", alias=alias or "",
                    user_defined=bool(entity))
                 for text, entity, alias in phrase_parts(phrase, i)]
        phrases.append(dialogflow.Intent.TrainingPhrase(
            type_=dialogflow.Intent.TrainingPhrase.Type.EXAMPLE, parts=parts))

    params = [dialogflow.Intent.Parameter(
                display_name=p["name"], value=p["value"],
                entity_type_display_name=p["dataType"], mandatory=p["required"],
                prompts=[pr["value"] for pr in p.get("prompts", [])])
              for p in spec.get("parameters", [])]

    return dialogflow.Intent(
        display_name=spec["name"],
        training_phrases=phrases,
        parameters=params,
        messages=[dialogflow.Intent.Message(
            text=dialogflow.Intent.Message.Text(text=[spec["response"]]))],
        webhook_state=dialogflow.Intent.WebhookState.WEBHOOK_STATE_ENABLED,
        events=["WELCOME"] if spec["name"] == "Welcome" else [],
    )


def sync_intents(project):
    client = dialogflow.IntentsClient()
    parent = f"projects/{project}/agent"
    existing = {i.display_name: i for i in client.list_intents(
        request={"parent": parent, "intent_view": dialogflow.IntentView.INTENT_VIEW_FULL})}

    for spec in INTENTS:
        intent = build_intent(spec)
        target = existing.get(spec["name"])
        if spec["name"] == "Welcome" and not target and DEFAULT_WELCOME in existing:
            target = existing[DEFAULT_WELCOME]
            intent.display_name = DEFAULT_WELCOME
        if target:
            intent.name = target.name
            client.update_intent(request={"intent": intent, "language_code": "en"})
            print(f"Updated intent {intent.display_name}")
        else:
            client.create_intent(request={"parent": parent, "intent": intent,
                                          "language_code": "en"})
            print(f"Created intent {intent.display_name}")


def sync_webhook(project, url):
    client = dialogflow.FulfillmentsClient()
    ws = dialogflow.Fulfillment.GenericWebService(
        uri=url,
        username=settings.dialogflow_webhook_user,
        password=settings.dialogflow_webhook_password,
    )
    fulfillment = dialogflow.Fulfillment(
        name=f"projects/{project}/agent/fulfillment",
        display_name="AttendSmart webhook",
        enabled=True,
        generic_web_service=ws,
    )
    client.update_fulfillment(request={
        "fulfillment": fulfillment,
        "update_mask": {"paths": ["display_name", "enabled", "generic_web_service"]},
    })
    auth = "with basic auth" if settings.dialogflow_webhook_user else "WITHOUT basic auth"
    print(f"Webhook set to {url} ({auth})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--project", default=settings.dialogflow_project_id)
    ap.add_argument("--webhook-url", help="Public HTTPS URL of /dialogflow/webhook")
    ap.add_argument("--no-train", action="store_true")
    args = ap.parse_args()
    if not args.project:
        sys.exit("Set DIALOGFLOW_PROJECT_ID in .env or pass --project.")

    sync_entity(args.project)
    sync_intents(args.project)
    if args.webhook_url:
        sync_webhook(args.project, args.webhook_url)
    if not args.no_train:
        print("Training agent...")
        dialogflow.AgentsClient().train_agent(parent=f"projects/{args.project}").result(timeout=300)
        print("Agent trained.")


if __name__ == "__main__":
    main()
