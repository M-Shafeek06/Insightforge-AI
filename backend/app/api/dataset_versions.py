from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.services.dataset_versions import get_dataset_versions


router = APIRouter(
    prefix="/datasets",
    tags=["dataset-versions"],
)


@router.get("/{dataset_id}/versions")
def list_dataset_versions(dataset_id: str) -> dict:

    # Validate dataset identifier
    try:
        validated_id = str(UUID(dataset_id))

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid dataset identifier.",
        ) from exc

    # Retrieve version registry
    try:
        registry = get_dataset_versions(validated_id)

        return registry

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Dataset version registry not found.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve dataset versions.",
        ) from exc