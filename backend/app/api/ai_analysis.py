import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.schemas.analysis import AnalysisPlanningRequest
from app.services.ai_business_analyst import generate_business_analysis_async
from app.services.request_cancellation import await_or_cancel_on_disconnect
from app.services.analysis_planner import plan_dataset_analysis
from app.services.storage import resolve_dataset_path
from app.data.loaders.tabular import load_tabular_file


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/datasets",
    tags=["AI Business Analysis"],
)


class AIBusinessAnalysisResponse(BaseModel):
    dataset_id: str
    ai_assisted: bool = True
    refined_objective: str
    business_questions: list[str]
    reasoning_summary: str
    recommended_focus_areas: list[str]
    clarifying_questions: list[str]
    analysis_plan: dict[str, Any]


@router.post(
    "/{dataset_id}/ai-analysis-plan",
    response_model=AIBusinessAnalysisResponse,
)
async def create_ai_analysis_plan(
    dataset_id: str,
    request: AnalysisPlanningRequest,
    http_request: Request,
):
    # --------------------------------------------------
    # 1. Load the uploaded dataset
    # --------------------------------------------------

    try:
        path = resolve_dataset_path(dataset_id)
        df = load_tabular_file(path)

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
    # 2. Extract dataset metadata
    # --------------------------------------------------

    columns = [
        {
            "name": str(column),
            "dtype": str(df[column].dtype),
        }
        for column in df.columns
    ]

    # --------------------------------------------------
    # 3. Generate AI-assisted business requirements
    # --------------------------------------------------

    try:
        ai_result = await await_or_cancel_on_disconnect(
            http_request,
            generate_business_analysis_async(
                objective=request.business_objective,
                business_questions=request.business_questions,
                columns=columns,
                row_count=len(df),
            ),
        )

    except ValueError as exc:
        # Invalid request/context limits are client-actionable, not provider outages.
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        logger.error(
            "AI Business Analyst unavailable: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=503,
            detail="The AI Business Analyst is currently unavailable. Verify provider configuration and backend logs.",
        ) from exc

    except Exception as exc:
        logger.exception(
            "Gemini Business Analyst request failed."
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The AI Business Analyst could not complete "
                "the request. Check backend logs for details."
            ),
        ) from exc

    # --------------------------------------------------
    # 4. Generate deterministic analysis plan
    # --------------------------------------------------

    try:
        analysis_plan = plan_dataset_analysis(
            path=path,
            dataset_id=dataset_id,
            business_objective=ai_result["refined_objective"],
            business_questions=ai_result["business_questions"],
        )

    except (ValueError, OSError) as exc:
        logger.exception(
            "Deterministic analysis plan generation failed."
        )

        raise HTTPException(
            status_code=422,
            detail=(
                f"Unable to generate deterministic analysis: {exc}"
            ),
        ) from exc

    # --------------------------------------------------
    # 5. Return combined AI + deterministic result
    # --------------------------------------------------

    return AIBusinessAnalysisResponse(
        dataset_id=dataset_id,
        ai_assisted=True,
        refined_objective=ai_result["refined_objective"],
        business_questions=ai_result["business_questions"],
        reasoning_summary=ai_result["reasoning_summary"],
        recommended_focus_areas=ai_result["recommended_focus_areas"],
        clarifying_questions=ai_result["clarifying_questions"],
        analysis_plan=analysis_plan,
    )