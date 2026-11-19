from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Dataset,
    AnalyticsExecution,
    SavedAnalytics,
    SavedBusinessArtifact,
)

from app.services.pdf_report import generate_saved_analytics_pdf


router = APIRouter(
    prefix="/datasets",
    tags=["Analytics Reports"],
)


@router.get("/{dataset_id}/report")
def download_saved_analytics_report(
    dataset_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Generate a PDF report containing only explicitly
    saved analytics executions belonging to the dataset.
    """

    # --------------------------------------------------------
    # 1. Validate dataset
    # --------------------------------------------------------

    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    # --------------------------------------------------------
    # 2. Retrieve explicitly saved analytics only
    # --------------------------------------------------------

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
            SavedAnalytics.saved_at.asc(),
            AnalyticsExecution.execution_id.asc(),
        )
    )

    rows = db.execute(statement).all()

    artifacts = db.scalars(select(SavedBusinessArtifact).where(SavedBusinessArtifact.dataset_id == dataset_id).order_by(SavedBusinessArtifact.saved_at.asc(), SavedBusinessArtifact.artifact_id.asc())).all()
    if not rows and not artifacts:
        raise HTTPException(status_code=400, detail="No saved business artefacts are available. Save at least one item before generating a report.")

    # --------------------------------------------------------
    # 3. Build report records
    # --------------------------------------------------------

    saved_analyses = []

    for execution, saved_at in rows:
        execution.saved_at = saved_at
        saved_analyses.append(execution)

    # --------------------------------------------------------
    # 4. Generate PDF
    # --------------------------------------------------------

    try:
        pdf_buffer = generate_saved_analytics_pdf(
            dataset=dataset,
            saved_analyses=saved_analyses,
            saved_artifacts=artifacts,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to generate the analytics report.",
        ) from exc

    # --------------------------------------------------------
    # 5. Return downloadable PDF
    # --------------------------------------------------------

    filename = f"InsightForge_Report_{dataset_id}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Cache-Control": "no-store",
        },
    )