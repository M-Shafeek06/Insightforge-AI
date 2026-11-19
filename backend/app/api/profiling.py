import json

from fastapi import APIRouter, HTTPException

from app.schemas.dataset import DatasetProfileResponse
from app.services.profiler import profile_dataset
from app.services.storage import resolve_dataset_path
from app.services.dataset_versions import get_dataset_versions
from app.services.settings import settings

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/{dataset_id}/profile", response_model=DatasetProfileResponse)
def get_dataset_profile(dataset_id: str) -> dict:

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

    metadata_path = path.parent / f"{dataset_id}.json"

    filename = path.name

    if metadata_path.exists():
        try:
            filename = json.loads(
                metadata_path.read_text(encoding="utf-8")
            ).get("filename", filename)

        except (json.JSONDecodeError, OSError):
            pass

    result = profile_dataset(
        path,
        dataset_id,
        filename,
    )

    # A CSV normally has no worksheet source. A cleaned version derived
    # from an XLSX workbook may itself be stored as CSV, so resolve the
    # original workbook through the version lineage rather than filename.
    worksheet_switchable = False
    try:
        registry = get_dataset_versions(dataset_id)
        root_id = registry["original_dataset_id"]
        root_metadata_path = settings.upload_dir / f"{root_id}.json"
        root_metadata = {}
        if root_metadata_path.is_file():
            try:
                root_metadata = json.loads(root_metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                root_metadata = {}
        workbook_id = (
            root_metadata.get("workbook_id")
            or root_metadata.get("source_workbook_dataset_id")
            or root_id
        )
        worksheet_switchable = (settings.upload_dir / f"{workbook_id}.xlsx").is_file()
    except (FileNotFoundError, ValueError):
        worksheet_switchable = False

    result["worksheet_switchable"] = worksheet_switchable
    return result