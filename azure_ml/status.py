"""Print whether the AttendSmart Azure ML deployment exists (i.e. is billing)."""

from common import ENDPOINT_NAME, ml_client

client = ml_client()
try:
    client.online_endpoints.get(ENDPOINT_NAME)
except Exception:
    raise SystemExit(f"Azure: endpoint {ENDPOINT_NAME} does not exist (nothing billing)")
live = [d.name for d in client.online_deployments.list(ENDPOINT_NAME)]
print(f"Azure: endpoint {ENDPOINT_NAME} exists; " +
      (f"deployment {live} RUNNING (billing)" if live else "no deployment (not billing)"))
