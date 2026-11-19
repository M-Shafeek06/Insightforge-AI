import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AnalyticsExecution
from app.schemas.ai_interpretation import AIInterpretationResponse
from app.services.ai_results_interpreter import (
    interpret_analytics_results_async,
)
from app.services.request_cancellation import await_or_cancel_on_disconnect


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/datasets",
    tags=["AI Results Interpretation"],
)


@router.post(
    "/{dataset_id}/executions/{execution_id}/interpret",
    response_model=AIInterpretationResponse,
)
async def interpret_saved_execution(
    dataset_id: UUID,
    execution_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Interpret an existing analytics execution using the configured
    AI provider with sequential fallback.

    The original execution and saved-analysis state remain unchanged.
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

    try:
        interpretation = await await_or_cancel_on_disconnect(
            request,
            interpret_analytics_results_async(
                operation=execution.operation,
                request_config=execution.request_config,
                result=execution.result,
            ),
        )

        execution.ai_interpretation = interpretation
        db.add(execution)
        db.commit()
        db.refresh(execution)

    except asyncio.CancelledError:
        db.rollback()
        raise

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()

        logger.exception(
            "AI Results Interpretation failed for execution %s",
            execution_id,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The AI Results Interpreter could not complete "
                "the request. Check backend logs for details."
            ),
        ) from exc

    return AIInterpretationResponse(
        dataset_id=dataset_id,
        execution_id=execution_id,
        ai_assisted=True,
        **interpretation,
    )