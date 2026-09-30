"""
Stop Azure ML billing.

  python azure_ml/teardown.py                  # delete the deployment only (default)
  python azure_ml/teardown.py --delete-endpoint  # delete the endpoint too

Only the *deployment* (the VM behind the endpoint) bills. Deleting just the
deployment keeps the endpoint's scoring URL and key stable, so re-running
deploy_endpoint.py brings scoring back at the same address and nothing that
holds the URL/key (.env, Streamlit Cloud secrets) needs to change. While no
deployment exists the app falls back to the local model on its own.

The registered model, data asset and job history are always kept.
"""

import argparse

from common import ENDPOINT_NAME, ml_client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=ENDPOINT_NAME)
    ap.add_argument("--deployment", default="blue")
    ap.add_argument("--delete-endpoint", action="store_true",
                    help="Also delete the endpoint (its URL and key are lost)")
    args = ap.parse_args()
    client = ml_client()

    if args.delete_endpoint:
        print(f"Deleting endpoint {args.endpoint} (and its deployments)...")
        client.online_endpoints.begin_delete(name=args.endpoint).result()
        print("Deleted.")
        return

    try:
        endpoint = client.online_endpoints.get(args.endpoint)
    except Exception:
        print(f"Endpoint {args.endpoint} not found — nothing is billing.")
        return
    if args.deployment not in [d.name for d in client.online_deployments.list(args.endpoint)]:
        print(f"No '{args.deployment}' deployment on {args.endpoint} — nothing is billing.")
        return
    if (endpoint.traffic or {}).get(args.deployment):  # can't delete a deployment that takes traffic
        endpoint.traffic = {args.deployment: 0}
        client.online_endpoints.begin_create_or_update(endpoint).result()
    print(f"Deleting deployment {args.deployment} (endpoint {args.endpoint} is kept)...")
    client.online_deployments.begin_delete(name=args.deployment,
                                           endpoint_name=args.endpoint).result()
    print("Deleted. Billing stopped; endpoint URL and key are unchanged.")


if __name__ == "__main__":
    main()
