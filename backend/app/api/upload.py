import json
from datetime import datetime
from io import BytesIO
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.data.loaders.tabular import SUPPORTED_EXTENSIONS
from app.db import get_db
from app.models import Dataset, DatasetVersion
from app.schemas.dataset import DatasetUploadResponse
from app.services.dataset_versions import (
    dataset_versions_lock,
    get_version_registry_path,
    register_original_dataset,
    get_dataset_versions,
)
from app.services.settings import settings

router = APIRouter(prefix="/datasets", tags=["datasets"])
MAX_FILE_SIZE = 50 * 1024 * 1024


def _workbook_registry_path(workbook_id: str) -> Path:
    return settings.upload_dir.parent / "metadata" / "workbooks" / f"{workbook_id}.json"


def _read_dataset_metadata(dataset_id: str) -> dict:
    path = settings.upload_dir / f"{dataset_id}.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_workbook_registry(workbook_id: str) -> dict:
    path = _workbook_registry_path(workbook_id)
    if not path.is_file():
        return {"workbook_id": workbook_id, "sheets": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sheets"), dict):
        raise ValueError("Workbook worksheet registry is invalid.")
    return data


def _save_workbook_registry(registry: dict) -> None:
    path = _workbook_registry_path(registry["workbook_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(registry, handle, indent=2)
            handle.flush()
            import os
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


@router.post("/workbook-sheets")
async def get_workbook_sheets(file: UploadFile = File(...)) -> dict[str, list[str]]:
    """Inspect an XLSX workbook without creating a dataset or persisting it."""
    extension = Path(file.filename or "").suffix.lower()
    if extension != ".xlsx":
        raise HTTPException(status_code=400, detail="Worksheet discovery is available for XLSX files only.")
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 50 MB upload limit.")
    try:
        workbook = pd.ExcelFile(BytesIO(content))
        sheets = workbook.sheet_names
        workbook.close()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to read the Excel workbook. Check that it is a valid XLSX file.") from exc
    if not sheets:
        raise HTTPException(status_code=400, detail="The Excel workbook does not contain any worksheets.")
    return {"sheets": sheets}




@router.get("/{dataset_id}/worksheet-options")
def get_dataset_worksheet_options(dataset_id: str) -> dict[str, list[str]]:
    """Return worksheet names from the workbook shared by this worksheet dataset."""
    try:
        registry = get_dataset_versions(dataset_id)
        # Cleaned versions may be stored as CSVs and do not have their own
        # upload metadata. Resolve workbook lineage from the worksheet's
        # original dataset metadata so switching remains available after
        # cleaning and version changes.
        root_metadata = _read_dataset_metadata(registry["original_dataset_id"])
        metadata = _read_dataset_metadata(dataset_id)
        workbook_id = (
            metadata.get("workbook_id")
            or metadata.get("source_workbook_dataset_id")
            or root_metadata.get("workbook_id")
            or root_metadata.get("source_workbook_dataset_id")
            or registry["original_dataset_id"]
        )
        workbook_path = settings.upload_dir / f"{workbook_id}.xlsx"
        if not workbook_path.is_file():
            raise HTTPException(status_code=409, detail="The original Excel workbook is unavailable for worksheet switching.")
        with pd.ExcelFile(workbook_path) as workbook:
            return {"sheets": workbook.sheet_names}
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Dataset workbook not found.")


@router.post("/{dataset_id}/select-worksheet", status_code=status.HTTP_201_CREATED)
def select_dataset_worksheet(
    dataset_id: str,
    sheet_name: str = Form(...),
    first_row_header: bool = Form(default=True),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Resolve a worksheet to its stable dataset ID, creating it only once."""
    try:
        source_registry = get_dataset_versions(dataset_id)
        worksheet_root_id = source_registry["original_dataset_id"]
        source_metadata = _read_dataset_metadata(worksheet_root_id)
        workbook_id = (source_metadata.get("workbook_id")
                       or source_metadata.get("source_workbook_dataset_id")
                       or worksheet_root_id)
        workbook_path = settings.upload_dir / f"{workbook_id}.xlsx"
        if not workbook_path.is_file():
            raise HTTPException(status_code=409, detail="The original Excel workbook is unavailable for worksheet switching.")

        with pd.ExcelFile(workbook_path) as workbook:
            if sheet_name not in workbook.sheet_names:
                raise HTTPException(status_code=422, detail="The selected worksheet does not exist in this workbook.")

        # Serialize map updates using the existing cross-process dataset lock.
        with dataset_versions_lock(workbook_id):
            workbook_registry = _load_workbook_registry(workbook_id)
            # Backfill the first worksheet for workbooks uploaded before this registry existed.
            current_sheet = source_metadata.get("sheet_name")
            if current_sheet and current_sheet not in workbook_registry["sheets"]:
                workbook_registry["sheets"][current_sheet] = {
                    "dataset_id": worksheet_root_id,
                    "filename": source_metadata.get("filename") or source_registry["versions"][0]["filename"],
                }
                _save_workbook_registry(workbook_registry)
            existing = workbook_registry["sheets"].get(sheet_name)
            if existing:
                existing_id = existing.get("dataset_id")
                if not existing_id:
                    raise ValueError("Worksheet mapping is missing its dataset identifier.")
                return {"dataset_id": existing_id, "filename": existing.get("filename", source_registry["versions"][0]["filename"]), "sheet_name": sheet_name}

            filename = source_metadata.get("filename") or source_registry["versions"][0]["filename"]
            new_id = str(uuid4())
            target = settings.upload_dir / f"{new_id}.xlsx"
            metadata_target = settings.upload_dir / f"{new_id}.json"
            shutil.copy2(workbook_path, target)
            metadata_target.write_text(json.dumps({
                "filename": filename,
                "sheet_name": sheet_name,
                "first_row_header": first_row_header,
                "workbook_id": workbook_id,
                "source_workbook_dataset_id": workbook_id,
            }), encoding="utf-8")

            registry_created = False
            try:
                new_registry = register_original_dataset(dataset_id=new_id, filename=filename)
                registry_created = True
                created_at = datetime.fromisoformat(new_registry["versions"][0]["created_at"])
                db.add(Dataset(id=UUID(new_id), filename=filename, stored_filename=target.name, storage_location="raw"))
                db.add(DatasetVersion(dataset_id=UUID(new_id), original_dataset_id=UUID(new_id), version_number=0, version_type="original", filename=filename, cleaning_plan_id=None, parent_dataset_id=None, created_at=created_at))
                db.commit()
                workbook_registry["sheets"][sheet_name] = {"dataset_id": new_id, "filename": filename}
                _save_workbook_registry(workbook_registry)
            except Exception:
                db.rollback()
                if registry_created:
                    with dataset_versions_lock(new_id):
                        get_version_registry_path(new_id).unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                metadata_target.unlink(missing_ok=True)
                raise

        return {"dataset_id": new_id, "filename": filename, "sheet_name": sheet_name}
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Dataset workbook not found.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to switch worksheet.") from exc


@router.post("/upload", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(default=None),
    first_row_header: bool = Form(default=True),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported.")
    dataset_id = str(uuid4())
    target = settings.upload_dir / f"{dataset_id}{extension}"
    metadata_target = settings.upload_dir / f"{dataset_id}.json"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    registry_created = False
    try:
        size = 0
        with target.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File exceeds the 50 MB upload limit.")
                destination.write(chunk)

        if extension == ".xlsx":
            try:
                workbook = pd.ExcelFile(target)
                sheet_names = workbook.sheet_names
                workbook.close()
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Unable to read the Excel workbook. Check that it is a valid XLSX file.") from exc
            if not sheet_names:
                raise HTTPException(status_code=400, detail="The Excel workbook does not contain any worksheets.")
            if sheet_name is None:
                if len(sheet_names) > 1:
                    raise HTTPException(status_code=422, detail={"code": "sheet_selection_required", "sheets": sheet_names, "message": "Select a worksheet before uploading this workbook."})
                sheet_name = sheet_names[0]
            elif sheet_name not in sheet_names:
                raise HTTPException(status_code=422, detail="The selected worksheet does not exist in this workbook.")
        elif sheet_name is not None:
            raise HTTPException(status_code=400, detail="A worksheet cannot be selected for a CSV file.")

        filename = file.filename or target.name
        metadata = {"filename": filename, "first_row_header": first_row_header}
        if sheet_name is not None:
            metadata["sheet_name"] = sheet_name
        if extension == ".xlsx":
            metadata["workbook_id"] = dataset_id
            metadata["source_workbook_dataset_id"] = dataset_id
        metadata_target.write_text(json.dumps(metadata), encoding="utf-8")

        registry = register_original_dataset(dataset_id=dataset_id, filename=filename)
        registry_created = True
        created_at = datetime.fromisoformat(registry["versions"][0]["created_at"])
        db.add(Dataset(id=UUID(dataset_id), filename=filename, stored_filename=target.name, storage_location="raw"))
        db.add(DatasetVersion(dataset_id=UUID(dataset_id), original_dataset_id=UUID(dataset_id), version_number=0, version_type="original", filename=filename, cleaning_plan_id=None, parent_dataset_id=None, created_at=created_at))
        db.commit()
        if extension == ".xlsx" and sheet_name is not None:
            with dataset_versions_lock(dataset_id):
                workbook_registry = _load_workbook_registry(dataset_id)
                workbook_registry["sheets"][sheet_name] = {"dataset_id": dataset_id, "filename": filename}
                _save_workbook_registry(workbook_registry)
    except HTTPException:
        db.rollback()
        target.unlink(missing_ok=True)
        metadata_target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        if registry_created:
            with dataset_versions_lock(dataset_id):
                get_version_registry_path(dataset_id).unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        metadata_target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Unable to save uploaded file.") from exc
    return {"dataset_id": dataset_id, "filename": filename}
