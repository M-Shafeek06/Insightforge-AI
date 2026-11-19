from __future__ import annotations

import os
import tempfile

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    DatasetVersion,
    CleaningPlan,
    CleaningExecution,
)

from app.data.loaders.tabular import load_tabular_file

from app.services.cleaning import (
    apply_cleaning_operations,
    dataset_metrics,
)

from app.services.cleaning_plans import (
    calculate_file_fingerprint,
    cleaning_plan_lock,
    load_cleaning_plan,
    save_cleaning_plan,
)

from app.services.dataset_versions import (
    ensure_original_dataset_registered,
    get_dataset_versions,
    register_cleaned_version,
    unregister_cleaned_version,
)

from app.services.settings import settings
from app.services.storage import resolve_dataset_path


class CleaningExecutionError(ValueError):
    """Raised when an approved cleaning plan cannot be executed."""


def save_cleaned_dataset(
    df: pd.DataFrame,
    extension: str,
) -> tuple[str, Path]:
    """Save a cleaned dataset atomically without modifying its source."""

    extension = extension.lower()

    if extension not in {".csv", ".xlsx"}:
        raise CleaningExecutionError(
            f"Unsupported output format: {extension}"
        )

    settings.processed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cleaned_dataset_id = str(uuid4())

    output_path = (
        settings.processed_dir
        / f"{cleaned_dataset_id}{extension}"
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=extension,
            dir=settings.processed_dir,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        if extension == ".csv":
            df.to_csv(
                temporary_path,
                index=False,
            )
        else:
            df.to_excel(
                temporary_path,
                index=False,
            )

        os.replace(
            temporary_path,
            output_path,
        )

        return cleaned_dataset_id, output_path

    except Exception as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

        output_path.unlink(missing_ok=True)

        raise CleaningExecutionError(
            "Unable to save the cleaned dataset."
        ) from exc


def execute_cleaning_plan(
    dataset_id: str,
    plan_id: str,
    db: Session | None = None,
) -> dict:
    """Execute an approved cleaning plan and persist its output."""

    try:
        validated_dataset_id = str(UUID(dataset_id))
        validated_plan_id = str(UUID(plan_id))

    except ValueError as exc:
        raise CleaningExecutionError(
            "Invalid dataset or cleaning plan identifier."
        ) from exc

    with cleaning_plan_lock(validated_plan_id):

        try:
            plan = load_cleaning_plan(validated_plan_id)

        except (ValueError, FileNotFoundError) as exc:
            raise CleaningExecutionError(
                "Cleaning plan not found or invalid."
            ) from exc

        if plan.get("dataset_id") != validated_dataset_id:
            raise CleaningExecutionError(
                "Cleaning plan does not belong to this dataset."
            )

        if plan.get("status") != "approved":
            raise CleaningExecutionError(
                "Only approved cleaning plans can be executed."
            )

        source_filename = plan.get("source_filename")

        if not source_filename:
            raise CleaningExecutionError(
                "The original dataset filename is missing from the plan."
            )

        # --------------------------------------------------
        # 1. RESOLVE SOURCE DATASET
        # --------------------------------------------------

        try:
            source_path = resolve_dataset_path(
                validated_dataset_id
            )

        except (FileNotFoundError, ValueError) as exc:
            raise CleaningExecutionError(
                "Source dataset could not be located."
            ) from exc

        if source_path.name != source_filename:
            raise CleaningExecutionError(
                "Source dataset does not match the approved cleaning plan."
            )

        try:
            current_fingerprint = calculate_file_fingerprint(
                source_path
            )

        except OSError as exc:
            raise CleaningExecutionError(
                "Unable to verify the source dataset."
            ) from exc

        if current_fingerprint != plan.get("source_fingerprint"):
            raise CleaningExecutionError(
                "Source dataset has changed since the cleaning plan was approved."
            )

        # --------------------------------------------------
        # 2. VERIFY POSTGRESQL METADATA
        # --------------------------------------------------

        db_backed = False
        db_plan = None

        if db is not None:

            db_dataset = db.get(
                Dataset,
                UUID(validated_dataset_id),
            )

            if db_dataset is not None:

                db_backed = True

                db_plan = db.get(
                    CleaningPlan,
                    UUID(validated_plan_id),
                )

                if db_plan is None:
                    raise CleaningExecutionError(
                        "Cleaning plan metadata not found in PostgreSQL."
                    )

                if db_plan.dataset_id != UUID(validated_dataset_id):
                    raise CleaningExecutionError(
                        "PostgreSQL cleaning plan belongs to another dataset."
                    )

                if db_plan.status != "approved":
                    raise CleaningExecutionError(
                        "PostgreSQL cleaning plan is not approved."
                    )

                if (
                    db_plan.source_fingerprint
                    != plan.get("source_fingerprint")
                ):
                    raise CleaningExecutionError(
                        "PostgreSQL cleaning plan fingerprint does not match."
                    )

        # --------------------------------------------------
        # 3. EXECUTE CLEANING OPERATIONS
        # --------------------------------------------------

        try:
            original_df = load_tabular_file(source_path)

            cleaned_df, operation_results = apply_cleaning_operations(
                original_df,
                plan.get("operations", []),
            )

        except Exception as exc:
            raise CleaningExecutionError(
                f"Cleaning execution failed: {exc}"
            ) from exc

        original_metrics = dataset_metrics(original_df)
        cleaned_metrics = dataset_metrics(cleaned_df)

        # --------------------------------------------------
        # 4. SAVE CLEANED DATASET
        # --------------------------------------------------

        cleaned_dataset_id, output_path = save_cleaned_dataset(
            cleaned_df,
            source_path.suffix,
        )

        registered = False
        original_plan = plan.copy()
        root_original_dataset_id = None

        try:

            # --------------------------------------------------
            # 5. RESOLVE ROOT VERSION LINEAGE
            # --------------------------------------------------

            try:
                registry = get_dataset_versions(
                    validated_dataset_id
                )

            except FileNotFoundError:
                # A dataset without a registry is treated as
                # the original V0 dataset.
                ensure_original_dataset_registered(
                    dataset_id=validated_dataset_id,
                    filename=source_path.name,
                )

                registry = get_dataset_versions(
                    validated_dataset_id
                )

            root_original_dataset_id = str(
                UUID(registry["original_dataset_id"])
            )

            # --------------------------------------------------
            # 6. REGISTER NEW VERSION
            # --------------------------------------------------

            registry = register_cleaned_version(
                original_dataset_id=validated_dataset_id,
                cleaned_dataset_id=cleaned_dataset_id,
                cleaning_plan_id=validated_plan_id,
                filename=output_path.name,
            )

            registered = True

            version_entry = next(
                (
                    version
                    for version in registry["versions"]
                    if version["dataset_id"] == cleaned_dataset_id
                ),
                None,
            )

            if version_entry is None:
                raise CleaningExecutionError(
                    "Cleaned dataset version registration failed."
                )

            executed_at = datetime.now(
                timezone.utc
            ).isoformat()

            executed_datetime = datetime.fromisoformat(
                executed_at
            )

            execution_results = {
                "operations": operation_results,
                "before": original_metrics,
                "after": cleaned_metrics,
            }

            # --------------------------------------------------
            # 7. UPDATE JSON CLEANING PLAN
            # --------------------------------------------------

            plan["status"] = "executed"
            plan["executed_at"] = executed_at
            plan["cleaned_dataset_id"] = cleaned_dataset_id
            plan["execution_results"] = execution_results
            plan["output_metrics"] = cleaned_metrics
            plan["output_filename"] = output_path.name

            save_cleaning_plan(plan)

            # --------------------------------------------------
            # 8. PERSIST POSTGRESQL METADATA
            # --------------------------------------------------

            if db_backed:

                cleaned_dataset = Dataset(
                    id=UUID(cleaned_dataset_id),
                    filename=output_path.name,
                    stored_filename=output_path.name,
                    storage_location="processed",
                )

                db.add(cleaned_dataset)
                db.flush()

                db_plan.status = "executed"
                db_plan.cleaned_dataset_id = UUID(
                    cleaned_dataset_id
                )
                db_plan.execution_results = execution_results
                db_plan.output_metrics = cleaned_metrics
                db_plan.output_filename = output_path.name
                db_plan.executed_at = executed_datetime

                cleaned_version = DatasetVersion(
                    dataset_id=UUID(cleaned_dataset_id),
                    original_dataset_id=UUID(
                        root_original_dataset_id
                    ),
                    version_number=version_entry["version_number"],
                    version_type="cleaned",
                    filename=output_path.name,
                    cleaning_plan_id=UUID(validated_plan_id),
                    parent_dataset_id=UUID(
                        validated_dataset_id
                    ),
                    created_at=datetime.fromisoformat(
                        version_entry["created_at"]
                    ),
                )

                db.add(cleaned_version)

                cleaning_execution = CleaningExecution(
                    plan_id=UUID(validated_plan_id),
                    dataset_id=UUID(validated_dataset_id),
                    cleaned_dataset_id=UUID(
                        cleaned_dataset_id
                    ),
                    execution_results=execution_results,
                    output_metrics=cleaned_metrics,
                    output_filename=output_path.name,
                    executed_at=executed_datetime,
                )

                db.add(cleaning_execution)

                db.commit()

            # --------------------------------------------------
            # 9. RETURN EXECUTION RESULT
            # --------------------------------------------------

            return {
                "status": "executed",
                "dataset_id": validated_dataset_id,
                "plan_id": validated_plan_id,
                "cleaned_dataset_id": cleaned_dataset_id,
                "output_filename": output_path.name,
                "original_rows": original_metrics["rows"],
                "cleaned_rows": cleaned_metrics["rows"],
                "execution_results": operation_results,
                "original_metrics": original_metrics,
                "cleaned_metrics": cleaned_metrics,
                "executed_at": executed_at,
            }

        except Exception as exc:

            # --------------------------------------------------
            # 10. ROLLBACK ON FAILURE
            # --------------------------------------------------

            if db is not None:
                db.rollback()

            if registered and root_original_dataset_id is not None:
                try:
                    unregister_cleaned_version(
                        original_dataset_id=root_original_dataset_id,
                        cleaned_dataset_id=cleaned_dataset_id,
                        cleaning_plan_id=validated_plan_id,
                    )
                except Exception:
                    pass

            try:
                save_cleaning_plan(original_plan)
            except Exception:
                pass

            output_path.unlink(missing_ok=True)

            if isinstance(exc, CleaningExecutionError):
                raise

            raise CleaningExecutionError(
                "Unable to complete and register the cleaning execution."
            ) from exc