"""
Start / stop the Azure ML online *deployment* from inside the app.

Only the deployment (the VM) bills; the endpoint keeps its URL and key, so the
app's secrets never change. Starting takes ~5-15 minutes, so start() returns at
once and a background thread finishes the job (routing 100% traffic once the
deployment is healthy); state() is what the System page polls.

Credentials: DefaultAzureCredential. Locally that is your `az login`; on
Streamlit Cloud set AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET for
a service principal scoped to the resource group (see docs/deployment_guide.md).
"""

import logging
import threading
from pathlib import Path

from core.config import _env

log = logging.getLogger("attendsmart.azure_control")

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "attendsmart-risk-model"
ENV_NAME = "attendsmart-sklearn-env"
DEPLOYMENT = "blue"
INSTANCE_TYPE = "Standard_DS2_v2"
CODE_DIR = ROOT / "ml"

_REQUIRED = ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE",
             "AZUREML_ENDPOINT_NAME")


def configured() -> bool:
    return all(_env(k) for k in _REQUIRED)


def _client():
    import os

    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    for k in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):  # service principal
        if _env(k):
            os.environ[k] = _env(k)
    return MLClient(DefaultAzureCredential(exclude_interactive_browser_credential=True),
                    _env("AZURE_SUBSCRIPTION_ID"), _env("AZURE_RESOURCE_GROUP"),
                    _env("AZUREML_WORKSPACE"))


def state() -> dict:
    """{'endpoint': bool, 'deployment': None|'Creating'|'Succeeded'|'Deleting'|'Failed'..., 'traffic': int}"""
    from azure.core.exceptions import ResourceNotFoundError

    c, name = _client(), _env("AZUREML_ENDPOINT_NAME")
    try:
        ep = c.online_endpoints.get(name)
    except ResourceNotFoundError:
        return {"endpoint": False, "deployment": None, "traffic": 0}
    dep = next((d for d in c.online_deployments.list(name) if d.name == DEPLOYMENT), None)
    ps = getattr(dep, "provisioning_state", None)
    return {"endpoint": True,
            "deployment": str(getattr(ps, "value", ps)) if ps else ("Unknown" if dep else None),
            "traffic": int((ep.traffic or {}).get(DEPLOYMENT, 0))}


def _route_traffic(c, name, pct):
    ep = c.online_endpoints.get(name)
    ep.traffic = {DEPLOYMENT: pct}
    c.online_endpoints.begin_create_or_update(ep).result()


def reconcile() -> None:
    """If the deployment is healthy but receives no traffic, route 100% to it."""
    s = state()
    if s["deployment"] == "Succeeded" and s["traffic"] != 100:
        _route_traffic(_client(), _env("AZUREML_ENDPOINT_NAME"), 100)


def _finish(poller):
    try:
        poller.result()
        _route_traffic(_client(), _env("AZUREML_ENDPOINT_NAME"), 100)
        log.info("Azure ML deployment is live.")
    except Exception:
        log.exception("Azure ML deployment failed")


def start() -> None:
    """Begin creating the deployment and return immediately."""
    from azure.ai.ml.entities import CodeConfiguration, ManagedOnlineDeployment

    c, name = _client(), _env("AZUREML_ENDPOINT_NAME")
    s = state()
    if not s["endpoint"]:
        raise RuntimeError("The endpoint doesn't exist. Create it once from a terminal with "
                           "./attendsmart.sh start (it issues the key the app uses).")
    if s["deployment"] in ("Creating", "Updating", "Succeeded"):
        return
    model = c.models.get(MODEL_NAME, label="latest")
    env = c.environments.get(ENV_NAME, label="latest")
    deployment = ManagedOnlineDeployment(
        name=DEPLOYMENT, endpoint_name=name, model=model, environment=f"{env.name}:{env.version}",
        code_configuration=CodeConfiguration(code=str(CODE_DIR), scoring_script="azure_score.py"),
        instance_type=INSTANCE_TYPE, instance_count=1)
    poller = c.online_deployments.begin_create_or_update(deployment)
    threading.Thread(target=_finish, args=(poller,), daemon=True).start()


def stop() -> None:
    """Stop billing: route traffic away, then delete the deployment (not waited on)."""
    c, name = _client(), _env("AZUREML_ENDPOINT_NAME")
    s = state()
    if s["deployment"] is None or s["deployment"] == "Deleting":
        return
    if s["traffic"]:
        _route_traffic(c, name, 0)
    c.online_deployments.begin_delete(name=DEPLOYMENT, endpoint_name=name)
