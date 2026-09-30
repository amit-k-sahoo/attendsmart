"""
AttendSmart — runtime configuration.

Everything is read from environment variables (optionally loaded from a
`.env` file in the project root — copy `.env.example` to get started).
Cloud integrations switch on automatically when their settings are present
and fall back to local implementations when they aren't, so the app always
runs out of the box.
"""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent

if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)


def _env(name, default=""):
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # --- storage / security -------------------------------------------------
    db_path: Path
    secret_key: str
    password_iterations: int
    max_failed_logins: int
    lockout_minutes: int
    allow_self_signup: bool
    api_key: str

    # --- Azure ML managed online endpoint -----------------------------------
    azureml_endpoint_url: str
    azureml_endpoint_key: str
    azureml_deployment: str
    azureml_timeout_s: float

    # --- Dialogflow ES --------------------------------------------------------
    dialogflow_project_id: str
    dialogflow_language: str
    dialogflow_webhook_user: str
    dialogflow_webhook_password: str
    dialogflow_use_webhook: bool

    @property
    def azureml_enabled(self) -> bool:
        return bool(self.azureml_endpoint_url and self.azureml_endpoint_key)

    @property
    def dialogflow_enabled(self) -> bool:
        return bool(self.dialogflow_project_id)


def load_settings() -> Settings:
    db_path = Path(_env("ATTENDSMART_DB_PATH") or ROOT / "instance" / "attendsmart.db")
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    return Settings(
        db_path=db_path,
        # A dev fallback keeps local runs working; production must set its own.
        secret_key=_env("ATTENDSMART_SECRET_KEY") or "dev-only-insecure-secret-change-me",
        password_iterations=int(_env("ATTENDSMART_PASSWORD_ITERATIONS") or 600_000),
        max_failed_logins=int(_env("ATTENDSMART_MAX_FAILED_LOGINS") or 5),
        lockout_minutes=int(_env("ATTENDSMART_LOCKOUT_MINUTES") or 15),
        allow_self_signup=_env("ATTENDSMART_ALLOW_SIGNUP", "true").lower() != "false",
        api_key=_env("ATTENDSMART_API_KEY"),
        azureml_endpoint_url=_env("AZUREML_ENDPOINT_URL"),
        azureml_endpoint_key=_env("AZUREML_ENDPOINT_KEY"),
        azureml_deployment=_env("AZUREML_DEPLOYMENT"),
        azureml_timeout_s=float(_env("AZUREML_TIMEOUT_S") or 15),
        dialogflow_project_id=_env("DIALOGFLOW_PROJECT_ID"),
        dialogflow_language=_env("DIALOGFLOW_LANGUAGE") or "en",
        dialogflow_webhook_user=_env("DIALOGFLOW_WEBHOOK_USER"),
        dialogflow_webhook_password=_env("DIALOGFLOW_WEBHOOK_PASSWORD"),
        dialogflow_use_webhook=_env("DIALOGFLOW_USE_WEBHOOK", "false").lower() == "true",
    )


settings = load_settings()
