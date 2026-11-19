import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.analytics_persistence import save_analytics_execution

from app.schemas.execution import (
    AnalyticsExecutionRequest,
    AnalyticsExecutionResponse,
    CorrelationAnalyticsResponse,
    DescriptiveAnalyticsResponse,
    ExecutionOperation,
    GroupedAnalyticsExecutionResponse,
    SegmentComparisonResponse,
    TrendAnalyticsResponse,
)

from app.services.analytics_executor import (
    AnalyticsExecutionError,
    DatasetNotFoundError,
    execute_grouped_kpi,
    execute_kpi,
    find_dataset_path,
)

from app.services.correlation_executor import execute_correlation
from app.services.descriptive_executor import execute_descriptive
from app.services.segment_executor import execute_segment_comparison
from app.services.settings import settings
from app.services.trend_executor import execute_trend


router = APIRouter(
    prefix="/datasets",
    tags=["Analytics Execution"],
)


@router.post("/{dataset_id}/execute")
def execute_dataset_analysis(
    dataset_id: str,
    request: AnalyticsExecutionRequest,
    db: Session = Depends(get_db),
) -> (
    AnalyticsExecutionResponse
    | GroupedAnalyticsExecutionResponse
    | DescriptiveAnalyticsResponse
    | TrendAnalyticsResponse
    | SegmentComparisonResponse
    | CorrelationAnalyticsResponse
):
    """
    Execute a supported analytics operation and persist its result.

    Supported operations:
    - KPI analysis
    - Grouped KPI analysis
    - Descriptive statistics
    - Trend analysis
    - Segment comparison
    - Pearson correlation analysis

    Execution workflow:
    1. Validate dataset identifier.
    2. Resolve the requested dataset version.
    3. Execute the selected analytics operation.
    4. Persist the execution configuration and result.
    5. Return the analytics response.
    """

    # ---------------------------------------------------------
    # 1. Validate dataset identifier
    # ---------------------------------------------------------

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", dataset_id):
        raise HTTPException(
            status_code=422,
            detail="Invalid dataset identifier.",
        )

    try:
        # -----------------------------------------------------
        # 2. Resolve requested dataset version
        # -----------------------------------------------------

        path = find_dataset_path(
            dataset_id=dataset_id,
            upload_dir=settings.upload_dir,
            version=request.version,
        )

        # Store the execution result instead of returning early.
        result = None

        # -----------------------------------------------------
        # 3. Correlation analysis
        # -----------------------------------------------------

        if request.operation == ExecutionOperation.CORRELATION:

            if request.second_column is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Correlation analysis requires a second numeric "
                        "column."
                    ),
                )

            if (
                request.aggregation is not None
                or request.group_by is not None
                or request.date_column is not None
                or request.interval is not None
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Correlation analysis accepts only the two "
                        "column selections and does not support "
                        "aggregation, grouping, or trend parameters."
                    ),
                )

            result = execute_correlation(
                path=path,
                dataset_id=dataset_id,
                column=request.column,
                second_column=request.second_column,
            )

        # -----------------------------------------------------
        # 4. Operations other than correlation
        # -----------------------------------------------------

        else:

            if request.second_column is not None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "second_column is supported only for correlation "
                        "analysis."
                    ),
                )

            # -------------------------------------------------
            # 4.1 Trend analysis
            # -------------------------------------------------

            if request.operation == ExecutionOperation.TREND:

                if request.group_by is not None:
                    raise HTTPException(
                        status_code=422,
                        detail="Trend analysis does not support group_by.",
                    )

                result = execute_trend(
                    path=path,
                    dataset_id=dataset_id,
                    request=request,
                )

            # -------------------------------------------------
            # 4.2 Descriptive statistics
            # -------------------------------------------------

            elif request.operation == ExecutionOperation.DESCRIPTIVE:

                if request.aggregation is not None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Descriptive analytics does not accept "
                            "an aggregation."
                        ),
                    )

                if request.group_by is not None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Descriptive analytics does not support group_by."
                        ),
                    )

                if (
                    request.date_column is not None
                    or request.interval is not None
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Descriptive analytics does not accept "
                            "trend parameters."
                        ),
                    )

                result = execute_descriptive(
                    path=path,
                    dataset_id=dataset_id,
                    request=request,
                )

            # -------------------------------------------------
            # 4.3 Segment comparison
            # -------------------------------------------------

            elif (
                request.operation
                == ExecutionOperation.SEGMENT_COMPARISON
            ):

                if (
                    request.date_column is not None
                    or request.interval is not None
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Segment comparison does not accept "
                            "trend parameters."
                        ),
                    )

                result = execute_segment_comparison(
                    path=path,
                    dataset_id=dataset_id,
                    request=request,
                )

            # -------------------------------------------------
            # 4.4 KPI and grouped KPI analysis
            # -------------------------------------------------

            else:

                if (
                    request.date_column is not None
                    or request.interval is not None
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "KPI operations do not accept trend parameters."
                        ),
                    )

                if request.aggregation is None:
                    raise HTTPException(
                        status_code=422,
                        detail="KPI operations require an aggregation.",
                    )

                if request.group_by is not None:
                    result = execute_grouped_kpi(
                        path=path,
                        dataset_id=dataset_id,
                        request=request,
                    )

                else:
                    result = execute_kpi(
                        path=path,
                        dataset_id=dataset_id,
                        request=request,
                    )

        # -----------------------------------------------------
        # 5. Persist successful analytics execution
        # -----------------------------------------------------

        if result is None:
            raise AnalyticsExecutionError(
                "Analytics execution did not produce a result."
            )

        execution_record = save_analytics_execution(
            db=db,
            dataset_id=dataset_id,
            request_config=request.model_dump(mode="json", exclude_none=True),
            result=result.model_dump(mode="json"),
        )

        if execution_record is not None:
            result.execution_id = execution_record.execution_id

        # -----------------------------------------------------
        # 6. Return analytics response
        # -----------------------------------------------------

        return result

    # ---------------------------------------------------------
    # Exception handling
    # ---------------------------------------------------------

    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except AnalyticsExecutionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc