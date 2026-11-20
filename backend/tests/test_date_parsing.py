import pandas as pd
import pytest

from app.services.cleaning import (
    CleaningValidationError,
    generate_cleaning_preview,
)
from app.services.date_parsing import parse_date_series


@pytest.mark.parametrize(
    "column,values,expected",
    [
        ("US_Date_MM_DD_YYYY", ["03/05/2024", "10/31/2024"], ["2024-03-05", "2024-10-31"]),
        ("UK_Date_DD_MM_YYYY", ["05/03/2024", "31/10/2024"], ["2024-03-05", "2024-10-31"]),
        ("Day_MonthName_Year", ["15-Jan-2024", "29-Feb-2024"], ["2024-01-15", "2024-02-29"]),
        ("MonthName_Day_Year", ["January 15, 2024", "February 29, 2024"], ["2024-01-15", "2024-02-29"]),
        ("ISO_Date_YYYY_MM_DD", ["2024-01-15", "2024-02-29"], ["2024-01-15", "2024-02-29"]),
    ],
)
def test_column_format_hints_parse_dates_without_day_month_swaps(column, values, expected):
    parsed = parse_date_series(pd.Series(values), column=column)
    assert [value.strftime("%Y-%m-%d") for value in parsed] == expected


def test_ambiguous_slash_dates_without_evidence_are_rejected():
    with pytest.raises(ValueError, match="cannot be determined safely"):
        parse_date_series(pd.Series(["01/02/2026", "03/04/2026"]), column="OrderDate")


def test_datetime_conversion_accepts_already_typed_datetime_columns():
    source = pd.DataFrame({
        "Native_Excel_Date": pd.to_datetime(["2024-01-15", "2024-02-29"])
    })
    result = generate_cleaning_preview(
        source,
        [{"type": "convert_datetime", "column": "Native_Excel_Date"}],
    )
    assert result["operations"][0]["converted_values"] == 2
    assert pd.Timestamp(result["preview"][1]["Native_Excel_Date"]).strftime("%Y-%m-%d") == "2024-02-29"


def test_datetime_conversion_uses_column_format_and_nulls_invalid_values():
    source = pd.DataFrame({
        "US_Date_MM_DD_YYYY": ["03/05/2024", "10/31/2024", "13/20/2026", None]
    })
    result = generate_cleaning_preview(
        source,
        [{"type": "convert_datetime", "column": "US_Date_MM_DD_YYYY"}],
    )
    operation = result["operations"][0]
    assert operation["converted_values"] == 2
    assert operation["invalid_values"] == 1
    assert operation["original_missing_values"] == 1
    assert pd.Timestamp(result["preview"][0]["US_Date_MM_DD_YYYY"]).strftime("%Y-%m-%d") == "2024-03-05"
    assert result["preview"][2]["US_Date_MM_DD_YYYY"] is None


def test_mixed_supported_date_formats_are_parsed_per_value():
    source = pd.Series([
        "2025-01-10 00:00:00",
        "11-Jan-2025",
        "January 14, 2025",
        "04/13/2025",  # unambiguous US
        "13/04/2025",  # unambiguous UK
        "2026-13-20",
        "13/20/2026",
        "20-NotAMonth-2026",
    ])

    parsed = parse_date_series(source, column="Order_Date")

    assert parsed.iloc[:5].notna().all()
    assert parsed.iloc[0].strftime("%Y-%m-%d") == "2025-01-10"
    assert parsed.iloc[1].strftime("%Y-%m-%d") == "2025-01-11"
    assert parsed.iloc[2].strftime("%Y-%m-%d") == "2025-01-14"
    assert parsed.iloc[3].strftime("%Y-%m-%d") == "2025-04-13"
    assert parsed.iloc[4].strftime("%Y-%m-%d") == "2025-04-13"
    assert parsed.iloc[5:].isna().all()


def test_ambiguous_slash_values_in_mixed_column_are_not_guessed():
    source = pd.Series([
        "2025-01-10",
        "01/04/2025",
        "13/04/2025",
    ])

    parsed = parse_date_series(source, column="Order_Date")

    assert parsed.iloc[0].strftime("%Y-%m-%d") == "2025-01-10"
    assert pd.isna(parsed.iloc[1])
    assert parsed.iloc[2].strftime("%Y-%m-%d") == "2025-04-13"


def test_year_month_format_is_supported():
    source = pd.Series([
        "2025-10",
        "2025-01",
        "2024-10",
        "2024-09",
    ])

    parsed = parse_date_series(
        source,
        column="Order_Month",
    )

    assert parsed.notna().all()

    assert [
        value.strftime("%Y-%m")
        for value in parsed
    ] == [
        "2025-10",
        "2025-01",
        "2024-10",
        "2024-09",
    ]