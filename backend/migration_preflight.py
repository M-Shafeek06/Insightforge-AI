import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.services.settings import settings


# ============================================================
# 1. PATH CONFIGURATION
# ============================================================

RAW_DIR = settings.upload_dir.resolve()
PROCESSED_DIR = settings.processed_dir.resolve()

PLAN_DIR = PROCESSED_DIR / "cleaning_plans"

VERSION_DIR = (
    settings.upload_dir.parent / "metadata" / "dataset_versions"
).resolve()

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}

VALID_PLAN_STATUSES = {
    "pending",
    "approved",
    "executed",
}


# ============================================================
# 2. REPORT STORAGE
# ============================================================

issues = []
warnings = []

datasets = {}
plans = {}
versions = []
executions = []


def add_issue(category, message):
    issues.append({
        "category": category,
        "message": message,
    })


def add_warning(category, message):
    warnings.append({
        "category": category,
        "message": message,
    })


# ============================================================
# 3. VALIDATION HELPERS
# ============================================================

def valid_uuid(value):
    if not isinstance(value, str):
        return False

    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False

    try:
        datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return True
    except ValueError:
        return False


def read_json(path):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        add_issue(
            "JSON",
            f"{path.name}: {exc}",
        )
        return None


def discover_files(directory):
    if not directory.is_dir():
        add_issue(
            "DIRECTORY",
            f"Directory does not exist: {directory}",
        )
        return []

    return sorted(
        file
        for file in directory.iterdir()
        if file.is_file()
        and file.suffix.lower() in SUPPORTED_EXTENSIONS
    )


# ============================================================
# 4. DISCOVER ORIGINAL DATASETS
# ============================================================

def inspect_original_datasets():

    print("\n========== ORIGINAL DATASETS ==========")

    for file in discover_files(RAW_DIR):

        dataset_id = file.stem

        if not valid_uuid(dataset_id):
            add_issue(
                "DATASET UUID",
                f"Invalid original dataset ID: {dataset_id}",
            )
            continue

        if dataset_id in datasets:
            add_issue(
                "DUPLICATE DATASET",
                f"Duplicate dataset ID: {dataset_id}",
            )
            continue

        metadata_file = RAW_DIR / f"{dataset_id}.json"

        if not metadata_file.is_file():
            add_issue(
                "DATASET METADATA",
                f"Missing metadata sidecar: {metadata_file.name}",
            )
            continue

        metadata = read_json(metadata_file)

        if not isinstance(metadata, dict):
            add_issue(
                "DATASET METADATA",
                f"Metadata must be a JSON object: {metadata_file.name}",
            )
            continue

        original_filename = metadata.get("filename")

        if not isinstance(original_filename, str) or not original_filename.strip():
            add_issue(
                "DATASET METADATA",
                f"Invalid original filename: {metadata_file.name}",
            )
            continue

        datasets[dataset_id] = {
            "id": dataset_id,
            "filename": original_filename,
            "stored_filename": file.name,
            "storage_location": "raw",
        }

    print("Valid original datasets:", sum(
        item["storage_location"] == "raw"
        for item in datasets.values()
    ))


# ============================================================
# 5. DISCOVER CLEANED DATASETS
# ============================================================

def inspect_cleaned_datasets():

    print("\n========== CLEANED DATASETS ==========")

    for file in discover_files(PROCESSED_DIR):

        dataset_id = file.stem

        if not valid_uuid(dataset_id):
            add_issue(
                "CLEANED DATASET UUID",
                f"Invalid cleaned dataset ID: {dataset_id}",
            )
            continue

        if dataset_id in datasets:
            add_issue(
                "DUPLICATE DATASET",
                f"Dataset ID exists in multiple locations: {dataset_id}",
            )
            continue

        datasets[dataset_id] = {
            "id": dataset_id,
            "filename": file.name,
            "stored_filename": file.name,
            "storage_location": "processed",
        }

    print("Total discovered datasets:", len(datasets))

    print(
        "Cleaned datasets:",
        sum(
            item["storage_location"] == "processed"
            for item in datasets.values()
        ),
    )


# ============================================================
# 6. INSPECT CLEANING PLANS
# ============================================================

def inspect_cleaning_plans():

    print("\n========== CLEANING PLANS ==========")

    if not PLAN_DIR.is_dir():
        add_issue(
            "DIRECTORY",
            f"Cleaning plan directory missing: {PLAN_DIR}",
        )
        return

    for file in sorted(PLAN_DIR.glob("*.json")):

        plan = read_json(file)

        if not isinstance(plan, dict):
            continue

        plan_id = plan.get("plan_id")
        dataset_id = plan.get("dataset_id")
        status = plan.get("status")

        valid = True

        if not valid_uuid(plan_id):
            add_issue(
                "PLAN UUID",
                f"Invalid plan ID in {file.name}",
            )
            continue

        if plan_id != file.stem:
            add_issue(
                "PLAN ID",
                f"Plan ID does not match filename: {file.name}",
            )
            valid = False

        if plan_id in plans:
            add_issue(
                "DUPLICATE PLAN",
                f"Duplicate plan ID: {plan_id}",
            )
            continue

        if not valid_uuid(dataset_id):
            add_issue(
                "PLAN DATASET",
                f"Invalid dataset ID in plan {plan_id}",
            )
            valid = False

        elif dataset_id not in datasets:
            add_warning(
                "ORPHANED PLAN",
                f"Plan {plan_id} references missing dataset {dataset_id}",
            )
            valid = False

        elif datasets[dataset_id]["storage_location"] != "raw":
            add_issue(
                "PLAN SOURCE",
                f"Plan {plan_id} does not reference an original dataset",
            )
            valid = False

        if status not in VALID_PLAN_STATUSES:
            add_issue(
                "PLAN STATUS",
                f"Invalid status in plan {plan_id}: {status}",
            )
            valid = False

        if not isinstance(plan.get("source_filename"), str):
            add_issue(
                "PLAN SOURCE",
                f"Missing source filename in plan {plan_id}",
            )
            valid = False

        if not isinstance(plan.get("source_fingerprint"), str):
            add_issue(
                "PLAN FINGERPRINT",
                f"Invalid source fingerprint in plan {plan_id}",
            )
            valid = False

        if not isinstance(plan.get("operations"), list):
            add_issue(
                "PLAN OPERATIONS",
                f"Invalid operations in plan {plan_id}",
            )
            valid = False

        if not isinstance(plan.get("preview"), dict):
            add_issue(
                "PLAN PREVIEW",
                f"Invalid preview in plan {plan_id}",
            )
            valid = False

        if not valid_timestamp(plan.get("created_at")):
            add_issue(
                "PLAN TIMESTAMP",
                f"Invalid created_at in plan {plan_id}",
            )
            valid = False

        if status in {"approved", "executed"}:
            if not valid_timestamp(plan.get("approved_at")):
                add_issue(
                    "PLAN TIMESTAMP",
                    f"Invalid approved_at in plan {plan_id}",
                )
                valid = False

        if status == "executed":

            cleaned_id = plan.get("cleaned_dataset_id")

            if not valid_uuid(cleaned_id):
                add_issue(
                    "EXECUTION DATASET",
                    f"Invalid cleaned dataset ID in plan {plan_id}",
                )
                valid = False

            elif (
                cleaned_id not in datasets
                or datasets[cleaned_id]["storage_location"] != "processed"
            ):
                add_issue(
                    "EXECUTION DATASET",
                    f"Cleaned dataset missing for plan {plan_id}",
                )
                valid = False

            if not valid_timestamp(plan.get("executed_at")):
                add_issue(
                    "EXECUTION TIMESTAMP",
                    f"Invalid executed_at in plan {plan_id}",
                )
                valid = False

            results = plan.get("execution_results")

            if not isinstance(results, (list, dict)):
                add_issue(
                    "EXECUTION RESULTS",
                    f"Invalid execution_results in plan {plan_id}",
                )
                valid = False

            metrics = plan.get("output_metrics")

            if not isinstance(metrics, dict):
                add_issue(
                    "EXECUTION METRICS",
                    f"Invalid output_metrics in plan {plan_id}",
                )
                valid = False

            if valid:
                output_filename = plan.get("output_filename")

                if not output_filename:
                    output_filename = datasets[cleaned_id]["stored_filename"]

                    add_warning(
                        "OUTPUT FILENAME",
                        f"Derived filename for plan {plan_id}: {output_filename}",
                    )

                executions.append({
                    "plan_id": plan_id,
                    "dataset_id": dataset_id,
                    "cleaned_dataset_id": cleaned_id,
                    "execution_results": results,
                    "output_metrics": metrics,
                    "output_filename": output_filename,
                    "executed_at": plan["executed_at"],
                })

        if valid:
            plans[plan_id] = plan

    print("Valid cleaning plans:", len(plans))
    print("Valid execution records:", len(executions))


# ============================================================
# 7. INSPECT DATASET VERSION REGISTRIES
# ============================================================

def inspect_version_registries():

    print("\n========== VERSION REGISTRIES ==========")

    if not VERSION_DIR.is_dir():
        add_issue(
            "DIRECTORY",
            f"Version registry directory missing: {VERSION_DIR}",
        )
        return

    seen_dataset_versions = set()
    seen_cleaning_plans = set()

    for file in sorted(VERSION_DIR.glob("*.json")):

        registry = read_json(file)

        if not isinstance(registry, dict):
            continue

        original_id = registry.get("original_dataset_id")
        registry_versions = registry.get("versions")

        if not valid_uuid(original_id):
            add_issue(
                "VERSION REGISTRY",
                f"Invalid original dataset ID: {file.name}",
            )
            continue

        if file.stem != original_id:
            add_issue(
                "VERSION REGISTRY",
                f"Registry filename does not match original ID: {file.name}",
            )
            continue

        if original_id not in datasets:
            add_issue(
                "VERSION REGISTRY",
                f"Original dataset missing: {original_id}",
            )
            continue

        if datasets[original_id]["storage_location"] != "raw":
            add_issue(
                "VERSION REGISTRY",
                f"Original ID is not stored in raw: {original_id}",
            )
            continue

        if not isinstance(registry_versions, list):
            add_issue(
                "VERSION REGISTRY",
                f"Invalid versions list: {file.name}",
            )
            continue

        registry_valid = True
        local_versions = []

        for version in registry_versions:

            if not isinstance(version, dict):
                add_issue(
                    "VERSION ENTRY",
                    f"Invalid version entry in {file.name}",
                )
                registry_valid = False
                continue

            dataset_id = version.get("dataset_id")
            version_number = version.get("version_number")
            version_type = version.get("version_type")

            if not valid_uuid(dataset_id) or dataset_id not in datasets:
                add_issue(
                    "VERSION DATASET",
                    f"Missing or invalid version dataset: {dataset_id}",
                )
                registry_valid = False
                continue

            if type(version_number) is not int or version_number < 0:
                add_issue(
                    "VERSION NUMBER",
                    f"Invalid version number for {dataset_id}",
                )
                registry_valid = False

            if version_type not in {"original", "cleaned"}:
                add_issue(
                    "VERSION TYPE",
                    f"Invalid version type for {dataset_id}",
                )
                registry_valid = False

            expected_location = (
                "raw" if version_type == "original" else "processed"
            )

            if datasets[dataset_id]["storage_location"] != expected_location:
                add_issue(
                    "VERSION LOCATION",
                    f"Incorrect storage location for version {dataset_id}",
                )
                registry_valid = False

            if not isinstance(version.get("filename"), str):
                add_issue(
                    "VERSION FILENAME",
                    f"Invalid filename for version {dataset_id}",
                )
                registry_valid = False

            if not valid_timestamp(version.get("created_at")):
                add_issue(
                    "VERSION TIMESTAMP",
                    f"Invalid timestamp for version {dataset_id}",
                )
                registry_valid = False

            if version_type == "original":
                if dataset_id != original_id or version_number != 0:
                    add_issue(
                        "ORIGINAL VERSION",
                        f"Invalid original version relationship: {dataset_id}",
                    )
                    registry_valid = False

            cleaning_plan_id = version.get("cleaning_plan_id")
            parent_id = version.get("parent_dataset_id")

            if cleaning_plan_id is not None:

                if (
                    not valid_uuid(cleaning_plan_id)
                    or cleaning_plan_id not in plans
                ):
                    add_issue(
                        "VERSION PLAN",
                        f"Invalid cleaning plan reference: {cleaning_plan_id}",
                    )
                    registry_valid = False

            if parent_id is not None:
                if not valid_uuid(parent_id) or parent_id not in datasets:
                    add_issue(
                        "VERSION PARENT",
                        f"Invalid parent dataset: {parent_id}",
                    )
                    registry_valid = False

            key = (original_id, version_number)

            if key in seen_dataset_versions:
                add_issue(
                    "DUPLICATE VERSION",
                    f"Duplicate version number: {key}",
                )
                registry_valid = False

            if dataset_id in seen_cleaning_plans:
                add_issue(
                    "DUPLICATE VERSION DATASET",
                    f"Dataset appears in multiple version entries: {dataset_id}",
                )
                registry_valid = False

            if cleaning_plan_id is not None:
                if cleaning_plan_id in seen_cleaning_plans:
                    add_issue(
                        "DUPLICATE VERSION PLAN",
                        f"Cleaning plan used by multiple versions: {cleaning_plan_id}",
                    )
                    registry_valid = False

            local_versions.append(version)

        if registry_valid:
            for version in local_versions:

                key = (
                    original_id,
                    version["version_number"],
                )

                seen_dataset_versions.add(key)
                seen_cleaning_plans.add(version["dataset_id"])

                if version.get("cleaning_plan_id") is not None:
                    seen_cleaning_plans.add(
                        version["cleaning_plan_id"]
                    )

                versions.append({
                    **version,
                    "original_dataset_id": original_id,
                })

    print("Valid version entries:", len(versions))


# ============================================================
# 8. GENERATE MIGRATION REPORT
# ============================================================

def generate_report():

    print("\n" + "=" * 60)
    print("INSIGHTFORGE AI — MIGRATION PREFLIGHT REPORT")
    print("=" * 60)

    print("\nDISCOVERED DATASETS")

    print(
        "Original datasets:",
        sum(
            item["storage_location"] == "raw"
            for item in datasets.values()
        ),
    )

    print(
        "Cleaned datasets:",
        sum(
            item["storage_location"] == "processed"
            for item in datasets.values()
        ),
    )

    print("Total datasets:", len(datasets))

    print("\nMIGRATION CANDIDATES")

    print("Datasets:", len(datasets))
    print("Cleaning plans:", len(plans))
    print("Dataset versions:", len(versions))
    print("Cleaning executions:", len(executions))

    print("\nVALIDATION SUMMARY")

    print("Errors:", len(issues))
    print("Warnings:", len(warnings))

    print("\nISSUES")

    if not issues:
        print("No validation errors.")

    for issue in issues:
        print(
            f"[{issue['category']}] {issue['message']}"
        )

    print("\nWARNINGS")

    if not warnings:
        print("No warnings.")

    for warning in warnings:
        print(
            f"[{warning['category']}] {warning['message']}"
        )

    print("\nMIGRATION READINESS")

    if issues:
        print("NOT READY — Resolve validation errors first.")

    elif warnings:
        print("REVIEW REQUIRED — Warnings must be reviewed.")

    else:
        print("READY FOR MIGRATION REVIEW.")

    print("\nIMPORTANT")
    print("This script did not modify any project files.")
    print("This script did not insert or modify PostgreSQL records.")
    print("=" * 60)


# ============================================================
# 9. EXECUTION
# ============================================================

if __name__ == "__main__":

    print("Starting read-only migration preflight...")

    inspect_original_datasets()

    inspect_cleaned_datasets()

    inspect_cleaning_plans()

    inspect_version_registries()

    generate_report()