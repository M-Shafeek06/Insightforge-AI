from pathlib import Path

import pandas as pd

from app.services.quality import assess_dataset_quality


def test_quality_detects_missing_values_and_date_as_text(tmp_path):
    dataset = pd.DataFrame(
        {
            "OrderDate": [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
                "2026-01-04",
                "2026-01-05",
            ],
            "Region": [
                "South",
                "North",
                "South",
                "West",
                "East",
            ],
            "Sales": [
                100.0,
                None,
                250.0,
                300.0,
                150.0,
            ],
        }
    )

    path = Path(tmp_path) / "quality_sample.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-quality-dataset",
    )

    assert result["dataset_id"] == "test-quality-dataset"
    assert result["overall_score"] == 82
    assert result["quality_status"] == "Good"

    assert result["summary"]["total_issues"] == 2
    assert result["summary"]["critical"] == 0
    assert result["summary"]["high"] == 1
    assert result["summary"]["medium"] == 0
    assert result["summary"]["low"] == 1

    issue_types = {issue["issue_type"] for issue in result["issues"]}

    assert "missing_values" in issue_types
    assert "date_as_text" in issue_types


def test_quality_detects_high_cardinality_column(tmp_path):
    dataset = pd.DataFrame({
        "CustomerID": [f"CUST-{i}" for i in range(100)],
        "Region": ["South", "North"] * 50,
    })

    path = Path(tmp_path) / "high_cardinality.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-high-cardinality",
    )

    issues = [
        issue for issue in result["issues"]
        if issue["issue_type"] == "high_cardinality"
    ]

    assert len(issues) == 1
    assert issues[0]["column"] == "CustomerID"
    assert issues[0]["severity"] == "low"
    assert issues[0]["affected_rows"] == 100
    assert issues[0]["affected_percentage"] == 100.0


def test_quality_does_not_flag_low_cardinality_column(tmp_path):
    dataset = pd.DataFrame({
        "Region": ["South", "North"] * 50,
    })

    path = Path(tmp_path) / "low_cardinality.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-low-cardinality",
    )

    assert not any(
        issue["issue_type"] == "high_cardinality"
        for issue in result["issues"]
    )


def test_quality_does_not_flag_high_cardinality_below_minimum_rows(tmp_path):
    dataset = pd.DataFrame({
        "CustomerID": [f"CUST-{i}" for i in range(19)],
    })

    path = Path(tmp_path) / "small_dataset.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-small-dataset",
    )

    assert not any(
        issue["issue_type"] == "high_cardinality"
        for issue in result["issues"]
    )

def test_quality_detects_high_cardinality_with_missing_values(tmp_path):
    dataset = pd.DataFrame({
        "CustomerID": [
            *[f"CUST-{i}" for i in range(90)],
            *[None] * 10,
        ]
    })

    path = Path(tmp_path) / "high_cardinality_nulls.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-high-cardinality-nulls",
    )

    issues = [
        issue for issue in result["issues"]
        if issue["issue_type"] == "high_cardinality"
    ]

    assert len(issues) == 1
    assert issues[0]["column"] == "CustomerID"
    assert issues[0]["affected_rows"] == 90
    assert issues[0]["affected_percentage"] == 90.0


def test_quality_does_not_flag_valid_year_month_values(tmp_path):
    dataset = pd.DataFrame({
        "Order_Month": [
            "2025-10",
            "2025-01",
            "2024-10",
            "2024-09",
        ]
    })

    path = Path(tmp_path) / "year_month.csv"
    dataset.to_csv(path, index=False)

    result = assess_dataset_quality(
        path=path,
        dataset_id="test-year-month",
    )

    issues = [
        issue for issue in result["issues"]
        if issue["column"] == "Order_Month"
        and issue["issue_type"] == "invalid_date_values"
    ]

    assert len(issues) == 0