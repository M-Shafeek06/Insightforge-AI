import pandas as pd

from app.services import analysis_planner as planner


def test_numeric_identifier_exclusion_uses_tokens_not_substrings():
    frame = pd.DataFrame({
        "OrderID": [1001, 1002],
        "ValidSales": [120.0, 150.0],
        "PostalCode": [600001, 600002],
        "DiscountKey": [1, 2],
    })
    assert planner._numeric_columns(frame) == ["ValidSales"]


def test_column_matching_prefers_exact_alias_and_avoids_partial_word_match():
    columns = ["Salesperson", "Sales", "WholesaleAmount"]
    assert planner._find_column(columns, ("sales",)) == "Sales"
    assert planner._find_column(columns, ("profit",)) is None


def test_kpis_follow_objective_and_business_questions():
    frame = pd.DataFrame({
        "Region": ["North", "South"],
        "Sales": [100.0, 120.0],
        "Profit": [20.0, 25.0],
        "OrderDate": pd.to_datetime(["2026-01-01", "2026-02-01"]),
    })
    kpis = planner._recommended_kpis(
        frame,
        list(frame.columns),
        "Analyze regional sales and profit performance",
        ["Which region has the highest sales?", "Which region has the highest profit?"],
    )
    assert [item.name for item in kpis] == ["Total Sales", "Average Sales", "Total Profit"]


def test_recommendations_are_limited_to_requested_supported_methods():
    frame = pd.DataFrame({
        "Region": ["North", "South", "North"],
        "Sales": [100.0, 120.0, 90.0],
        "Profit": [20.0, 25.0, 18.0],
        "OrderDate": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
    })
    analyses = planner._recommended_analyses(
        frame,
        list(frame.columns),
        [
            "Which region generates the highest total sales?",
            "How do sales vary monthly?",
            "Is there a relationship between sales and profit?",
        ],
        "Analyze regional sales and profit performance and monthly variations",
    )
    assert {item.operation for item in analyses} == {"segment_comparison", "trend", "correlation"}
    assert all(set(item.required_columns).issubset(frame.columns) for item in analyses)


def test_missing_dimension_is_reported_only_when_requested():
    assert planner._objective_requirements(
        ["Sales", "Profit"],
        "Analyze regional sales performance",
        [],
    ) == ["Region"]
    assert planner._objective_requirements(
        ["Sales", "Profit"],
        "Analyze overall sales performance",
        [],
    ) == []
