"""
Delete the managed online endpoint (it bills per hour while it exists).

  python azure_ml/teardown.py

The registered model, data asset and job history are kept, so re-running
deploy_endpoint.py brings the endpoint back without retraining. The app
falls back to local scoring automatically once the endpoint is gone —
remove AZUREML_ENDPOINT_URL / AZUREML_ENDPOINT_KEY from .env to skip the
failed-request round trip.
"""

import argparse

from common import ENDPOINT_NAME, ml_client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=ENDPOINT_NAME)
    args = ap.parse_args()
    client = ml_client()
    print(f"Deleting endpoint {args.endpoint}...")
    client.online_endpoints.begin_delete(name=args.endpoint).result()
    print("Deleted.")


if __name__ == "__main__":
    main()
