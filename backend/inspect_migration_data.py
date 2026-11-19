import json
from pathlib import Path

raw_dir = Path("../data/raw")
processed_dir = Path("../data/processed")
plan_dir = processed_dir / "cleaning_plans"

print("========== ORIGINAL DATASETS ==========")

for file in sorted(raw_dir.iterdir()):
    if file.suffix.lower() not in {".csv", ".xlsx", ".json"}:
        continue

    if file.suffix.lower() == ".json":
        continue

    metadata_file = raw_dir / f"{file.stem}.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

    print({
        "dataset_id": file.stem,
        "stored_filename": file.name,
        "original_filename": metadata.get("filename"),
        "extension": file.suffix,
    })

print("\n========== CLEANED DATASETS ==========")

for file in sorted(processed_dir.iterdir()):
    if file.suffix.lower() in {".csv", ".xlsx"}:
        print({
            "dataset_id": file.stem,
            "stored_filename": file.name,
            "extension": file.suffix,
        })

print("\n========== EXECUTED PLAN DETAILS ==========")

for file in sorted(plan_dir.glob("*.json")):
    plan = json.loads(file.read_text(encoding="utf-8"))

    if plan.get("status") != "executed":
        continue

    print(f"\nPlan: {plan['plan_id']}")

    for field in [
        "dataset_id",
        "source_filename",
        "status",
        "created_at",
        "approved_at",
        "executed_at",
        "cleaned_dataset_id",
        "output_filename",
        "execution_results",
        "output_metrics",
    ]:
        value = plan.get(field)

        if field == "execution_results" and isinstance(value, dict):
            value = {
                "keys": list(value.keys()),
                "operations_type": type(value.get("operations")).__name__,
            }

        if field == "output_metrics" and isinstance(value, dict):
            value = {"keys": list(value.keys())}

        print(f"{field}: {value}")

print("\n========== COMPLETE ==========")
