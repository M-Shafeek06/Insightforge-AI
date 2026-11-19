from fastapi import APIRouter, HTTPException

from app.schemas.analysis import (
    AnalysisPlanResponse,
    AnalysisPlanningRequest,
)

from app.services.analysis_planner import plan_dataset_analysis
from app.services.storage import resolve_dataset_path

router = APIRouter(prefix="/datasets", tags=["Analysis Planning"])


@router.post(
    "/{dataset_id}/analysis-plan",
    response_model=AnalysisPlanResponse,
)
def create_analysis_plan(
    dataset_id: str,
    request: AnalysisPlanningRequest,
) -> AnalysisPlanResponse:

    try:
        path = resolve_dataset_path(dataset_id)

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

    try:
        result = plan_dataset_analysis(
            path=path,
            dataset_id=dataset_id,
            business_objective=request.business_objective,
            business_questions=request.business_questions,
        )

        return AnalysisPlanResponse.model_validate(result)

    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unable to create analysis plan: {exc}",
        ) from exc