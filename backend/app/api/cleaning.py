import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db

from app.data.loaders.tabular import load_tabular_file

from app.schemas.cleaning import (
    CleaningApprovalRequest,
    CleaningPreviewRequest,
)

from app.services.cleaning import (
    CleaningValidationError,
    generate_cleaning_preview,
)

from app.services.cleaning_plans import (
    approve_cleaning_plan,
    calculate_file_fingerprint,
    create_cleaning_plan,
)

from app.services.cleaning_execution import (
    CleaningExecutionError,
    execute_cleaning_plan,
)

from app.services.storage import resolve_dataset_path


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/datasets",
    tags=["cleaning"],
)


def resolve_cleaning_source(dataset_id: str):
    """
    Resolve the exact dataset version from raw or processed storage.
    """
    try:
        return resolve_dataset_path(dataset_id)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# 1. CLEANING PREVIEW
# --------------------------------------------------

@router.post("/{dataset_id}/cleaning-preview")
def preview_dataset_cleaning(
    dataset_id: str,
    request: CleaningPreviewRequest,
    db: Session = Depends(get_db),
) -> dict:

    try:
        validated_id = str(UUID(dataset_id))

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid dataset identifier.",
        ) from exc

    dataset_file = resolve_cleaning_source(validated_id)

    try:
        df = load_tabular_file(dataset_file)

        operations = [
            operation.model_dump(
                mode="json",
                exclude_none=True,
            )
            for operation in request.operations
        ]

        result = generate_cleaning_preview(
            df=df,
            operations=operations,
        )

        plan = create_cleaning_plan(
            dataset_id=validated_id,
            source_path=dataset_file,
            operations=operations,
            preview=result,
            db=db,
        )

        return {
            "dataset_id": validated_id,
            "plan_id": plan["plan_id"],
            "status": "preview_generated",
            "approval_status": plan["status"],
            **result,
        }

    except CleaningValidationError as exc:
        logger.warning(
            "Cleaning validation failed for dataset %s: %s",
            validated_id,
            str(exc),
        )

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Failed to generate cleaning preview for dataset %s",
            validated_id,
        )

        raise HTTPException(
            status_code=422,
            detail="Unable to generate cleaning preview.",
        ) from exc


# --------------------------------------------------
# 2. CLEANING PLAN APPROVAL
# --------------------------------------------------

@router.post("/{dataset_id}/cleaning-plans/{plan_id}/approve")
def approve_dataset_cleaning(
    dataset_id: str,
    plan_id: str,
    request: CleaningApprovalRequest,
    db: Session = Depends(get_db),
) -> dict:

    try:
        validated_dataset_id = str(UUID(dataset_id))
        validated_plan_id = str(UUID(plan_id))

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid dataset or cleaning plan identifier.",
        ) from exc

    dataset_file = resolve_cleaning_source(
        validated_dataset_id
    )

    try:
        current_fingerprint = calculate_file_fingerprint(
            dataset_file
        )

        plan = approve_cleaning_plan(
            dataset_id=validated_dataset_id,
            plan_id=validated_plan_id,
            current_fingerprint=current_fingerprint,
            db=db,
        )

        return {
            "dataset_id": validated_dataset_id,
            "plan_id": validated_plan_id,
            "status": "approved",
            "approved_at": plan["approved_at"],
            "message": "Cleaning plan approved successfully.",
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Cleaning plan not found.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Failed to approve cleaning plan %s for dataset %s",
            validated_plan_id,
            validated_dataset_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to approve cleaning plan.",
        ) from exc


# --------------------------------------------------
# 3. APPROVED CLEANING PLAN EXECUTION
# --------------------------------------------------

@router.post("/{dataset_id}/cleaning-plans/{plan_id}/execute")
def execute_dataset_cleaning(
    dataset_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
) -> dict:

    try:
        validated_dataset_id = str(UUID(dataset_id))
        validated_plan_id = str(UUID(plan_id))

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid dataset or cleaning plan identifier.",
        ) from exc

    try:
        result = execute_cleaning_plan(
            dataset_id=validated_dataset_id,
            plan_id=validated_plan_id,
            db=db,
        )

        return result

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except CleaningExecutionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Failed to execute cleaning plan %s for dataset %s",
            validated_plan_id,
            validated_dataset_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to execute cleaning plan.",
        ) from exc