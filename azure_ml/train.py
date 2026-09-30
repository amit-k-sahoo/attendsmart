"""
Step 2 — train the risk model as an Azure ML command job and register it.

Runs the same ml/train_model.py used locally (Leave-One-Out CV + final fit)
on Azure ML compute, logs metrics to the Studio run page via MLflow, then
registers the job's output folder as the model `attendsmart-risk-model`.

  python azure_ml/train.py                      # serverless compute
  python azure_ml/train.py --compute cpu-cluster # an existing / new AmlCompute cluster
"""

import argparse

from common import (CODE_DIR, DATA_ASSET, EXPERIMENT, MODEL_NAME, ROOT,
                    get_or_create_environment, ml_client)


def ensure_cluster(client, name):
    from azure.ai.ml.entities import AmlCompute
    try:
        return client.compute.get(name)
    except Exception:
        print(f"Creating compute cluster {name} (scales to zero when idle)...")
        return client.compute.begin_create_or_update(AmlCompute(
            name=name, size="Standard_DS3_v2", min_instances=0, max_instances=1,
            idle_time_before_scale_down=120,
        )).result()


def main():
    from azure.ai.ml import Input, Output, command
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import Model

    ap = argparse.ArgumentParser()
    ap.add_argument("--compute", help="AmlCompute cluster name (omit for serverless)")
    ap.add_argument("--no-wait", action="store_true", help="Submit and return immediately")
    args = ap.parse_args()

    client = ml_client()
    env = get_or_create_environment(client)
    if args.compute:
        ensure_cluster(client, args.compute)

    data = client.data.get(DATA_ASSET, label="latest")
    job = command(
        code=str(CODE_DIR),
        command="python train_model.py --data ${{inputs.data}} --output-dir ${{outputs.model_dir}}",
        inputs={"data": Input(type=AssetTypes.URI_FILE, path=data.id)},
        outputs={"model_dir": Output(type=AssetTypes.URI_FOLDER)},
        environment=f"{env.name}:{env.version}",
        compute=args.compute,  # None => serverless compute
        experiment_name=EXPERIMENT,
        display_name="attendsmart-logreg-loocv",
        description="Logistic regression, LOO-CV evaluated, on early-term engagement features.",
    )
    job = client.jobs.create_or_update(job)
    print(f"Submitted job {job.name}\nStudio: {job.studio_url}")
    if args.no_wait:
        return

    client.jobs.stream(job.name)
    job = client.jobs.get(job.name)
    if job.status != "Completed":
        raise SystemExit(f"Job finished with status {job.status}")

    model = client.models.create_or_update(Model(
        name=MODEL_NAME,
        path=f"azureml://jobs/{job.name}/outputs/model_dir",
        type=AssetTypes.CUSTOM_MODEL,
        description="AttendSmart attendance-risk logistic regression (model.joblib + metadata)",
        tags={"job": job.name, "framework": "scikit-learn"},
    ))
    print(f"Registered model {model.name}:{model.version}")

    out = ROOT / "ml" / "azure_artifacts" / f"v{model.version}"
    client.jobs.download(job.name, output_name="model_dir", download_path=str(out))
    print(f"Downloaded trained artifacts to {out}")


if __name__ == "__main__":
    main()
