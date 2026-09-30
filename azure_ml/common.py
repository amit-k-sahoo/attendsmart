"""
AttendSmart — shared Azure ML (SDK v2) helpers.

Reads the workspace from .env:
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZUREML_WORKSPACE
and authenticates with DefaultAzureCredential (run `az login` first, or set
AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET for a service
principal in CI).
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import settings  # noqa: E402,F401  (loads .env)

DATA_ASSET = "attendsmart-student-features"
ENV_NAME = "attendsmart-sklearn-env"
MODEL_NAME = "attendsmart-risk-model"
EXPERIMENT = "attendsmart-risk"
ENDPOINT_NAME = os.environ.get("AZUREML_ENDPOINT_NAME", "attendsmart-risk")
BASE_IMAGE = "mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest"
CONDA_FILE = Path(__file__).parent / "environment" / "conda.yaml"
CODE_DIR = ROOT / "ml"  # shared by the training job and the endpoint scoring script


def ml_client():
    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    missing = [k for k in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE")
               if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} — set them in .env (see .env.example).")
    return MLClient(
        DefaultAzureCredential(exclude_interactive_browser_credential=False),
        subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
        resource_group_name=os.environ["AZURE_RESOURCE_GROUP"],
        workspace_name=os.environ["AZUREML_WORKSPACE"],
    )


def get_or_create_environment(client):
    from azure.ai.ml.entities import Environment

    env = Environment(
        name=ENV_NAME,
        description="scikit-learn runtime for AttendSmart training + online scoring",
        image=BASE_IMAGE,
        conda_file=str(CONDA_FILE),
    )
    # create_or_update is idempotent: a new version is only made if the spec changed
    return client.environments.create_or_update(env)


def update_env_file(values: dict, path: Path = ROOT / ".env"):
    """Upserts KEY=value lines in .env (creates it if needed)."""
    lines = path.read_text().splitlines() if path.exists() else []
    for key, value in values.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        new_line = f"{key}={value}"
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
    path.write_text("\n".join(lines) + "\n")
