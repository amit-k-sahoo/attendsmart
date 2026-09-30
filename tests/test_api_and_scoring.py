import json
import os
import sys

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from chatbot.identity import identity_from_user, issue_token
from core import scoring
from core.config import ROOT
from ml.inference import FEATURES, sample_payload, score_frame

client = TestClient(app)


def _df_request(intent, params=None, token=None, text="test"):
    body = {"queryResult": {"queryText": text, "parameters": params or {},
                            "intent": {"displayName": intent}}}
    if token:
        body["originalDetectIntentRequest"] = {"payload": {"attendsmart_token": token}}
    return body


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["scoring_backend"] == "local"


def test_webhook_answers_with_valid_identity(advisor):
    token = issue_token(identity_from_user(advisor))
    r = client.post("/dialogflow/webhook", json=_df_request("ListAtRiskStudents", token=token))
    assert r.status_code == 200
    assert "flagged" in r.json()["fulfillmentText"]


def test_webhook_without_token_is_anonymous():
    r = client.post("/dialogflow/webhook", json=_df_request("ListAtRiskStudents"))
    assert "only available to advisors" in r.json()["fulfillmentText"]


def test_webhook_basic_auth(monkeypatch, advisor):
    from core import config
    monkeypatch.setattr("api.main.settings", config.Settings(**{
        **config.settings.__dict__,
        "dialogflow_webhook_user": "df", "dialogflow_webhook_password": "pw"}))
    assert client.post("/dialogflow/webhook", json=_df_request("Welcome")).status_code == 401
    ok = client.post("/dialogflow/webhook", json=_df_request("Welcome"), auth=("df", "pw"))
    assert ok.status_code == 200


def test_score_route_matches_azure_contract():
    df = scoring.get_features_df()
    r = client.post("/score", json=sample_payload(df, 3))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3 and {"risk_probability", "risk_label", "contributions"} <= rows[0].keys()


def test_score_rejects_missing_columns():
    r = client.post("/score", json={"input_data": {"columns": ["x"], "data": [[1.0]]}})
    assert r.status_code == 400


def test_contributions_reconstruct_logit():
    """Explanations must be faithful: intercept + sum(contributions) == model log-odds."""
    import numpy as np
    pipe = joblib.load(ROOT / "ml" / "model.joblib")
    df = scoring.get_features_df().head(5)
    for res, (_, row) in zip(score_frame(pipe, df), df.iterrows()):
        logit = pipe.named_steps["clf"].intercept_[0] + sum(c["contribution"] for c in res["contributions"])
        assert abs(1 / (1 + np.exp(-logit)) - res["risk_probability"]) < 0.01


def test_azure_entry_script(monkeypatch):
    """ml/azure_score.py works as Azure ML would call it (init() then run(json))."""
    monkeypatch.setenv("AZUREML_MODEL_DIR", str(ROOT / "ml"))
    sys.path.insert(0, str(ROOT / "ml"))
    import azure_score
    azure_score.init()
    out = azure_score.run(json.dumps(sample_payload(scoring.get_features_df(), 2)))
    assert len(out) == 2 and 0 <= out[0]["risk_probability"] <= 1
    assert "error" in azure_score.run("{not json")


def test_azure_fallback_to_local(monkeypatch):
    from core import config
    monkeypatch.setattr(scoring, "settings", config.Settings(**{
        **config.settings.__dict__,
        "azureml_endpoint_url": "http://127.0.0.1:9/score",  # nothing listens here
        "azureml_endpoint_key": "k", "azureml_timeout_s": 1.0}))
    res = scoring.score_rows(scoring.get_features_df().head(2))
    assert res[0]["backend"] == "local" and scoring.status.last_error


def test_azure_success_path(monkeypatch):
    from core import config
    monkeypatch.setattr(scoring, "settings", config.Settings(**{
        **config.settings.__dict__,
        "azureml_endpoint_url": "https://example.invalid/score", "azureml_endpoint_key": "k"}))
    df = scoring.get_features_df().head(2)
    fake = score_frame(joblib.load(ROOT / "ml" / "model.joblib"), df)

    class Resp:
        def raise_for_status(self): pass
        def json(self): return fake

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured.update(headers=headers, body=json)
        return Resp()
    monkeypatch.setattr(scoring.requests, "post", fake_post)
    res = scoring.score_rows(df)
    assert res[0]["backend"] == "azureml"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["body"]["input_data"]["columns"] == FEATURES
