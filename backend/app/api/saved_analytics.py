from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AnalyticsExecution,
    Dataset,
    SavedAnalytics,
)

from app.schemas.saved_analytics import (
    SavedAnalyticsItem,
    SavedAnalyticsListResponse,
    SavedAnalyticsResponse,
)


router = APIRouter(
    prefix="/datasets",
    tags=["Saved Analytics"],
)


def get_dataset_execution(
    db: Session,
    dataset_id: UUID,
    execution_id: UUID,
) -> AnalyticsExecution:
    """
    Retrieve an execution only when it belongs to the requested dataset.
    """

    execution = db.scalar(
        select(AnalyticsExecution).where(
            AnalyticsExecution.execution_id == execution_id,
            AnalyticsExecution.dataset_id == dataset_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Analytics execution not found for this dataset.",
        )

    return execution


# ============================================================
# SAVE ANALYTICS
# ============================================================

@router.post(
    "/{dataset_id}/executions/{execution_id}/save",
    response_model=SavedAnalyticsResponse,
)
def save_analytics(
    dataset_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Save an analytics execution for future report generation.

    Repeated save requests do not create duplicate records.
    """

    execution = get_dataset_execution(
        db,
        dataset_id,
        execution_id,
    )

    existing = db.get(SavedAnalytics, execution_id)

    if existing is not None:
        return SavedAnalyticsResponse(
            execution_id=execution_id,
            dataset_id=dataset_id,
            saved=True,
            saved_at=existing.saved_at,
            message="Analytics execution is already saved.",
        )

    saved_record = SavedAnalytics(
        execution_id=execution_id,
    )

    try:
        db.add(saved_record)
        db.commit()
        db.refresh(saved_record)

    except Exception:
        db.rollback()
        raise

    return SavedAnalyticsResponse(
        execution_id=execution_id,
        dataset_id=dataset_id,
        saved=True,
        saved_at=saved_record.saved_at,
        message="Analytics execution saved successfully.",
    )


# ============================================================
# UNSAVE ANALYTICS
# ============================================================

@router.delete(
    "/{dataset_id}/executions/{execution_id}/save",
    response_model=SavedAnalyticsResponse,
)
def unsave_analytics(
    dataset_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Remove an analytics execution from saved analytics.

    The original execution history remains untouched.
    """

    get_dataset_execution(
        db,
        dataset_id,
        execution_id,
    )

    saved_record = db.get(SavedAnalytics, execution_id)

    if saved_record is None:
        return SavedAnalyticsResponse(
            execution_id=execution_id,
            dataset_id=dataset_id,
            saved=False,
            message="Analytics execution is not currently saved.",
        )

    try:
        db.delete(saved_record)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return SavedAnalyticsResponse(
        execution_id=execution_id,
        dataset_id=dataset_id,
        saved=False,
        message="Analytics execution removed from saved analytics.",
    )


# ============================================================
# GET SAVED ANALYTICS
# ============================================================

@router.get(
    "/{dataset_id}/saved-analyses",
    response_model=SavedAnalyticsListResponse,
)
def get_saved_analytics(
    dataset_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Retrieve only explicitly saved analytics executions.
    """

    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    statement = (
        select(
            AnalyticsExecution,
            SavedAnalytics.saved_at,
        )
        .join(
            SavedAnalytics,
            AnalyticsExecution.execution_id
            == SavedAnalytics.execution_id,
        )
        .where(
            AnalyticsExecution.dataset_id == dataset_id,
        )
        .order_by(
            SavedAnalytics.saved_at.desc(),
        )
    )

    rows = db.execute(statement).all()

    saved_analyses = [
        SavedAnalyticsItem(
            execution_id=execution.execution_id,
            dataset_id=execution.dataset_id,
            operation=execution.operation,
            request_config=execution.request_config,
            result=execution.result,
            created_at=execution.created_at,
            saved_at=saved_at,
        )
        for execution, saved_at in rows
    ]

    return SavedAnalyticsListResponse(
        dataset_id=dataset_id,
        total=len(saved_analyses),
        saved_analyses=saved_analyses,
    )