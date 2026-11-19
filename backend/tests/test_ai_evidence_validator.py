import pytest

from app.services.ai_evidence_validator import (
    AnalyticsEvidenceValidationError,
    validate_analytics_evidence,
)


def counts(row_count=10, valid_value_count=9, null_count=1):
    return {
        "row_count": row_count,
        "valid_value_count": valid_value_count,
        "null_count": null_count,
    }


def test_valid_single_kpi_evidence():
    validate_analytics_evidence(
        "kpi",
        {"value": 125.5, **counts()},
    )


def test_valid_grouped_kpi_evidence_allows_null_aggregate():
    validate_analytics_evidence(
        "kpi",
        {
            "groups": [
                {"group": "North", "value": 125.5, **counts()},
                {"group": "South", "value": None, **counts(3, 0, 3)},
            ]
        },
    )


def test_kpi_rejects_inconsistent_counts():
    with pytest.raises(AnalyticsEvidenceValidationError, match="counts are inconsistent"):
        validate_analytics_evidence(
            "kpi",
            {"value": 125.5, **counts(10, 8, 1)},
        )


def test_valid_descriptive_statistics():
    validate_analytics_evidence(
        "descriptive",
        {
            "statistics": {
                "mean": 12.0,
                "median": 11.0,
                "minimum": 2.0,
                "maximum": 25.0,
                "standard_deviation": 4.5,
            },
            **counts(),
        },
    )


@pytest.mark.parametrize(
    "statistics",
    [
        {"mean": 30.0, "median": 11.0, "minimum": 2.0, "maximum": 25.0, "standard_deviation": 4.5},
        {"mean": 12.0, "median": 11.0, "minimum": 26.0, "maximum": 25.0, "standard_deviation": 4.5},
        {"mean": 12.0, "median": 11.0, "minimum": 2.0, "maximum": 25.0, "standard_deviation": -1.0},
    ],
)
def test_descriptive_rejects_invalid_statistical_invariants(statistics):
    with pytest.raises(AnalyticsEvidenceValidationError):
        validate_analytics_evidence(
            "descriptive",
            {"statistics": statistics, **counts()},
        )


def test_valid_trend_evidence():
    validate_analytics_evidence(
        "trend",
        {
            "points": [
                {"period": "2026-01-01", "value": 10.0, **counts()},
                {"period": "2026-02-01", "value": None, **counts(2, 0, 2)},
            ]
        },
    )


def test_trend_rejects_out_of_order_periods():
    with pytest.raises(AnalyticsEvidenceValidationError, match="strictly chronological"):
        validate_analytics_evidence(
            "trend",
            {
                "points": [
                    {"period": "2026-02-01", "value": 10.0, **counts()},
                    {"period": "2026-01-01", "value": 11.0, **counts()},
                ]
            },
        )


def test_valid_segment_comparison_evidence():
    validate_analytics_evidence(
        "segment_comparison",
        {
            "segments": [
                {"group": "North", "value": 10.0, **counts()},
                {"group": None, "value": None, **counts(2, 0, 2)},
            ]
        },
    )


@pytest.mark.parametrize(
    "coefficient,strength,direction",
    [
        (0.05, "negligible", "positive"),
        (0.2, "weak", "positive"),
        (-0.5, "moderate", "negative"),
        (-0.9, "strong", "negative"),
        (0.0, "negligible", "none"),
    ],
)
def test_valid_correlation_evidence(coefficient, strength, direction):
    validate_analytics_evidence(
        "correlation",
        {
            "correlation": coefficient,
            "observation_count": 25,
            "strength": strength,
            "direction": direction,
        },
    )


def test_correlation_rejects_incorrect_direction():
    with pytest.raises(AnalyticsEvidenceValidationError, match="direction does not match"):
        validate_analytics_evidence(
            "correlation",
            {
                "correlation": -0.82,
                "observation_count": 25,
                "strength": "strong",
                "direction": "positive",
            },
        )


def test_correlation_rejects_incorrect_strength():
    with pytest.raises(AnalyticsEvidenceValidationError, match="strength does not match"):
        validate_analytics_evidence(
            "correlation",
            {
                "correlation": 0.82,
                "observation_count": 25,
                "strength": "moderate",
                "direction": "positive",
            },
        )


def test_unsupported_operation_is_rejected():
    with pytest.raises(AnalyticsEvidenceValidationError, match="Unsupported analytics operation"):
        validate_analytics_evidence("descriptive_statistics", {})
