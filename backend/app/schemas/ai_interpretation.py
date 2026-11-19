from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AIInsightFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=3,
        max_length=200,
    )

    observation: str = Field(
        min_length=5,
        max_length=1000,
    )

    business_impact: str = Field(
        min_length=5,
        max_length=1000,
    )


class AIInsightRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        min_length=5,
        max_length=500,
    )

    rationale: str = Field(
        min_length=5,
        max_length=1000,
    )

    priority: Literal["high", "medium", "low"] = Field(
        description="Recommendation priority: high, medium, or low.",
    )


class AIInterpretationContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(
        min_length=10,
        max_length=2000,
    )

    key_findings: list[AIInsightFinding] = Field(
        max_length=10,
    )

    business_implications: list[str] = Field(
        max_length=10,
    )

    risks_and_limitations: list[str] = Field(
        default_factory=list,
        max_length=10,
    )

    recommendations: list[AIInsightRecommendation] = Field(
        max_length=10,
    )


class AIInterpretationResponse(AIInterpretationContent):
    dataset_id: UUID
    execution_id: UUID
    ai_assisted: bool = True
    provider: str
    model: str