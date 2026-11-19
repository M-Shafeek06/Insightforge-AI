"""Deterministic integrity checks for persisted analytics evidence.

This module validates the shape and mathematical invariants of analytics
results before they are supplied to an AI provider. It deliberately does
not attempt to interpret or parse free-form LLM prose.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any


class AnalyticsEvidenceValidationError(ValueError):
    """Raised when persisted analytics evidence is internally inconsistent."""


def _operation_value(operation: Any) -> str:
    return str(getattr(operation, "value", operation)).strip().lower()


def _number(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticsEvidenceValidationError(
            f"Analytics evidence field '{field}' must be a numeric value."
        )
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise AnalyticsEvidenceValidationError(
            f"Analytics evidence field '{field}' must be finite."
        )
    return numeric_value


def _non_negative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalyticsEvidenceValidationError(
            f"Analytics evidence field '{field}' must be a non-negative integer."
        )
    return value


def _validate_counts(item: dict[str, Any], prefix: str = "") -> None:
    row_count = _non_negative_integer(
        item.get("row_count"), f"{prefix}row_count"
    )
    valid_count = _non_negative_integer(
        item.get("valid_value_count"), f"{prefix}valid_value_count"
    )
    null_count = _non_negative_integer(
        item.get("null_count"), f"{prefix}null_count"
    )

    if valid_count + null_count != row_count:
        raise AnalyticsEvidenceValidationError(
            f"Analytics evidence counts are inconsistent for '{prefix or 'result'}'."
        )


def _validate_kpi(result: dict[str, Any]) -> None:
    # KPI execution supports both a single aggregate and grouped aggregates.
    if "groups" in result:
        groups = result.get("groups")
        if not isinstance(groups, list):
            raise AnalyticsEvidenceValidationError(
                "KPI evidence field 'groups' must be a list."
            )
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                raise AnalyticsEvidenceValidationError(
                    f"KPI evidence group at index {index} must be an object."
                )
            _number(group.get("value"), f"groups[{index}].value", nullable=True)
            _validate_counts(group, f"groups[{index}].")
        return

    _number(result.get("value"), "value")
    _validate_counts(result)


def _validate_descriptive(result: dict[str, Any]) -> None:
    statistics = result.get("statistics")
    if not isinstance(statistics, dict):
        raise AnalyticsEvidenceValidationError(
            "Descriptive evidence field 'statistics' must be an object."
        )

    minimum = _number(statistics.get("minimum"), "statistics.minimum")
    maximum = _number(statistics.get("maximum"), "statistics.maximum")
    mean = _number(statistics.get("mean"), "statistics.mean")
    median = _number(statistics.get("median"), "statistics.median")
    standard_deviation = _number(
        statistics.get("standard_deviation"),
        "statistics.standard_deviation",
        nullable=True,
    )

    if minimum > maximum:
        raise AnalyticsEvidenceValidationError(
            "Descriptive evidence minimum cannot exceed maximum."
        )
    if not minimum <= mean <= maximum:
        raise AnalyticsEvidenceValidationError(
            "Descriptive evidence mean must be between minimum and maximum."
        )
    if not minimum <= median <= maximum:
        raise AnalyticsEvidenceValidationError(
            "Descriptive evidence median must be between minimum and maximum."
        )
    if standard_deviation is not None and standard_deviation < 0:
        raise AnalyticsEvidenceValidationError(
            "Descriptive evidence standard deviation cannot be negative."
        )

    _validate_counts(result)


def _validate_trend(result: dict[str, Any]) -> None:
    points = result.get("points")
    if not isinstance(points, list):
        raise AnalyticsEvidenceValidationError(
            "Trend evidence field 'points' must be a list."
        )

    previous_period: date | None = None
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise AnalyticsEvidenceValidationError(
                f"Trend evidence point at index {index} must be an object."
            )

        period = point.get("period")
        if not isinstance(period, str):
            raise AnalyticsEvidenceValidationError(
                f"Trend evidence period at index {index} must be a string."
            )
        try:
            parsed_period = date.fromisoformat(period)
        except ValueError as exc:
            raise AnalyticsEvidenceValidationError(
                f"Trend evidence period at index {index} must use ISO date format."
            ) from exc

        if previous_period is not None and parsed_period <= previous_period:
            raise AnalyticsEvidenceValidationError(
                "Trend evidence periods must be strictly chronological."
            )
        previous_period = parsed_period

        _number(point.get("value"), f"points[{index}].value", nullable=True)
        _validate_counts(point, f"points[{index}].")


def _validate_segments(result: dict[str, Any]) -> None:
    segments = result.get("segments")
    if not isinstance(segments, list):
        raise AnalyticsEvidenceValidationError(
            "Segment comparison evidence field 'segments' must be a list."
        )

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise AnalyticsEvidenceValidationError(
                f"Segment evidence at index {index} must be an object."
            )
        if "group" not in segment:
            raise AnalyticsEvidenceValidationError(
                f"Segment evidence at index {index} is missing its group value."
            )
        _number(segment.get("value"), f"segments[{index}].value", nullable=True)
        _validate_counts(segment, f"segments[{index}].")


def _validate_correlation(result: dict[str, Any]) -> None:
    coefficient = _number(result.get("correlation"), "correlation")
    if not -1.0 <= coefficient <= 1.0:
        raise AnalyticsEvidenceValidationError(
            "Correlation evidence coefficient must be between -1 and 1."
        )

    observation_count = result.get("observation_count")
    if (
        isinstance(observation_count, bool)
        or not isinstance(observation_count, int)
        or observation_count < 2
    ):
        raise AnalyticsEvidenceValidationError(
            "Correlation evidence observation_count must be an integer of at least 2."
        )

    absolute_coefficient = abs(coefficient)
    if absolute_coefficient < 0.1:
        expected_strength = "negligible"
    elif absolute_coefficient < 0.3:
        expected_strength = "weak"
    elif absolute_coefficient < 0.7:
        expected_strength = "moderate"
    else:
        expected_strength = "strong"

    expected_direction = (
        "positive" if coefficient > 0 else "negative" if coefficient < 0 else "none"
    )

    if result.get("strength") != expected_strength:
        raise AnalyticsEvidenceValidationError(
            "Correlation evidence strength does not match its coefficient."
        )
    if result.get("direction") != expected_direction:
        raise AnalyticsEvidenceValidationError(
            "Correlation evidence direction does not match its coefficient."
        )


def validate_analytics_evidence(operation: Any, result: Any) -> None:
    """Validate persisted result invariants for a supported analytics operation.

    The checks intentionally mirror the response structures and correlation
    thresholds used by InsightForge's existing analytics executors.
    """
    operation_name = _operation_value(operation)
    if not isinstance(result, dict):
        raise AnalyticsEvidenceValidationError(
            "Analytics evidence must be an object."
        )

    validators = {
        "kpi": _validate_kpi,
        "descriptive": _validate_descriptive,
        "trend": _validate_trend,
        "segment_comparison": _validate_segments,
        "correlation": _validate_correlation,
    }

    validator = validators.get(operation_name)
    if validator is None:
        raise AnalyticsEvidenceValidationError(
            f"Unsupported analytics operation for AI interpretation: {operation_name}."
        )

    validator(result)
