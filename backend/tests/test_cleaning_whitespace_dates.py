import pandas as pd

from app.services.cleaning import apply_cleaning_operations


def test_datetime_conversion_counts_whitespace_only_values_as_blank():
    frame = pd.DataFrame(
        {
            "MonthName_Day_Year": [
                "January 15, 2024",
                " ",
                "not-a-date",
            ]
        }
    )

    cleaned, results = apply_cleaning_operations(
        frame,
        [
            {
                "type": "convert_datetime",
                "column": "MonthName_Day_Year",
            }
        ],
    )

    result = results[0]

    assert pd.isna(cleaned.loc[1, "MonthName_Day_Year"])
    assert pd.isna(cleaned.loc[2, "MonthName_Day_Year"])

    assert result["converted_values"] == 1
    assert result["invalid_values"] == 1
    assert result["original_missing_values"] == 1
    assert result["invalid_value_samples"] == ["not-a-date"]
    assert result["null_values_after_conversion"] == 2
    assert "1 non-empty value(s)" in result["warning"]
