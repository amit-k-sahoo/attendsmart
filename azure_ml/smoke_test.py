"""
Step 4 — verify the live endpoint and compare it with the local model.

  python azure_ml/smoke_test.py

Scores the full roster through AZUREML_ENDPOINT_URL and locally, then
reports latency and the largest probability difference (should be ~0 when
the endpoint serves the same model version).
"""

import sys
import time

import joblib
import pandas as pd

from common import ROOT

sys.path.insert(0, str(ROOT))
from core import scoring  # noqa: E402
from core.config import settings  # noqa: E402
from ml.inference import score_frame  # noqa: E402


def main():
    if not settings.azureml_enabled:
        sys.exit("AZUREML_ENDPOINT_URL / AZUREML_ENDPOINT_KEY are not set in .env.")
    df = pd.read_csv(ROOT / "data" / "student_features.csv")

    started = time.perf_counter()
    remote = scoring._score_azure(df)
    latency = (time.perf_counter() - started) * 1000
    local = score_frame(joblib.load(ROOT / "ml" / "model.joblib"), df)

    diffs = [abs(r["risk_probability"] - l["risk_probability"]) for r, l in zip(remote, local)]
    flips = sum(r["risk_label"] != l["risk_label"] for r, l in zip(remote, local))
    print(f"Endpoint OK: {len(remote)} rows scored in {latency:.0f} ms")
    print(f"Max |p_azure - p_local| = {max(diffs):.4f}; label disagreements: {flips}")
    print("Sample:", {k: remote[0][k] for k in ("risk_probability", "risk_label")},
          "top factor:", remote[0]["contributions"][0])


if __name__ == "__main__":
    main()
