"""
AttendSmart — Azure ML managed online endpoint entry script.

Azure ML calls init() once when the container starts and run() per request.
Deployed by azureml/deploy_endpoint.py with code_configuration pointing at
this ml/ folder, so it shares ml/inference.py with the local app.

Request  (standard Azure ML shape):
  {"input_data": {"columns": [...7 features...], "data": [[...], ...]}}
Response:
  [{"risk_probability": 0.81, "risk_label": 1, "contributions": [...]}, ...]
"""

import json
import logging
import os
from pathlib import Path

import joblib
import pandas as pd

from inference import score_frame

_model = None


def _find_model_file() -> Path:
    model_dir = Path(os.environ.get("AZUREML_MODEL_DIR", Path(__file__).parent))
    matches = sorted(model_dir.rglob("model.joblib"))
    if not matches:
        raise FileNotFoundError(f"model.joblib not found under {model_dir}")
    return matches[0]


def init():
    global _model
    path = _find_model_file()
    _model = joblib.load(path)
    logging.info("AttendSmart model loaded from %s", path)


def run(raw_data):
    try:
        body = json.loads(raw_data) if isinstance(raw_data, (str, bytes)) else raw_data
        payload = body["input_data"]
        df = pd.DataFrame(payload["data"], columns=payload["columns"])
        return score_frame(_model, df)
    except Exception as exc:  # Azure ML returns whatever run() returns as the body
        logging.exception("Scoring failed")
        return {"error": str(exc)}
