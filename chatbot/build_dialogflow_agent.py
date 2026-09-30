"""
Generates an importable Dialogflow ES agent (zip) for AttendSmart:
agent.json, package.json, intents/*.json + *_usersays_en.json,
entities/student_name.json + student_name_entries_en.json.

NOTE ON ACCURACY: this follows the documented Dialogflow ES agent
export/import zip schema from memory as of this build. Dialogflow's exact
export format has changed subtly across versions before, so treat this as a
strong best-effort starting point, not a guarantee: try
"Agent Settings -> Export and Import -> Restore from zip" in the Dialogflow
ES console first. If the import errors out, docs/deployment_guide.md also
gives the same 12 intents as a plain table you can enter by hand in ~15
minutes, which will always work regardless of schema drift.

Run: python3 build_dialogflow_agent.py
Outputs: chatbot/dialogflow_agent/  and  chatbot/AttendSmart_dialogflow_agent.zip
"""

import json
import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
from roster_names import ROSTER  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent))
from chatbot.agent_spec import INTENTS, phrase_parts  # noqa: E402

OUT = Path(__file__).parent / "dialogflow_agent"
NOW_MS = int(time.time() * 1000)


def uid():
    return str(uuid.uuid4())


def make_intent(name, training_phrases, response_text, parameters=None,
                 fallback=False, webhook=True):
    intent_id = uid()
    intent = {
        "id": intent_id,
        "name": name,
        "auto": True,
        "contexts": [],
        "responses": [
            {
                "resetContexts": False,
                "affectedContexts": [],
                "parameters": parameters or [],
                "messages": [
                    {"type": 0, "lang": "en", "condition": "", "speech": [response_text]}
                ],
                "defaultResponsePlatforms": {},
                "speech": [],
            }
        ],
        "priority": 500000,
        "webhookUsed": webhook,
        "webhookForSlotFilling": False,
        "fallbackIntent": fallback,
        "events": [{"name": "WELCOME"}] if name == "Welcome" else [],
    }
    usersays = []
    for i, phrase in enumerate(training_phrases):
        data = []
        for text, entity, alias in phrase_parts(phrase, i):
            part = {"text": text, "userDefined": entity is not None}
            if entity:
                part.update({"meta": entity, "alias": alias})
            data.append(part)
        usersays.append({
            "id": uid(),
            "data": data,
            "isTemplate": False,
            "count": 0,
            "updated": NOW_MS,
        })
    return intent, usersays



def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "intents").mkdir(parents=True)
    (OUT / "entities").mkdir(parents=True)

    for spec in INTENTS:
        params = [dict(p, id=uid()) for p in spec.get("parameters", [])]
        intent, usersays = make_intent(spec["name"], spec["phrases"], spec["response"], params)
        with open(OUT / "intents" / f"{spec['name']}.json", "w") as f:
            json.dump(intent, f, indent=2)
        with open(OUT / "intents" / f"{spec['name']}_usersays_en.json", "w") as f:
            json.dump(usersays, f, indent=2)

    # Default Fallback Intent
    fallback, fallback_says = make_intent(
        "Default Fallback Intent", [],
        "I didn't quite catch that. Try asking about your attendance risk, why "
        "you were flagged, or what to do next.",
        fallback=True,
    )
    with open(OUT / "intents" / "Default Fallback Intent.json", "w") as f:
        json.dump(fallback, f, indent=2)
    with open(OUT / "intents" / "Default Fallback Intent_usersays_en.json", "w") as f:
        json.dump(fallback_says, f, indent=2)

    # student_name entity, seeded from the real roster
    entity = {
        "id": uid(),
        "name": "student_name",
        "isOverridable": True,
        "isEnum": True,
        "isRegexp": False,
        "automatedExpansion": False,
        "allowFuzzyExtraction": True,
    }
    entries = []
    for name in ROSTER:
        first = name.split()[0]
        entries.append({"value": name, "synonyms": list({name, first})})
    with open(OUT / "entities" / "student_name.json", "w") as f:
        json.dump(entity, f, indent=2)
    with open(OUT / "entities" / "student_name_entries_en.json", "w") as f:
        json.dump(entries, f, indent=2)

    # agent.json
    agent = {
        "description": "AttendSmart - Attendance Risk Assistant (IIT Kanpur CDAIO "
                        "Smart Classroom Challenge, Group 9)",
        "language": "en",
        "shortDescription": "",
        "examples": "",
        "linkToDocs": "",
        "displayName": "AttendSmart",
        "disableInteractionLogs": False,
        "disableStackdriverLogs": True,
        "defaultTimezone": "Asia/Kolkata",
        "webhook": {
            "url": "https://YOUR-API-HOST/dialogflow/webhook",
            "headers": {},
            "available": True,
            "useForDomains": False,
            "cloudFunctionsEnabled": False,
            "cloudFunctionsInitialized": False,
        },
        "isPrivate": True,
        "customClassifierMode": "use.after",
        "mlMinConfidence": 0.3,
        "supportedLanguages": [],
        "onePlatformApiVersion": "v2",
        "analyzeQueryTextSentiment": False,
        "enabledKnowledgeBaseNames": [],
        "knowledgeServiceConfidenceAdjustment": -0.4,
        "dialogflowHistoryEnabled": False,
        "predictionRequestHistoryEnabled": True,
    }
    with open(OUT / "agent.json", "w") as f:
        json.dump(agent, f, indent=2)
    with open(OUT / "package.json", "w") as f:
        json.dump({"version": "1.0.0"}, f, indent=2)

    zip_path = Path(__file__).parent / "AttendSmart_dialogflow_agent.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in OUT.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(OUT))

    print(f"Built {len(INTENTS) + 1} intents and 1 entity ({len(ROSTER)} entries).")
    print(f"Agent folder: {OUT}")
    print(f"Zip for import: {zip_path}")


if __name__ == "__main__":
    build()
