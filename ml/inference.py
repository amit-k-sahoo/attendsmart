"""
AttendSmart — model inference + explanation (single source of truth).

Used in three places so they can never drift apart:
  - core/scoring.py         local fallback scoring inside the app / webhook
  - ml/azure_score.py       the Azure ML managed online endpoint entry script
  - ml/train_model.py       feature list for training

Kept dependency-light and free of package-relative imports because Azure ML
uploads the ml/ folder as-is and imports this file from the endpoint
container.
"""

import numpy as np
import pandas as pd

FEATURES = [
    "consecutive_absences_early",
    "attendance_trend_early",
    "late_arrival_pct_early",
    "avg_quiz_score_early",
    "assignment_submission_rate_early",
    "avg_lms_logins_early",
    "avg_forum_posts_early",
]
TARGET = "risk_label"


def score_frame(pipeline, df: pd.DataFrame) -> list:
    """Scores every row of `df` (must contain FEATURES).

    Returns one dict per row:
      {"risk_probability": float, "risk_label": int,
       "contributions": [{"feature", "value", "contribution"}, ...]}
    Contributions are z-score x coefficient (log-odds units), sorted by
    absolute size — exactly what the "why flagged" chart shows.
    """
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    X = df[FEATURES].astype(float).to_numpy()
    probs = pipeline.predict_proba(X)[:, 1]
    labels = pipeline.predict(X)

    scaler = pipeline.named_steps["scaler"]
    coefs = pipeline.named_steps["clf"].coef_[0]
    contribs = scaler.transform(X) * coefs

    results = []
    for i in range(len(X)):
        factors = [
            {"feature": f, "value": round(float(X[i, j]), 4),
             "contribution": round(float(contribs[i, j]), 3)}
            for j, f in enumerate(FEATURES)
        ]
        factors.sort(key=lambda c: -abs(c["contribution"]))
        results.append({
            "risk_probability": round(float(probs[i]), 4),
            "risk_label": int(labels[i]),
            "contributions": factors,
        })
    return results


def risk_tier(probability: float) -> str:
    if probability >= 0.75:
        return "High"
    if probability >= 0.40:
        return "Medium"
    return "Low"


def sample_payload(df: pd.DataFrame, n: int = 2) -> dict:
    """Azure-ML-style request body built from the first `n` rows (for smoke tests)."""
    rows = df[FEATURES].head(n).astype(float)
    return {"input_data": {"columns": FEATURES,
                           "data": np.round(rows.to_numpy(), 4).tolist()}}
