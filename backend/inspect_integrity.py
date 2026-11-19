import json
from pathlib import Path
from collections import Counter

version_dir = Path("../data/metadata/dataset_versions")
plan_dir = Path("../data/processed/cleaning_plans")
raw_dir = Path("../data/raw")

print("========== VERSION REGISTRIES ==========")

for file in sorted(version_dir.glob("*.json")):
    data = json.loads(file.read_text(encoding="utf-8"))

    print(f"\nRegistry: {file.stem}")
    print("Original ID:", data["original_dataset_id"])

    for version in data.get("versions", []):
        print({
            "dataset_id": version.get("dataset_id"),
            "version_number": version.get("version_number"),
            "version_type": version.get("version_type"),
            "cleaning_plan_id": version.get("cleaning_plan_id"),
            "parent_dataset_id": version.get("parent_dataset_id"),
        })

print("\n========== CLEANING PLAN SUMMARY ==========")

plans = []
for file in sorted(plan_dir.glob("*.json")):
    data = json.loads(file.read_text(encoding="utf-8"))
    plans.append(data)

print("Total plans:", len(plans))
print("Statuses:", dict(Counter(p.get("status") for p in plans)))

for field in [
    "execution_results",
    "output_metrics",
    "cleaned_dataset_id",
    "approved_at",
    "executed_at",
]:
    print(
        f"{field} present:",
        sum(field in p for p in plans),
        "| non-null:",
        sum(p.get(field) is not None for p in plans),
    )

print("\n========== RAW DATASET METADATA ==========")

raw_metadata = {}

for file in raw_dir.glob("*.json"):
    data = json.loads(file.read_text(encoding="utf-8"))
    raw_metadata[file.stem] = data.get("filename")

print("Raw metadata records:", len(raw_metadata))

print("\n========== CLEANING PLAN RELATIONSHIPS ==========")

for plan in plans:
    print({
        "plan_id": plan.get("plan_id"),
        "dataset_id": plan.get("dataset_id"),
        "cleaned_dataset_id": plan.get("cleaned_dataset_id"),
        "status": plan.get("status"),
    })
