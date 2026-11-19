from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.quality import DatasetQualityResponse
from app.services.quality import assess_dataset_quality
from app.services.storage import resolve_dataset_path

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/{dataset_id}/quality", response_model=DatasetQualityResponse)
def get_dataset_quality(dataset_id: str) -> dict:

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

    return assess_dataset_quality(
        path=Path(path),
        dataset_id=dataset_id,
    )