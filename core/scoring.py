"""
AttendSmart — prediction client.

If AZUREML_ENDPOINT_URL / AZUREML_ENDPOINT_KEY are set, every prediction is
served by the Azure ML managed online endpoint (deployed with
azureml/deploy_endpoint.py). Otherwise — or if the endpoint errors or times
out — the same model is scored locally from ml/model.joblib, so a demo
never dies on a network hiccup. Each result records which backend actually
produced it, and the UI shows that as a badge.

The whole roster is scored in ONE request (Azure ML endpoints accept a
batch of rows) and cached briefly, so dashboards don't fan out 39 calls.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import joblib
import pandas as pd
import requests

from core.config import ROOT, settings
from ml.inference import FEATURES, risk_tier, score_frame

log = logging.getLogger(__name__)

FEATURES_PATH = ROOT / "data" / "student_features.csv"
MODEL_PATH = ROOT / "ml" / "model.joblib"
CACHE_TTL_S = 300

_lock = threading.Lock()
_model = None
_features_df = None
_cache: dict = {}


@dataclass
class ScoringStatus:
    backend: str = "local"            # "azureml" or "local"
    azure_configured: bool = False
    last_error: Optional[str] = None
    last_latency_ms: Optional[float] = None
    scored_at: float = field(default_factory=time.time)


status = ScoringStatus(azure_configured=settings.azureml_enabled)


def get_features_df() -> pd.DataFrame:
    global _features_df
    if _features_df is None:
        _features_df = pd.read_csv(FEATURES_PATH)
    return _features_df


def roster() -> dict:
    """student_id -> full name."""
    df = get_features_df()
    return dict(zip(df["student_id"], df["name"]))


def _local_model():
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def _score_azure(df: pd.DataFrame) -> list:
    payload = {"input_data": {"columns": FEATURES,
                              "data": df[FEATURES].astype(float).round(4).values.tolist()}}
    headers = {"Authorization": f"Bearer {settings.azureml_endpoint_key}",
               "Content-Type": "application/json"}
    if settings.azureml_deployment:  # pin a deployment (e.g. during blue/green rollout)
        headers["azureml-model-deployment"] = settings.azureml_deployment
    resp = requests.post(settings.azureml_endpoint_url, json=payload, headers=headers,
                         timeout=settings.azureml_timeout_s)
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, str):  # some endpoint stacks double-encode the JSON
        import json
        body = json.loads(body)
    if isinstance(body, dict) and "error" in body:
        raise RuntimeError(f"Endpoint error: {body['error']}")
    if not isinstance(body, list) or len(body) != len(df):
        raise RuntimeError("Unexpected response shape from Azure ML endpoint")
    return body


def score_rows(df: pd.DataFrame) -> list:
    """Scores feature rows via Azure ML (if configured) or locally. Adds a `backend` key."""
    if settings.azureml_enabled:
        started = time.perf_counter()
        try:
            results = _score_azure(df)
            status.backend, status.last_error = "azureml", None
            status.last_latency_ms = round((time.perf_counter() - started) * 1000, 1)
            for r in results:
                r["backend"] = "azureml"
            return results
        except Exception as exc:  # network, auth, timeout, schema — all fall back
            log.warning("Azure ML scoring failed, falling back to local model: %s", exc)
            status.last_error = f"{type(exc).__name__}: {exc}"[:300]

    results = score_frame(_local_model(), df)
    status.backend = "local"
    for r in results:
        r["backend"] = "local"
    return results


def _all_predictions() -> dict:
    with _lock:
        cached = _cache.get("all")
        if cached and time.time() - cached[0] < CACHE_TTL_S:
            return cached[1]
        df = get_features_df()
        scored = score_rows(df)
        preds = {}
        for (_, row), r in zip(df.iterrows(), scored):
            preds[row["student_id"]] = {
                "student_id": row["student_id"],
                "name": row["name"],
                "risk_label": int(r["risk_label"]),
                "risk_probability": float(r["risk_probability"]),
                "risk_tier": risk_tier(float(r["risk_probability"])),
                "top_factors": r["contributions"][:4],
                "all_factors": r["contributions"],
                "backend": r["backend"],
            }
        status.scored_at = time.time()
        _cache["all"] = (time.time(), preds)
        return preds


def predict_student(student_id: str) -> Optional[dict]:
    return _all_predictions().get(student_id)


def predict_all() -> list:
    return list(_all_predictions().values())


def clear_cache():
    with _lock:
        _cache.clear()
