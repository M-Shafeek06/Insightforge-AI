from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SavedAnalyticsResponse(BaseModel):
    execution_id: UUID
    dataset_id: UUID
    saved: bool
    saved_at: datetime | None = None
    message: str


class SavedAnalyticsItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_id: UUID
    dataset_id: UUID
    operation: str
    request_config: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    saved_at: datetime


class SavedAnalyticsListResponse(BaseModel):
    dataset_id: UUID
    total: int
    saved_analyses: list[SavedAnalyticsItem]