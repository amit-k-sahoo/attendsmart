import os
import sys
import tempfile
from pathlib import Path

# Configure BEFORE core.config is imported anywhere.
_TMP = tempfile.mkdtemp(prefix="attendsmart-test-")
os.environ.update({
    "ATTENDSMART_DB_PATH": str(Path(_TMP) / "test.db"),
    "ATTENDSMART_SECRET_KEY": "test-secret",
    "ATTENDSMART_PASSWORD_ITERATIONS": "1000",   # fast hashing in tests
    "ATTENDSMART_MAX_FAILED_LOGINS": "3",
    "AZUREML_ENDPOINT_URL": "",
    "AZUREML_ENDPOINT_KEY": "",
    "DIALOGFLOW_PROJECT_ID": "",
    "DIALOGFLOW_WEBHOOK_USER": "",
    "DIALOGFLOW_WEBHOOK_PASSWORD": "",
    "ATTENDSMART_API_KEY": "",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from core import auth, scoring  # noqa: E402
from core.db import get_conn, init_db  # noqa: E402

PASSWORD = "correct-horse-9"


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    with get_conn() as conn:
        for table in ("sessions", "users", "audit_log", "overrides", "escalations"):
            conn.execute(f"DELETE FROM {table}")
    scoring.clear_cache()
    yield


@pytest.fixture
def student():
    sid, name = next(iter(scoring.roster().items()))
    return auth.create_user("student@example.com", name, PASSWORD, "student", sid)


@pytest.fixture
def other_student():
    sid, name = list(scoring.roster().items())[1]
    return auth.create_user("other@example.com", name, PASSWORD, "student", sid)


@pytest.fixture
def advisor():
    return auth.create_user("advisor@example.com", "Test Advisor", PASSWORD, "advisor")


@pytest.fixture
def admin():
    return auth.create_user("admin@example.com", "Test Admin", PASSWORD, "admin")
