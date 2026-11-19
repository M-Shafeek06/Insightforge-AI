import json
from pathlib import Path
from uuid import UUID

raw_dir = Path("../data/raw")
processed_dir = Path("../data/processed")
plan_dir = processed_dir / "cleaning_plans"
version_dir = Path("../data/metadata/dataset_versions")

raw_ids = {
    f.stem for f in raw_dir.glob("*.csv")
}

processed_ids = {
    f.stem for f in processed_dir.glob("*.csv")
}

raw_names = {}

for file in raw_dir.glob("*.json"):
    data = json.loads(file.read_text(encoding="utf-8"))
    raw_names[file.stem] = data.get("filename")

plans = [
    json.loads(f.read_text(encoding="utf-8"))
    for f in plan_dir.glob("*.json")
]

version_entries = []

for file in version_dir.glob("*.json"):
    registry = json.loads(file.read_text(encoding="utf-8"))
    version_entries.extend(registry.get("versions", []))

print("========== DATASET INVENTORY ==========")
print("Raw CSV files:", len(raw_ids))
print("Processed CSV files:", len(processed_ids))
print("Raw IDs with metadata:", len(raw_names))

print("\n========== PLAN DATASET REFERENCES ==========")

plan_dataset_ids = {p["dataset_id"] for p in plans}

for dataset_id in sorted(plan_dataset_ids):
    print({
        "dataset_id": dataset_id,
        "raw_file_exists": dataset_id in raw_ids,
        "raw_metadata_exists": dataset_id in raw_names,
    })

print("\n========== EXECUTED PLAN OUTPUTS ==========")

for plan in plans:
    if plan.get("status") == "executed":
        cleaned_id = plan.get("cleaned_dataset_id")
        print({
            "plan_id": plan["plan_id"],
            "source_exists": plan["dataset_id"] in raw_ids,
            "cleaned_dataset_id": cleaned_id,
            "cleaned_file_exists": cleaned_id in processed_ids if cleaned_id else False,
            "output_filename": plan.get("output_filename"),
            "execution_results_present": plan.get("execution_results") is not None,
            "output_metrics_present": plan.get("output_metrics") is not None,
        })

print("\n========== VERSION REFERENCES ==========")

for version in version_entries:
    print({
        "dataset_id": version["dataset_id"],
        "original_dataset_id": next(
            (
                json.loads(f.read_text(encoding="utf-8"))["original_dataset_id"]
                for f in version_dir.glob("*.json")
                if any(
                    v["dataset_id"] == version["dataset_id"]
                    for v in json.loads(f.read_text(encoding="utf-8"))["versions"]
                )
            ),
            None,
        ),
        "cleaning_plan_id": version.get("cleaning_plan_id"),
    })

print("\n========== INVALID UUID CHECK ==========")

all_ids = (
    raw_ids
    | processed_ids
    | plan_dataset_ids
    | {p["plan_id"] for p in plans}
)

for dataset_id in sorted(all_ids):
    try:
        UUID(dataset_id)
    except ValueError:
        print("INVALID:", dataset_id)

print("\n========== RECONCILIATION COMPLETE ==========")
