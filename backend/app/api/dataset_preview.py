from fastapi import APIRouter, HTTPException, Query

from app.services.dataset_preview import (
    DatasetPreviewError,
    get_dataset_preview,
    get_column_unique_values,
)

router = APIRouter(
    prefix="/datasets",
    tags=["dataset-preview"],
)


@router.get("/{dataset_id}/preview")
def preview_dataset(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=10),
    search: str | None = Query(default=None, max_length=200),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc"),
) -> dict:

    try:
        return get_dataset_preview(
            dataset_id=dataset_id,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Dataset version not found.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except DatasetPreviewError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

@router.get("/{dataset_id}/columns/{column_name}/unique-values")
def get_unique_column_values(
    dataset_id: str,
    column_name: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    try:
        return get_column_unique_values(
            dataset_id=dataset_id,
            column_name=column_name,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset version not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatasetPreviewError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
