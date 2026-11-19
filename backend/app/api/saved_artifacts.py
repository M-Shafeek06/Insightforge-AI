import hashlib, json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Dataset, SavedBusinessArtifact, AnalyticsExecution

router = APIRouter(prefix="/datasets", tags=["Saved Business Artefacts"])
ArtifactType = Literal["interpretation", "deterministic_plan", "ai_business_plan"]
class SaveArtifactRequest(BaseModel):
    artifact_type: ArtifactType
    title: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any]
    source_execution_id: UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        """Keep persisted titles within the database's VARCHAR(255) limit.

        Planner objectives can be long, so they belong in `payload`, not in
        the display title. This is a defensive fallback for older clients.
        """
        if not isinstance(value, str):
            return value
        title = value.strip()
        if len(title) > 255:
            title = title[:252].rstrip() + "..."
        return title
class SavedArtifactResponse(BaseModel):
    artifact_id: UUID
    dataset_id: UUID
    artifact_type: str
    title: str
    saved_at: datetime
    already_saved: bool = False
class SavedArtifactListResponse(BaseModel):
    dataset_id: UUID
    total: int
    artifacts: list[SavedArtifactResponse]

@router.post("/{dataset_id}/saved-artifacts", response_model=SavedArtifactResponse)
def save_artifact(dataset_id: UUID, request: SaveArtifactRequest, db: Session = Depends(get_db)):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if request.source_execution_id is not None and db.scalar(select(AnalyticsExecution).where(AnalyticsExecution.execution_id == request.source_execution_id, AnalyticsExecution.dataset_id == dataset_id)) is None:
        raise HTTPException(status_code=404, detail="Source execution not found for this dataset.")
    canonical = json.dumps(request.payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    query = select(SavedBusinessArtifact).where(SavedBusinessArtifact.dataset_id == dataset_id, SavedBusinessArtifact.artifact_type == request.artifact_type, SavedBusinessArtifact.content_hash == digest)
    existing = db.scalar(query)
    if existing:
        return SavedArtifactResponse(artifact_id=existing.artifact_id, dataset_id=existing.dataset_id, artifact_type=existing.artifact_type, title=existing.title, saved_at=existing.saved_at, already_saved=True)
    record = SavedBusinessArtifact(artifact_id=uuid4(), dataset_id=dataset_id, artifact_type=request.artifact_type, content_hash=digest, title=request.title, payload=request.payload, source_execution_id=request.source_execution_id)
    try:
        db.add(record); db.commit(); db.refresh(record)
    except IntegrityError:
        db.rollback(); existing = db.scalar(query)
        if existing is None: raise
        return SavedArtifactResponse(artifact_id=existing.artifact_id, dataset_id=existing.dataset_id, artifact_type=existing.artifact_type, title=existing.title, saved_at=existing.saved_at, already_saved=True)
    except Exception:
        db.rollback(); raise
    return SavedArtifactResponse(artifact_id=record.artifact_id, dataset_id=record.dataset_id, artifact_type=record.artifact_type, title=record.title, saved_at=record.saved_at)

@router.get("/{dataset_id}/saved-artifacts", response_model=SavedArtifactListResponse)
def list_artifacts(dataset_id: UUID, db: Session = Depends(get_db)):
    if db.get(Dataset, dataset_id) is None: raise HTTPException(status_code=404, detail="Dataset not found.")
    rows = db.scalars(select(SavedBusinessArtifact).where(SavedBusinessArtifact.dataset_id == dataset_id).order_by(SavedBusinessArtifact.saved_at, SavedBusinessArtifact.artifact_id)).all()
    return SavedArtifactListResponse(dataset_id=dataset_id, total=len(rows), artifacts=[SavedArtifactResponse(artifact_id=r.artifact_id, dataset_id=r.dataset_id, artifact_type=r.artifact_type, title=r.title, saved_at=r.saved_at) for r in rows])

@router.delete("/{dataset_id}/saved-artifacts/{artifact_id}")
def delete_artifact(dataset_id: UUID, artifact_id: UUID, db: Session = Depends(get_db)):
    row = db.scalar(select(SavedBusinessArtifact).where(SavedBusinessArtifact.dataset_id == dataset_id, SavedBusinessArtifact.artifact_id == artifact_id))
    if row is None: raise HTTPException(status_code=404, detail="Saved artefact not found.")
    db.delete(row); db.commit()
    return {"dataset_id": str(dataset_id), "artifact_id": str(artifact_id), "deleted": True}
