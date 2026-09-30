"""
Step 1 — register data/student_features.csv as an Azure ML data asset.

  python azure_ml/register_data.py
"""

from common import DATA_ASSET, ROOT, ml_client


def main():
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import Data

    client = ml_client()
    asset = client.data.create_or_update(Data(
        name=DATA_ASSET,
        path=str(ROOT / "data" / "student_features.csv"),
        type=AssetTypes.URI_FILE,
        description="AttendSmart ML feature table (100% synthetic; names only are real). "
                    "Early-window features + late-window risk_label.",
        tags={"project": "attendsmart", "synthetic": "true"},
    ))
    print(f"Registered data asset {asset.name}:{asset.version}")


if __name__ == "__main__":
    main()
