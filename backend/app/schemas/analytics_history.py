from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalyticsExecutionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_id: UUID
    dataset_id: UUID
    operation: str
    request_config: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime


class AnalyticsExecutionHistoryResponse(BaseModel):
    dataset_id: UUID
    total: int
    limit: int
    offset: int
    executions: list[AnalyticsExecutionHistoryItem]