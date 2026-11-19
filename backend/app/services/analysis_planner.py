from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.data.loaders.tabular import load_tabular_file
from app.schemas.analysis import (
    AnalysisPlanResponse,
    AnalysisQualityWarning,
    RecommendedAnalysis,
    RecommendedKPI,
)
from app.services.profiler import _semantic_role
from app.services.quality import assess_dataset_quality


def _normalize(value: str) -> str:
    """Normalize text for exact, case-insensitive comparisons."""
    return "".join(character for character in value.casefold() if character.isalnum())


def _tokens(value: str) -> set[str]:
    """Split snake_case, kebab-case, spaces and camelCase into semantic tokens."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9]+", value)}


def _contains_term(text: str, term: str) -> bool:
    """Match a phrase as words, not as an arbitrary substring."""
    text_tokens = _tokens(text)
    term_tokens = _tokens(term)
    if not term_tokens:
        return False
    if len(term_tokens) == 1:
        return next(iter(term_tokens)) in text_tokens
    normalized_text = f" {_normalize(text)} "
    normalized_term = _normalize(term)
    return f"{normalized_term}" in normalized_text


def _find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    """Resolve a column by exact alias first, then conservative token matching."""
    normalized_columns = {column: _normalize(column) for column in columns}
    for candidate in candidates:
        target = _normalize(candidate)
        for column, normalized in normalized_columns.items():
            if normalized == target:
                return column

    # A candidate must match a complete token/phrase. Prefer the most specific
    # alias and then the shortest column name to avoid arbitrary broad matches.
    matches: list[tuple[int, int, str]] = []
    for candidate in candidates:
        candidate_tokens = _tokens(candidate)
        if not candidate_tokens:
            continue
        for column in columns:
            column_tokens = _tokens(column)
            if candidate_tokens.issubset(column_tokens):
                matches.append((len(candidate_tokens), -len(column_tokens), column))
    if matches:
        return max(matches)[2]
    return None


def _objective_requirements(columns: list[str], objective: str, questions: list[str]) -> list[str]:
    """Identify explicitly requested business dimensions absent from the data."""
    text = " ".join([objective, *questions])
    requirements = [
        (("product", "products", "item", "items", "sku"), ("product", "product name", "item", "item name", "sku"), "Product"),
        (("customer", "customers", "customer segment", "client", "clients"), ("customer", "customer id", "customer name", "client", "client id"), "Customer"),
        (("region", "regional", "territory", "geography", "geographic"), ("region", "territory", "state", "country", "city", "geography"), "Region"),
        (("employee", "employees", "sales representative", "salesperson"), ("employee", "employee id", "sales rep", "salesperson", "representative"), "Employee"),
    ]
    missing: list[str] = []
    for triggers, aliases, label in requirements:
        if any(_contains_term(text, trigger) for trigger in triggers) and _find_column(columns, aliases) is None:
            missing.append(label)
    return missing


def _quality_warnings(path: Path, dataset_id: str) -> list[AnalysisQualityWarning]:
    quality_result = assess_dataset_quality(path=path, dataset_id=dataset_id)
    return [
        AnalysisQualityWarning(
            issue_type=issue["issue_type"],
            severity=issue["severity"],
            column=issue["column"],
            message=issue["message"],
            recommendation=issue["recommendation"],
        )
        for issue in quality_result["issues"]
    ]


def _is_identifier_column(column: str) -> bool:
    tokens = _tokens(column)
    identifier_tokens = {"id", "identifier", "code", "key", "zip", "postal", "postcode", "phone", "telephone"}
    return bool(tokens & identifier_tokens)


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    """Return non-empty numeric measures; exclude identifier fields by token."""
    return [
        str(column)
        for column in df.columns
        if pd.api.types.is_numeric_dtype(df[column])
        and df[column].notna().any()
        and not _is_identifier_column(str(column))
    ]


def _question_column(columns: list[str], questions: list[str], candidates: list[str]) -> str | None:
    """Find a column explicitly mentioned in questions, preferring specificity."""
    for question in questions:
        q_norm = _normalize(question)
        exact = [column for column in candidates if _normalize(column) == q_norm]
        if exact:
            return max(exact, key=lambda value: len(_tokens(value)))
        matches = [
            column for column in candidates
            if _normalize(column) and _normalize(column) in q_norm
        ]
        if matches:
            return max(matches, key=lambda value: (len(_normalize(value)), value))
    return None


def _recommended_kpis(df: pd.DataFrame, columns: list[str], objective: str, questions: list[str] | None = None) -> list[RecommendedKPI]:
    """Recommend only metrics supported by actual non-empty numeric columns."""
    text = " ".join([objective, *(questions or [])])
    numeric = _numeric_columns(df)
    kpis: list[RecommendedKPI] = []

    def add(name: str, description: str, column: str | None, calculation: str) -> None:
        if column and column in numeric and all(item.name != name for item in kpis):
            kpis.append(RecommendedKPI(name=name, description=description, required_columns=[column], calculation=calculation.format(column=column)))

    sales = _find_column(columns, ("sales", "revenue", "total amount", "sales amount", "turnover"))
    profit = _find_column(columns, ("profit", "net profit", "gross profit"))
    quantity = _find_column(columns, ("quantity", "units sold", "units", "qty"))
    orders = _find_column(columns, ("order amount", "order value", "orders"))

    asks_sales = any(_contains_term(text, term) for term in ("sales", "revenue", "turnover"))
    asks_profit = any(_contains_term(text, term) for term in ("profit", "margin", "financial"))
    asks_quantity = any(_contains_term(text, term) for term in ("quantity", "units", "inventory"))
    asks_orders = any(_contains_term(text, term) for term in ("orders", "order volume", "order value"))

    if sales and (asks_sales or not (asks_profit or asks_quantity or asks_orders)):
        add("Total Sales", "Total value recorded in the sales measure.", sales, "SUM({column})")
        add("Average Sales", "Average value recorded per row.", sales, "AVERAGE({column})")
    if profit and asks_profit:
        add("Total Profit", "Total value recorded in the profit measure.", profit, "SUM({column})")
    if quantity and asks_quantity:
        add("Total Quantity", "Total quantity recorded across all rows.", quantity, "SUM({column})")
    if orders and asks_orders and orders != sales:
        add("Total Orders", "Total value recorded in the orders measure.", orders, "SUM({column})")

    if not kpis and numeric:
        column = _question_column(columns, questions or [], numeric) or numeric[0]
        add(f"Total {column}", f"Sum of values in the {column} column.", column, "SUM({column})")
    return kpis


def _recommended_analyses(df: pd.DataFrame, columns: list[str], business_questions: list[str] | None = None, objective: str = "") -> list[RecommendedAnalysis]:
    """Recommend supported analyses based on intent and available column roles."""
    questions = business_questions or []
    intent_text = " ".join([objective, *questions])
    numeric = _numeric_columns(df)
    time_columns = [str(c) for c in df.columns if _semantic_role(df[c]) == "time"]
    dimensions = [str(c) for c in df.columns if _semantic_role(df[c]) == "dimension"]

    selected_dimension = _question_column(columns, questions, dimensions) or (dimensions[0] if dimensions else None)
    selected_measure = _question_column(columns, questions, numeric)
    if selected_measure is None:
        selected_measure = _find_column(columns, ("sales", "revenue", "profit", "quantity", "amount"))
    if selected_measure not in numeric:
        selected_measure = numeric[0] if numeric else None
    selected_time = _question_column(columns, questions, time_columns) or (time_columns[0] if time_columns else None)

    asks_trend = any(_contains_term(intent_text, term) for term in ("trend", "over time", "monthly", "daily", "weekly", "yearly", "seasonality", "fluctuate", "variation", "temporal"))
    asks_segment = any(_contains_term(intent_text, term) for term in ("region", "regional", "category", "product", "customer", "segment", "territory", "compare", "highest", "lowest", "top performing", "contribution", "breakdown", "by region", "by category"))
    asks_correlation = any(_contains_term(intent_text, term) for term in ("relationship", "correlation", "association", "related", "connection"))

    analyses: list[RecommendedAnalysis] = []
    if asks_segment and selected_dimension and selected_measure:
        analyses.append(RecommendedAnalysis(
            name="Segment Comparison", description="Compare a numeric measure across categories.",
            analysis_method="Group-by aggregation", operation="segment_comparison",
            required_columns=[selected_dimension, selected_measure],
            business_value="Identify the categories contributing most to the measure.",
        ))
    if asks_trend and selected_time and selected_measure:
        analyses.append(RecommendedAnalysis(
            name="Trend Analysis", description="Examine how a numeric measure changes over time.",
            analysis_method="Time-based aggregation", operation="trend",
            required_columns=[selected_time, selected_measure],
            business_value="Identify temporal patterns, peaks and declines.",
        ))
    if asks_correlation and len(numeric) >= 2:
        first = selected_measure or numeric[0]
        second = next((column for column in numeric if column != first), None)
        if second:
            analyses.append(RecommendedAnalysis(
                name="Measure Relationship", description="Explore the relationship between two numeric measures.",
                analysis_method="Correlation analysis", operation="correlation",
                required_columns=[first, second],
                business_value="Assess the direction and strength of association between measures.",
            ))

    # For broad objectives, provide a small useful baseline rather than
    # generating every possible method merely because columns exist.
    if not analyses and selected_measure:
        if selected_dimension:
            analyses.append(RecommendedAnalysis(
                name="Segment Comparison", description="Compare a numeric measure across categories.",
                analysis_method="Group-by aggregation", operation="segment_comparison",
                required_columns=[selected_dimension, selected_measure],
                business_value="Compare performance across available categories.",
            ))
        elif selected_time:
            analyses.append(RecommendedAnalysis(
                name="Trend Analysis", description="Examine how a numeric measure changes over time.",
                analysis_method="Time-based aggregation", operation="trend",
                required_columns=[selected_time, selected_measure],
                business_value="Identify temporal patterns, peaks and declines.",
            ))
        else:
            analyses.append(RecommendedAnalysis(
                name="Descriptive Analysis", description="Summarize the distribution of a numeric measure.",
                analysis_method="Descriptive statistics", operation="descriptive",
                required_columns=[selected_measure],
                business_value="Understand the scale and distribution of the measure.",
            ))
    return analyses


def plan_dataset_analysis(path: Path, dataset_id: str, business_objective: str, business_questions: list[str] | None = None) -> dict[str, Any]:
    """Create a deterministic, dataset-grounded analysis plan."""
    df = load_tabular_file(path)
    columns = [str(column) for column in df.columns]
    objective = business_objective.strip()
    questions = business_questions or []

    recommended_kpis = _recommended_kpis(df, columns, objective, questions)
    recommended_analyses = _recommended_analyses(df, columns, questions, objective)
    objective_missing = _objective_requirements(columns, objective, questions)

    if not columns or len(df) == 0:
        status, reason = "not_feasible", "The dataset contains no usable rows or columns."
    elif not _numeric_columns(df):
        status, reason = "not_feasible", "No non-empty numeric measure is available for the supported analytical methods."
    elif objective_missing:
        status = "partially_feasible"
        reason = "The dataset supports some analysis, but the requested objective may require additional dimension(s): " + ", ".join(objective_missing) + "."
    elif not recommended_kpis and not recommended_analyses:
        status, reason = "partially_feasible", "Some dataset fields are available, but the current planner could not identify a supported analysis matching the request."
    else:
        status, reason = "feasible", "The dataset contains fields that support the recommended analyses. Recommendations are limited to the available columns and detected data types."

    quality_warnings = _quality_warnings(path=path, dataset_id=dataset_id)
    return AnalysisPlanResponse(
        dataset_id=dataset_id,
        business_objective=objective,
        feasibility_status=status,
        feasibility_reason=reason,
        recommended_kpis=recommended_kpis,
        recommended_analyses=recommended_analyses,
        available_columns=columns,
        missing_required_columns=objective_missing,
        quality_warnings=quality_warnings,
    ).model_dump()
