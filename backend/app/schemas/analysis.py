from pydantic import BaseModel, Field, field_validator
from typing import Literal

class AnalysisPlanningRequest(BaseModel):
    business_objective: str = Field(
        min_length=5,
        max_length=1000,
        description="The business objective the user wants to investigate.",
    )
    business_questions: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Specific business questions to investigate (maximum 500 characters each).",
    )

    @field_validator("business_objective")
    @classmethod
    def validate_objective_not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Business objective must contain at least 5 non-whitespace characters.")
        return value

    @field_validator("business_questions")
    @classmethod
    def validate_business_questions(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if len(cleaned) > 20 or any(len(value) > 500 for value in cleaned):
            raise ValueError("Provide at most 20 non-empty business questions, each no longer than 500 characters.")
        return list(dict.fromkeys(cleaned))


class RecommendedKPI(BaseModel):
    name: str
    description: str
    required_columns: list[str]
    calculation: str


class RecommendedAnalysis(BaseModel):
    name: str
    description: str
    analysis_method: str
    operation: Literal[
        "descriptive",
        "trend",
        "segment_comparison",
        "correlation",
    ]
    required_columns: list[str]
    business_value: str


class AnalysisQualityWarning(BaseModel):
    issue_type: str
    severity: str
    column: str | None = None
    message: str
    recommendation: str


class AnalysisPlanResponse(BaseModel):
    dataset_id: str
    business_objective: str
    feasibility_status: str
    feasibility_reason: str
    recommended_kpis: list[RecommendedKPI]
    recommended_analyses: list[RecommendedAnalysis]
    available_columns: list[str]
    missing_required_columns: list[str]
    quality_warnings: list[AnalysisQualityWarning]