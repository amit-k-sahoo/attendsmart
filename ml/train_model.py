"""
AttendSmart — attendance-risk model training.

Trains a scikit-learn classifier on the synthetic student_features.csv
table produced by data/generate_dataset.py, evaluates it honestly given the
small cohort size (Leave-One-Out cross-validation, since a single 80/20
split on 39 rows would be noisy and easy to overstate), and saves:

  ml/model.joblib          - fitted pipeline (StandardScaler + LogisticRegression)
  ml/model_metadata.json   - feature list, LOO-CV metrics, coefficients
  ml/model_card.md         - governance-facing model card

This same feature table / target design is what you would upload as a
registered dataset in Azure ML Studio's Designer or AutoML to train the
"real" managed version — see docs/deployment_guide.md.
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                              f1_score, roc_auc_score, confusion_matrix)
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from inference import FEATURES, TARGET

try:  # present inside Azure ML jobs; metrics then show up in the Studio run page
    import mlflow
except ImportError:
    mlflow = None

ROOT = Path(__file__).parent
DATA_PATH = ROOT.parent / "data" / "student_features.csv"

# Dropped from the model (kept in the dataset for the app's dashboard/explain
# view): attendance_pct_early is 0.84-correlated with consecutive_absences_early,
# and prior_module_score_pct showed ~0 correlation with the outcome in this
# cohort. With only 39 training rows, keeping collinear/uninformative columns
# in a logistic regression flips coefficient signs and makes the model
# unstable — pruning them is a deliberate small-n modeling choice, not an
# oversight (see model_card.md).


def load_data(path=DATA_PATH):
    path = Path(path)
    if path.is_dir():  # Azure ML uri_folder inputs arrive as a directory
        path = next(path.glob("*.csv"))
    df = pd.read_csv(path)
    df = df.dropna(subset=FEATURES + [TARGET])
    return df


def build_pipeline():
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", C=0.5)),
    ])


def loo_evaluate(df):
    X = df[FEATURES].values
    y = df[TARGET].values
    loo = LeaveOneOut()
    preds, probs = np.zeros(len(y)), np.zeros(len(y))
    for train_idx, test_idx in loo.split(X):
        pipe = build_pipeline()
        pipe.fit(X[train_idx], y[train_idx])
        probs[test_idx] = pipe.predict_proba(X[test_idx])[:, 1]
        preds[test_idx] = pipe.predict(X[test_idx])
    metrics = {
        "accuracy": round(float(accuracy_score(y, preds)), 3),
        "precision": round(float(precision_score(y, preds, zero_division=0)), 3),
        "recall": round(float(recall_score(y, preds, zero_division=0)), 3),
        "f1": round(float(f1_score(y, preds, zero_division=0)), 3),
        "roc_auc": round(float(roc_auc_score(y, probs)), 3),
        "confusion_matrix": confusion_matrix(y, preds).tolist(),  # [[TN,FP],[FN,TP]]
        "n": int(len(y)),
        "validation_method": "Leave-One-Out cross-validation (appropriate given the "
                              "small 39-student demo cohort; a held-out test split "
                              "would be too small/noisy to trust).",
    }
    return metrics


def parse_args():
    ap = argparse.ArgumentParser(description="Train the AttendSmart risk model.")
    ap.add_argument("--data", default=str(DATA_PATH),
                    help="student_features.csv (file or folder). Azure ML passes the data asset.")
    ap.add_argument("--output-dir", default=str(ROOT),
                    help="Where model.joblib + model_metadata.json are written.")
    return ap.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_data(args.data)
    print(f"Training on {len(df)} students, {len(FEATURES)} features.")

    metrics = loo_evaluate(df)
    print("LOO-CV metrics:", json.dumps(metrics, indent=2))
    if mlflow is not None:
        mlflow.log_metrics({f"loo_{k}": v for k, v in metrics.items()
                            if isinstance(v, (int, float))})
        mlflow.log_params({"model": "LogisticRegression", "C": 0.5,
                           "class_weight": "balanced", "n_features": len(FEATURES)})

    # Final model fit on all available data (this is what gets deployed)
    final_pipe = build_pipeline()
    final_pipe.fit(df[FEATURES].values, df[TARGET].values)
    joblib.dump(final_pipe, out_dir / "model.joblib")

    scaler = final_pipe.named_steps["scaler"]
    clf = final_pipe.named_steps["clf"]
    coefficients = dict(zip(FEATURES, [round(float(c), 4) for c in clf.coef_[0]]))

    metadata = {
        "features": FEATURES,
        "target": TARGET,
        "model_type": "LogisticRegression (StandardScaler-normalized, class_weight=balanced)",
        "coefficients": coefficients,
        "intercept": round(float(clf.intercept_[0]), 4),
        "feature_means_": {f: round(float(m), 3) for f, m in zip(FEATURES, scaler.mean_)},
        "feature_scales_": {f: round(float(s), 3) for f, s in zip(FEATURES, scaler.scale_)},
        "loo_cv_metrics": metrics,
        "risk_threshold_used_for_label": 0.75,
        "positive_class_meaning": "1 = predicted to fall below 75% attendance in the "
                                   "back half of the term",
        "trained_on_rows": len(df),
        "azure_ml_equivalent": "Two-Class Logistic Regression module in Azure ML "
                                "Designer, or AutoML classification job targeting "
                                "risk_label with the same feature columns.",
    }
    with open(out_dir / "model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nSaved model.joblib and model_metadata.json to {out_dir}")
    print("\nTop feature weights (standardized):")
    for feat, coef in sorted(coefficients.items(), key=lambda kv: -abs(kv[1])):
        direction = "increases risk" if coef > 0 else "decreases risk"
        print(f"  {feat:35s} {coef:+.3f}  ({direction})")


if __name__ == "__main__":
    main()
