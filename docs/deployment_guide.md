# AttendSmart — Going Live on Azure ML and Dialogflow ES

The app runs fully offline by default. It uses a local copy of the model and a
local intent engine that implements the same intents. This guide switches
each part to its real cloud service. Everything is driven by `.env`, so no
code changes are needed, and each integration falls back to local if it's
unavailable.

> **Heads-up:** cloud consoles change their menus often. The SDK and API
> calls below are stable, but if a console label differs, search the portal
> for the term in *italics*.

---

## Part A — Azure ML (SDK v2)

### A0. Prerequisites
- An Azure subscription and an **Azure Machine Learning workspace**. Create
  one in the portal under *Azure Machine Learning*, or run
  `az ml workspace create -n <ws> -g <rg>`.
- The Azure CLI, signed in with `az login`. The scripts authenticate with
  `DefaultAzureCredential`, which reuses that login. In CI, set
  `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_CLIENT_SECRET` for a
  service principal instead.
- Enough vCPU quota for one `Standard_DS2_v2` instance (Azure reserves 2x its vCPUs for updates) in your region. You
  can check this under *Quotas* in ML Studio.

Add these to `.env`:
```
AZURE_SUBSCRIPTION_ID=...
AZURE_RESOURCE_GROUP=...
AZUREML_WORKSPACE=...
AZUREML_ENDPOINT_NAME=attendsmart-risk-<something-unique>
```
The endpoint name must be unique within the Azure region.

### A1. Register the dataset
```bash
python azure_ml/register_data.py
```
This creates the data asset `attendsmart-student-features` from
`data/student_features.csv`, tagged as synthetic.

### A2. Train as an Azure ML job
```bash
python azure_ml/train.py
# or, on a dedicated cluster that scales to zero when idle:
python azure_ml/train.py --compute cpu-cluster
```
- The job runs the same `ml/train_model.py` you run locally: leave-one-out
  cross-validation, then a final fit. It uses the environment in
  `azure_ml/environment/conda.yaml`.
- LOO-CV metrics are logged with MLflow, so they appear on the job's page
  in Studio. The script prints the Studio URL.
- The job output is registered as the model `attendsmart-risk-model`, and a
  copy is downloaded to `ml/azure_artifacts/v<N>/`.

**Alternatives that show up well in a demo:**
- *AutoML:* start a classification job on the registered data asset with
  target `risk_label`. Exclude `student_id`, `name`, `city`,
  `attendance_pct_actual_late_window` and `risk_tier`. The last two leak the
  label.
- *Designer:* use the *Two-Class Logistic Regression* module with the same
  seven feature columns.

### A3. Deploy a managed online endpoint
```bash
python azure_ml/deploy_endpoint.py --write-env
# or skip A1–A2 and deploy the locally trained model:
python azure_ml/deploy_endpoint.py --local-model --write-env
```
- This creates the endpoint (key auth) and a `blue` deployment, then sends
  100% of traffic to it. It usually takes 8–15 minutes.
- The scoring script is `ml/azure_score.py`. It imports `ml/inference.py`,
  so the endpoint returns probabilities **and** per-feature explanations in
  exactly the shape the dashboard expects.
- `--write-env` saves `AZUREML_ENDPOINT_URL` and `AZUREML_ENDPOINT_KEY`
  into `.env`.

### A4. Verify, then use it
```bash
python azure_ml/smoke_test.py
```
This scores the whole roster through the endpoint and compares the results
with the local model. The max probability difference should be about 0, with
no label disagreements.

Restart the app. Every dashboard then shows **"Scored live by Azure ML
endpoint · N ms"**. The admin **System status** page shows the active
backend, the last latency and any endpoint error. If the endpoint fails or
times out, the app falls back to the local model and says so on screen.

To route traffic during a blue/green rollout, set `AZUREML_DEPLOYMENT=green`.
The client then sends the `azureml-model-deployment` header.

### A5. Stop billing (important: the deployment bills hourly)
```bash
python azure_ml/teardown.py          # or: ./attendsmart.sh stop
```
This deletes only the deployment. The endpoint keeps its scoring URL and key, so
`.env` and Streamlit Cloud secrets never need updating; run A3 (or
`./attendsmart.sh start`) to bring scoring back at the same address. Add
`--delete-endpoint` to remove the endpoint as well. The model, data asset and
job history are always kept.

---

## Part B — Dialogflow ES

### B0. Prerequisites
1. Create a Google Cloud project and enable the **Dialogflow API**.
2. Create an agent in the [Dialogflow ES console](https://dialogflow.cloud.google.com/):
   name it `AttendSmart`, select that project, set language English and
   timezone Asia/Kolkata.
3. Create a **service account**. Give it *Dialogflow API Admin* for the sync
   script, or *Dialogflow API Client* if it's only for the app. Download a
   JSON key and keep it outside the repo.
4. Add these to `.env`:
   ```
   DIALOGFLOW_PROJECT_ID=<gcp-project-id>
   GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/key.json
   DIALOGFLOW_WEBHOOK_USER=attendsmart
   DIALOGFLOW_WEBHOOK_PASSWORD=<long random string>
   ATTENDSMART_SECRET_KEY=<long random string>
   ```

### B1. Put the webhook on a public HTTPS URL
Dialogflow has to reach `POST /dialogflow/webhook`. Pick one option:

- **For development:** run `uvicorn api.main:app --port 8000`, then
  `ngrok http 8000`, and use the `https://…ngrok…` URL.
- **Azure Container Apps**, which keeps everything in Azure:
  ```bash
  az containerapp up -n attendsmart-api -g <rg> --source . \
    --target-port 8000 --ingress external \
    --env-vars ATTENDSMART_SECRET_KEY=... DIALOGFLOW_WEBHOOK_USER=... \
               DIALOGFLOW_WEBHOOK_PASSWORD=... AZUREML_ENDPOINT_URL=... AZUREML_ENDPOINT_KEY=...
  ```
  Set the container command to
  `uvicorn api.main:app --host 0.0.0.0 --port 8000`. Deploy the Streamlit
  app the same way on port 8501, and give both the **same
  `ATTENDSMART_SECRET_KEY`**. With SQLite, both containers also need a shared
  volume (an Azure Files mount at `/app/instance`). Otherwise, move the
  database to PostgreSQL.

Check the deployment with `curl https://<host>/health`.

### B2. Sync the agent via the API
```bash
python -m chatbot.sync_dialogflow_agent --webhook-url https://<host>/dialogflow/webhook
```
The sync is idempotent. It:
- creates or updates the `@student_name` entity, with all roster names and
  first-name synonyms
- creates or updates all intents from `chatbot/agent_spec.py`, with webhook
  fulfillment enabled; the agent's built-in *Default Welcome Intent* is
  reused for greetings
- points the agent's fulfillment at your webhook, with the basic-auth
  credentials from `.env`
- trains the agent

As an alternative, `chatbot/AttendSmart_dialogflow_agent.zip` can be
restored in the console under *Agent settings → Export and Import → Restore
from zip*. You would then set the fulfillment URL by hand. The API sync is
more reliable because it doesn't depend on the zip schema.

### B3. How identity reaches the webhook
```
app ──detectIntent(text, queryParams.payload = {attendsmart_token})──▶ Dialogflow
Dialogflow ──POST /dialogflow/webhook (basic auth, originalDetectIntentRequest.payload)──▶ API
API verifies HMAC token → identity {user_id, role, name, student_id} → fulfillment.py (RBAC)
```
The token lasts 5 minutes and is signed with `ATTENDSMART_SECRET_KEY`.
Requests without a valid token, such as the console simulator or the
Messenger widget, are treated as anonymous. They get general answers only:
no personal data and no roster.

### B4. Verify
- Restart the app. The Assistant page shows **"Powered by Dialogflow ES"**,
  and each answer is tagged with the matched intent and confidence.
- As a student, "Who's at risk?" should be refused. As an advisor, it
  should list the cohort.
- If Dialogflow can't be reached, the assistant falls back to the local
  engine and tags answers `local (Dialogflow unreachable)`. If Dialogflow
  answers but your webhook fails, the app fulfils locally using the intent
  Dialogflow matched.

---

## Part C — Suggested demo setup
- Before presenting, run `python -m core.seed --reset` for a clean audit log.
- Start the Azure endpoint about 20 minutes ahead of time, and run
  `azure_ml/smoke_test.py`.
- Keep ML Studio open on the training job's metrics and the endpoint's *Test*
  tab, and keep the Dialogflow console open on the `CheckStudentRisk` intent.
- Afterwards, run `python azure_ml/teardown.py`.
