from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CleaningOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "drop_duplicates",
        "drop_column",
        "fill_missing",
        "trim_whitespace",
        "standardize_text",
        "convert_numeric",
        "convert_datetime",
    ]

    column: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    columns: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    strategy: Literal[
        "mean",
        "median",
        "mode",
        "constant",
        "drop_rows",
    ] | None = None

    value: Any = None

    case: Literal["lower", "upper", "title"] = "lower"


class CleaningPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[CleaningOperation] = Field(
        min_length=1,
        max_length=50,
    )


class CleaningApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: Literal[True]