from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AnalyticsExecution, Dataset

from app.schemas.analytics_history import (
    AnalyticsExecutionHistoryItem,
    AnalyticsExecutionHistoryResponse,
)


router = APIRouter(
    prefix="/datasets",
    tags=["Analytics History"],
)


@router.get(
    "/{dataset_id}/executions",
    response_model=AnalyticsExecutionHistoryResponse,
)
def get_analytics_execution_history(
    dataset_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Retrieve analytics execution history for a dataset.

    Results are ordered from newest to oldest.
    """

    # Verify that the dataset exists.
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    # Count all executions belonging to this dataset.
    total = db.scalar(
        select(func.count())
        .select_from(AnalyticsExecution)
        .where(
            AnalyticsExecution.dataset_id == dataset_id
        )
    )

    # Retrieve paginated execution history.
    executions = db.scalars(
        select(AnalyticsExecution)
        .where(
            AnalyticsExecution.dataset_id == dataset_id
        )
        .order_by(
            AnalyticsExecution.created_at.desc(),
            AnalyticsExecution.execution_id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return AnalyticsExecutionHistoryResponse(
        dataset_id=dataset_id,
        total=total or 0,
        limit=limit,
        offset=offset,
        executions=executions,
    )


@router.get(
    "/{dataset_id}/executions/{execution_id}",
    response_model=AnalyticsExecutionHistoryItem,
)
def get_analytics_execution_details(
    dataset_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Retrieve a specific analytics execution.

    The execution must belong to the requested dataset.
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
            detail="Analytics execution not found.",
        )

    return execution