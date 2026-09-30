"""
Step 3 — deploy the registered model to a managed online endpoint.

Uses ml/azure_score.py as the scoring script (which shares ml/inference.py
with the app), so the endpoint returns probabilities AND per-feature
explanations in exactly the shape the dashboard/chatbot expect.

  python azure_ml/deploy_endpoint.py --write-env
  python azure_ml/deploy_endpoint.py --local-model   # skip Azure training, deploy ml/model.joblib

--write-env stores AZUREML_ENDPOINT_URL / AZUREML_ENDPOINT_KEY in .env so the
app switches to live Azure scoring on next start. Endpoints bill while they
exist — run azure_ml/teardown.py when you're done demoing.
"""

import argparse

from common import (CODE_DIR, ENDPOINT_NAME, MODEL_NAME, ROOT, get_or_create_environment,
                    ml_client, update_env_file)


def main():
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import (CodeConfiguration, ManagedOnlineDeployment,
                                      ManagedOnlineEndpoint, Model)

    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=ENDPOINT_NAME,
                    help="Endpoint name (must be unique within the Azure region)")
    ap.add_argument("--deployment", default="blue")
    ap.add_argument("--model-version", help="Registered model version (default: latest)")
    ap.add_argument("--local-model", action="store_true",
                    help="Register and deploy the locally trained ml/model.joblib")
    ap.add_argument("--instance-type", default="Standard_DS3_v2")
    ap.add_argument("--write-env", action="store_true",
                    help="Write the scoring URL + key into .env")
    args = ap.parse_args()

    client = ml_client()

    if args.local_model:
        model = client.models.create_or_update(Model(
            name=MODEL_NAME, path=str(ROOT / "ml" / "model.joblib"),
            type=AssetTypes.CUSTOM_MODEL, tags={"source": "local-train"},
        ))
    elif args.model_version:
        model = client.models.get(MODEL_NAME, version=args.model_version)
    else:
        model = client.models.get(MODEL_NAME, label="latest")
    print(f"Deploying model {model.name}:{model.version}")

    endpoint = ManagedOnlineEndpoint(
        name=args.endpoint, auth_mode="key",
        description="AttendSmart attendance-risk scoring",
        tags={"project": "attendsmart"},
    )
    print(f"Creating/updating endpoint {args.endpoint} (takes a minute or two)...")
    client.online_endpoints.begin_create_or_update(endpoint).result()

    env = get_or_create_environment(client)
    deployment = ManagedOnlineDeployment(
        name=args.deployment,
        endpoint_name=args.endpoint,
        model=model,
        environment=f"{env.name}:{env.version}",
        code_configuration=CodeConfiguration(code=str(CODE_DIR), scoring_script="azure_score.py"),
        instance_type=args.instance_type,
        instance_count=1,
    )
    print(f"Creating deployment {args.deployment} (typically 8-15 minutes)...")
    client.online_deployments.begin_create_or_update(deployment).result()

    endpoint = client.online_endpoints.get(args.endpoint)
    endpoint.traffic = {args.deployment: 100}
    client.online_endpoints.begin_create_or_update(endpoint).result()

    endpoint = client.online_endpoints.get(args.endpoint)
    print(f"\nScoring URI: {endpoint.scoring_uri}")
    if args.write_env:
        keys = client.online_endpoints.get_keys(args.endpoint)
        update_env_file({"AZUREML_ENDPOINT_URL": endpoint.scoring_uri,
                         "AZUREML_ENDPOINT_KEY": keys.primary_key,
                         "AZUREML_ENDPOINT_NAME": args.endpoint})
        print("Wrote AZUREML_ENDPOINT_URL / AZUREML_ENDPOINT_KEY to .env — restart the app.")
    else:
        print("Re-run with --write-env to save the URL + key to .env, or fetch the key with:\n"
              f"  az ml online-endpoint get-credentials -n {args.endpoint}")


if __name__ == "__main__":
    main()
