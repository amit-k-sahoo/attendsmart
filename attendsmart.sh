#!/usr/bin/env bash
# Start/stop AttendSmart. Only the Azure ML *deployment* bills (hourly), so `stop`
# deletes just that; the endpoint keeps its URL and key, so .env and Streamlit
# Cloud secrets are set ONCE and never change.
#
#   ./attendsmart.sh start          Azure scoring goes live (~10-15 min) + local app
#   ./attendsmart.sh start local    local app only, local model, no cost
#   ./attendsmart.sh stop           stop the local app and the Azure deployment (billing stops)
#   ./attendsmart.sh status         what is running
#   ./attendsmart.sh secrets        print the block to paste ONCE into Streamlit Cloud > Secrets
#
# Both the local app and Streamlit Cloud read the same endpoint URL/key. While the
# deployment is stopped they fall back to the local model automatically.
set -uo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8501}"
RUN_DIR=".run"; PID_FILE="$RUN_DIR/streamlit.pid"; LOG_FILE="$RUN_DIR/streamlit.log"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
mkdir -p "$RUN_DIR"

app_pid() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null && cat "$PID_FILE"; }

azure() {  # azure <script.py> [args] — runs the repo's Azure ML scripts
  PYTHONPATH=azure_ml "$PY" "azure_ml/$@"
}

start_app() {
  if pid=$(app_pid); then echo "App already running (pid $pid) → http://localhost:$PORT"; return; fi
  nohup "$PY" -m streamlit run app/attendsmart_app.py --server.port "$PORT" --server.headless true \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "App started (pid $!) → http://localhost:$PORT   (logs: $LOG_FILE)"
}

stop_app() {
  if pid=$(app_pid); then kill "$pid" && echo "App stopped."; else echo "App not running."; fi
  rm -f "$PID_FILE"
}

has_endpoint_env() { grep -qE '^AZUREML_ENDPOINT_URL=.+' .env 2>/dev/null; }

deploy_azure() {
  echo "Deploying Azure ML (bills hourly until: ./attendsmart.sh stop) — takes ~10-15 min ..."
  azure deploy_endpoint.py --local-model --write-env \
    || { echo "!! Azure deploy failed (run 'az login'; check AZURE_* in .env)"; return 1; }
  echo "Azure scoring is live."
}

case "${1:-}" in
  start)
    if [ "${2:-}" = "local" ]; then start_app; exit 0; fi
    if has_endpoint_env; then
      start_app            # endpoint URL/key already known: app falls back until Azure is live
      deploy_azure || exit 1
    else
      deploy_azure || exit 1   # first run: deploy writes URL/key to .env, then app picks them up
      start_app
      echo "First run: run ./attendsmart.sh secrets and paste the output into Streamlit Cloud > Secrets (once)."
    fi
    ;;
  stop)
    stop_app
    if grep -qE '^AZUREML_ENDPOINT_NAME=.+' .env 2>/dev/null; then
      azure teardown.py || {
        echo "!! Could not delete the Azure deployment — it may STILL BE BILLING."
        echo "!! Run 'az login' and retry, or delete the deployment in Azure ML Studio > Endpoints."
        exit 1; }
    else
      echo "No AZUREML_ENDPOINT_NAME in .env — skipping Azure."
    fi
    ;;
  status)
    if pid=$(app_pid); then echo "Local app: running (pid $pid) → http://localhost:$PORT"; else echo "Local app: stopped"; fi
    if has_endpoint_env; then
      azure status.py 2>/dev/null || echo "Azure: endpoint configured in .env (run 'az login' to see live state)"
    else
      echo "Azure: no endpoint yet — run ./attendsmart.sh start"
    fi
    ;;
  secrets)
    has_endpoint_env || { echo "No endpoint yet — run ./attendsmart.sh start first."; exit 1; }
    echo "# Paste into Streamlit Cloud > Manage app > Settings > Secrets (once)"
    grep -E '^(AZUREML_ENDPOINT_URL|AZUREML_ENDPOINT_KEY)=' .env | sed -E 's/^([A-Z_]+)=(.*)$/\1 = "\2"/'
    ;;
  *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
