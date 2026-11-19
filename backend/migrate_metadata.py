"""
InsightForge AI metadata migration.

Run from the backend directory:
    python migrate_metadata.py --dry-run
    python migrate_metadata.py --apply

Migrates filesystem metadata into PostgreSQL without modifying source JSON/CSV files.
Existing rows are accepted only when their stored values match the migration candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CleaningExecution, CleaningPlan, Dataset, DatasetVersion
from app.services.cleaning_plans import calculate_file_fingerprint
from app.services.settings import settings


RAW_DIR = settings.upload_dir.resolve()
PROCESSED_DIR = settings.processed_dir.resolve()
PLAN_DIR = PROCESSED_DIR / "cleaning_plans"
VERSION_DIR = (settings.upload_dir.parent / "metadata" / "dataset_versions").resolve()
SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


def parse_datetime(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed


def parse_uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid UUID in {field}: {value!r}") from exc


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def discover_datasets() -> tuple[dict[UUID, dict[str, Any]], dict[UUID, Path]]:
    candidates: dict[UUID, dict[str, Any]] = {}
    physical_files: dict[UUID, Path] = {}

    for sidecar in sorted(RAW_DIR.glob("*.json")):
        metadata = read_json(sidecar)
        dataset_id = parse_uuid(sidecar.stem, f"sidecar filename {sidecar.name}")
        original_filename = metadata.get("filename")
        if not isinstance(original_filename, str) or not original_filename.strip():
            raise ValueError(f"Missing original filename in {sidecar}")

        matches = [
            RAW_DIR / f"{dataset_id}{extension}"
            for extension in SUPPORTED_EXTENSIONS
            if (RAW_DIR / f"{dataset_id}{extension}").is_file()
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one raw file for {dataset_id}; found {len(matches)}"
            )

        physical = matches[0]
        candidates[dataset_id] = {
            "id": dataset_id,
            "filename": original_filename,
            "stored_filename": physical.name,
            "storage_location": "raw",
        }
        physical_files[dataset_id] = physical

    for physical in sorted(PROCESSED_DIR.iterdir()):
        if not physical.is_file() or physical.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        dataset_id = parse_uuid(physical.stem, f"processed filename {physical.name}")
        if dataset_id in candidates:
            raise ValueError(f"Dataset ID appears in both raw and processed storage: {dataset_id}")
        candidates[dataset_id] = {
            "id": dataset_id,
            "filename": physical.name,
            "stored_filename": physical.name,
            "storage_location": "processed",
        }
        physical_files[dataset_id] = physical

    return candidates, physical_files


def discover_plans(
    datasets: dict[UUID, dict[str, Any]],
    physical_files: dict[UUID, Path],
) -> tuple[dict[UUID, dict[str, Any]], dict[UUID, dict[str, Any]]]:
    plans: dict[UUID, dict[str, Any]] = {}
    executions: dict[UUID, dict[str, Any]] = {}

    for path in sorted(PLAN_DIR.glob("*.json")):
        raw = read_json(path)
        if raw.get("status") != "executed":
            continue

        plan_id = parse_uuid(raw.get("plan_id"), f"{path.name}: plan_id")
        dataset_id = parse_uuid(raw.get("dataset_id"), f"{path.name}: dataset_id")
        cleaned_id = parse_uuid(raw.get("cleaned_dataset_id"), f"{path.name}: cleaned_dataset_id")

        if plan_id in plans:
            raise ValueError(f"Duplicate executed cleaning plan ID: {plan_id}")
        if dataset_id not in datasets or datasets[dataset_id]["storage_location"] != "raw":
            raise ValueError(f"Executed plan {plan_id} references an unknown original dataset")
        if cleaned_id not in datasets or datasets[cleaned_id]["storage_location"] != "processed":
            raise ValueError(f"Executed plan {plan_id} references an unknown cleaned dataset")

        source_filename = raw.get("source_filename")
        if not isinstance(source_filename, str):
            raise ValueError(f"Plan {plan_id} has no source_filename")
        source_path = RAW_DIR / source_filename
        if not source_path.is_file() or source_path.resolve() != physical_files[dataset_id].resolve():
            raise ValueError(f"Plan {plan_id} source_filename does not resolve to its original dataset")

        expected_fingerprint = raw.get("source_fingerprint")
        if not expected_fingerprint or calculate_file_fingerprint(source_path) != expected_fingerprint:
            raise ValueError(f"Source fingerprint mismatch for cleaning plan {plan_id}")

        cleaned_path = physical_files[cleaned_id]
        output_filename = raw.get("output_filename") or cleaned_path.name
        if output_filename != cleaned_path.name:
            raise ValueError(f"Output filename mismatch for cleaning plan {plan_id}")

        execution_results = raw.get("execution_results")
        output_metrics = raw.get("output_metrics")
        if not isinstance(execution_results, (list, dict)):
            raise ValueError(f"Invalid execution_results for cleaning plan {plan_id}")
        if not isinstance(output_metrics, dict):
            raise ValueError(f"Invalid output_metrics for cleaning plan {plan_id}")

        created_at = parse_datetime(raw.get("created_at"), f"{plan_id}.created_at")
        executed_at = parse_datetime(raw.get("executed_at"), f"{plan_id}.executed_at")
        approved_at = parse_datetime(raw.get("approved_at"), f"{plan_id}.approved_at")
        if created_at is None or executed_at is None or approved_at is None:
            raise ValueError(f"Executed plan {plan_id} is missing a required timestamp")

        if not isinstance(raw.get("operations"), list) or not isinstance(raw.get("preview"), dict):
            raise ValueError(f"Invalid operations/preview structure for cleaning plan {plan_id}")

        plans[plan_id] = {
            "plan_id": plan_id,
            "dataset_id": dataset_id,
            "source_filename": source_filename,
            "source_fingerprint": expected_fingerprint,
            "operations": raw["operations"],
            "preview": raw["preview"],
            "status": "executed",
            "cleaned_dataset_id": cleaned_id,
            "execution_results": execution_results,
            "output_metrics": output_metrics,
            "output_filename": output_filename,
            "created_at": created_at,
            "approved_at": approved_at,
            "executed_at": executed_at,
        }
        executions[plan_id] = {
            "plan_id": plan_id,
            "dataset_id": dataset_id,
            "cleaned_dataset_id": cleaned_id,
            "execution_results": execution_results,
            "output_metrics": output_metrics,
            "output_filename": output_filename,
            "executed_at": executed_at,
        }

    return plans, executions


def discover_versions(
    datasets: dict[UUID, dict[str, Any]],
    plans: dict[UUID, dict[str, Any]],
) -> dict[UUID, dict[str, Any]]:
    versions: dict[UUID, dict[str, Any]] = {}
    seen_numbers: set[tuple[UUID, int]] = set()
    seen_plan_ids: set[UUID] = set()

    for path in sorted(VERSION_DIR.glob("*.json")):
        registry = read_json(path)
        original_id = parse_uuid(
            registry.get("original_dataset_id"), f"{path.name}.original_dataset_id"
        )
        if original_id not in datasets or datasets[original_id]["storage_location"] != "raw":
            raise ValueError(f"Version registry {path.name} references an unknown original dataset")

        entries = registry.get("versions")
        if not isinstance(entries, list):
            raise ValueError(f"Invalid versions array in {path.name}")

        original_entries = 0
        for entry in entries:
            dataset_id = parse_uuid(entry.get("dataset_id"), f"{path.name}.dataset_id")
            version_number = entry.get("version_number")
            version_type = entry.get("version_type")
            if not isinstance(version_number, int) or version_number < 0:
                raise ValueError(f"Invalid version_number in {path.name}")
            if version_type not in {"original", "cleaned"}:
                raise ValueError(f"Invalid version_type in {path.name}")
            if dataset_id not in datasets:
                raise ValueError(f"Version entry references unknown dataset {dataset_id}")

            number_key = (original_id, version_number)
            if number_key in seen_numbers:
                raise ValueError(f"Duplicate version number {version_number} for {original_id}")
            seen_numbers.add(number_key)

            cleaning_plan_id = (
                parse_uuid(entry["cleaning_plan_id"], f"{path.name}.cleaning_plan_id")
                if entry.get("cleaning_plan_id") else None
            )
            parent_id = (
                parse_uuid(entry["parent_dataset_id"], f"{path.name}.parent_dataset_id")
                if entry.get("parent_dataset_id") else None
            )

            if version_type == "original":
                original_entries += 1
                if dataset_id != original_id or version_number != 0 or cleaning_plan_id is not None:
                    raise ValueError(f"Invalid original version entry in {path.name}")
            else:
                if version_number == 0 or parent_id != original_id or cleaning_plan_id is None:
                    raise ValueError(f"Invalid cleaned version relationship in {path.name}")
                if cleaning_plan_id not in plans:
                    raise ValueError(f"Version entry references unknown executed plan {cleaning_plan_id}")
                plan = plans[cleaning_plan_id]
                if plan["dataset_id"] != original_id or plan["cleaned_dataset_id"] != dataset_id:
                    raise ValueError(f"Version/cleaning-plan relationship mismatch in {path.name}")
                if cleaning_plan_id in seen_plan_ids:
                    raise ValueError(f"Duplicate version entry for cleaning plan {cleaning_plan_id}")
                seen_plan_ids.add(cleaning_plan_id)

            created_at = parse_datetime(entry.get("created_at"), f"{path.name}.created_at")
            if created_at is None:
                raise ValueError(f"Missing version timestamp in {path.name}")
            filename = entry.get("filename")
            if not isinstance(filename, str):
                raise ValueError(f"Missing version filename for dataset {dataset_id}")
            if dataset_id in versions:
                raise ValueError(f"Duplicate dataset version entry for dataset {dataset_id}")

            versions[dataset_id] = {
                "dataset_id": dataset_id,
                "original_dataset_id": original_id,
                "version_number": version_number,
                "version_type": version_type,
                "filename": filename,
                "cleaning_plan_id": cleaning_plan_id,
                "parent_dataset_id": parent_id,
                "created_at": created_at,
            }

        if original_entries != 1:
            raise ValueError(f"Expected exactly one original version entry in {path.name}")

    return versions


def same_values(existing: Any, candidate: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(getattr(existing, field) == candidate[field] for field in fields)


def upsert_checked(
    session: Session,
    model: Any,
    primary_key: str,
    candidate: dict[str, Any],
    compare_fields: tuple[str, ...],
    apply: bool,
) -> str:
    existing = session.get(model, candidate[primary_key])
    if existing is not None:
        if not same_values(existing, candidate, compare_fields):
            raise ValueError(
                f"Existing {model.__tablename__} record {candidate[primary_key]} "
                "conflicts with filesystem metadata"
            )
        return "existing"
    if apply:
        session.add(model(**candidate))
        session.flush()
    return "would_insert"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate InsightForge filesystem metadata to PostgreSQL.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    print("Building and validating migration candidates...")
    datasets, physical_files = discover_datasets()
    plans, executions = discover_plans(datasets, physical_files)
    versions = discover_versions(datasets, plans)

    actual = (len(datasets), len(plans), len(versions), len(executions))
    expected = (47, 5, 3, 5)
    print("\n========== MIGRATION CANDIDATES ==========")
    print(f"Datasets: {actual[0]}")
    print(f"Cleaning plans: {actual[1]}")
    print(f"Dataset versions: {actual[2]}")
    print(f"Cleaning executions: {actual[3]}")
    # Counts are reported for this migration run, not enforced as fixed limits.
    # Future uploads and cleaned datasets are not capped by this one-time script.

    stages = [
        (Dataset, "id", list(datasets.values()),
         ("filename", "stored_filename", "storage_location"), "datasets"),
        (CleaningPlan, "plan_id", list(plans.values()),
         ("dataset_id", "source_filename", "source_fingerprint", "operations", "preview",
          "status", "cleaned_dataset_id", "execution_results", "output_metrics",
          "output_filename", "created_at", "approved_at", "executed_at"), "cleaning_plans"),
        (DatasetVersion, "dataset_id", list(versions.values()),
         ("original_dataset_id", "version_number", "version_type", "filename",
          "cleaning_plan_id", "parent_dataset_id", "created_at"), "dataset_versions"),
        (CleaningExecution, "plan_id", list(executions.values()),
         ("dataset_id", "cleaned_dataset_id", "execution_results", "output_metrics",
          "output_filename", "executed_at"), "cleaning_executions"),
    ]

    counts = {label: {"to_insert": 0, "already_matching": 0} for *_, label in stages}

    print("\nChecking PostgreSQL...")
    with SessionLocal() as session:
        try:
            with session.begin():
                for model, primary_key, rows, fields, label in stages:
                    for candidate in rows:
                        result = upsert_checked(
                            session, model, primary_key, candidate, fields, args.apply
                        )
                        counts[label]["to_insert" if result == "would_insert" else "already_matching"] += 1

            if args.dry_run:
                print("\nDRY RUN successful. No records were inserted.")
            else:
                print("\nMigration committed successfully.")
        except Exception:
            session.rollback()
            raise

    print("\n========== RESULT ==========")
    for label, values in counts.items():
        print(f"{label}: pending_insert={values['to_insert']}, already_matching={values['already_matching']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nMIGRATION STOPPED: {exc}", file=sys.stderr)
        raise SystemExit(1)
