import pandas as pd
import pytest

from app.services.cleaning import (
    CleaningValidationError,
    dataset_metrics,
    generate_cleaning_preview,
)


def test_missing_values_filled_with_mean():
    df = pd.DataFrame({"Sales": [100.0, None, 300.0]})

    result = generate_cleaning_preview(
        df,
        [{"type": "fill_missing", "column": "Sales", "strategy": "mean"}],
    )

    assert result["before"]["missing_values"] == 1
    assert result["after"]["missing_values"] == 0
    assert result["operations"][0]["rows_affected"] == 1


def test_missing_values_filled_with_constant():
    df = pd.DataFrame({"City": ["Chennai", None, "Bangalore"]})

    result = generate_cleaning_preview(
        df,
        [{
            "type": "fill_missing",
            "column": "City",
            "strategy": "constant",
            "value": "Unknown",
        }],
    )

    assert result["after"]["missing_values"] == 0
    assert result["preview"][1]["City"] == "Unknown"


def test_duplicate_rows_removed():
    df = pd.DataFrame({"ID": [1, 2, 2, 3]})

    result = generate_cleaning_preview(
        df,
        [{"type": "drop_duplicates"}],
    )

    assert result["before"]["rows"] == 4
    assert result["after"]["rows"] == 3
    assert result["operations"][0]["rows_affected"] == 1


def test_whitespace_trimmed():
    df = pd.DataFrame({"City": [" Chennai ", "Bangalore  ", " Kochi"]})

    result = generate_cleaning_preview(
        df,
        [{"type": "trim_whitespace", "column": "City"}],
    )

    assert result["preview"] == [
        {"City": "Chennai"},
        {"City": "Bangalore"},
        {"City": "Kochi"},
    ]


def test_text_standardization():
    df = pd.DataFrame({"City": ["chennai", "BANGALORE", "kochi"]})

    result = generate_cleaning_preview(
        df,
        [{
            "type": "standardize_text",
            "column": "City",
            "case": "title",
        }],
    )

    assert [row["City"] for row in result["preview"]] == [
        "Chennai", "Bangalore", "Kochi"
    ]


def test_numeric_conversion():
    df = pd.DataFrame({"Sales": ["100", "200", "300"]})

    result = generate_cleaning_preview(
        df,
        [{"type": "convert_numeric", "column": "Sales"}],
    )

    assert result["after"]["rows"] == 3
    assert result["preview"][0]["Sales"] == 100


def test_invalid_numeric_conversion_rejected():
    df = pd.DataFrame({"Sales": ["100", "invalid", "300"]})

    with pytest.raises(CleaningValidationError):
        generate_cleaning_preview(
            df,
            [{"type": "convert_numeric", "column": "Sales"}],
        )


def test_missing_column_rejected():
    df = pd.DataFrame({"Sales": [100, 200]})

    with pytest.raises(CleaningValidationError):
        generate_cleaning_preview(
            df,
            [{"type": "trim_whitespace", "column": "City"}],
        )


def test_original_dataset_is_never_modified():
    df = pd.DataFrame({
        "City": [" Chennai ", None],
        "Sales": [100.0, 200.0],
    })
    original = df.copy(deep=True)

    generate_cleaning_preview(
        df,
        [
            {"type": "trim_whitespace", "column": "City"},
            {
                "type": "fill_missing",
                "column": "City",
                "strategy": "constant",
                "value": "Unknown",
            },
        ],
    )

    pd.testing.assert_frame_equal(df, original)


def test_empty_operations_rejected():
    df = pd.DataFrame({"Sales": [100, 200]})

    with pytest.raises(CleaningValidationError):
        generate_cleaning_preview(df, [])


def test_metrics_calculated_correctly():
    df = pd.DataFrame({
        "Sales": [100, None, 100],
        "City": ["Chennai", "Kochi", "Chennai"],
    })

    metrics = dataset_metrics(df)

    assert metrics == {
        "rows": 3,
        "columns": 2,
        "missing_values": 1,
        "duplicate_rows": 1,
    }


def test_drop_single_column():
    df = pd.DataFrame({
        "Product": ["Laptop", "Phone"],
        "Sales": [1000, 500],
        "Internal": ["A1", "A2"],
    })

    result = generate_cleaning_preview(
        df,
        [{
            "type": "drop_column",
            "columns": ["Internal"],
        }],
    )

    assert result["before"]["columns"] == 3
    assert result["after"]["columns"] == 2

    assert list(result["preview"][0].keys()) == [
        "Product",
        "Sales",
    ]

    assert result["operations"][0]["columns_removed"] == [
        "Internal",
    ]


def test_drop_multiple_columns():
    df = pd.DataFrame({
        "Product": ["Laptop", "Phone"],
        "Sales": [1000, 500],
        "Internal": ["A1", "A2"],
        "Temporary": ["X", "Y"],
    })

    result = generate_cleaning_preview(
        df,
        [{
            "type": "drop_column",
            "columns": ["Internal", "Temporary"],
        }],
    )

    assert result["after"]["columns"] == 2

    assert list(result["preview"][0].keys()) == [
        "Product",
        "Sales",
    ]

    assert result["operations"][0]["columns_removed_count"] == 2


def test_drop_column_rejects_all_columns():
    df = pd.DataFrame({
        "Product": ["Laptop"],
        "Sales": [1000],
    })

    with pytest.raises(
        CleaningValidationError,
        match="every column",
    ):
        generate_cleaning_preview(
            df,
            [{
                "type": "drop_column",
                "columns": ["Product", "Sales"],
            }],
        )


def test_drop_column_rejects_missing_column():
    df = pd.DataFrame({
        "Product": ["Laptop"],
        "Sales": [1000],
    })

    with pytest.raises(
        CleaningValidationError,
        match="do not exist",
    ):
        generate_cleaning_preview(
            df,
            [{
                "type": "drop_column",
                "columns": ["Unknown"],
            }],
        )


def test_drop_column_rejects_duplicate_selection():
    df = pd.DataFrame({
        "Product": ["Laptop"],
        "Sales": [1000],
        "Internal": ["A1"],
    })

    with pytest.raises(
        CleaningValidationError,
        match="Duplicate column selections",
    ):
        generate_cleaning_preview(
            df,
            [{
                "type": "drop_column",
                "columns": ["Internal", "Internal"],
            }],
        )


def test_drop_column_preserves_original_dataframe():
    df = pd.DataFrame({
        "Product": ["Laptop", "Phone"],
        "Sales": [1000, 500],
        "Internal": ["A1", "A2"],
    })

    original = df.copy(deep=True)

    generate_cleaning_preview(
        df,
        [{
            "type": "drop_column",
            "columns": ["Internal"],
        }],
    )

    pd.testing.assert_frame_equal(df, original)

def test_multiple_cleaning_operations_execute_sequentially():
    df = pd.DataFrame({
        "Name": [" Alice ", "BOB", " Charlie "],
        "Age": ["25", "30", "35"],
        "City": ["Chennai", "Bangalore", "Coimbatore"],
        "Unused": [1, 2, 3],
    })

    original = df.copy(deep=True)

    operations = [
        {
            "type": "drop_column",
            "columns": ["Unused"],
        },
        {
            "type": "trim_whitespace",
            "column": "Name",
        },
        {
            "type": "standardize_text",
            "column": "Name",
            "case": "lower",
        },
        {
            "type": "convert_numeric",
            "column": "Age",
        },
    ]

    result = generate_cleaning_preview(df, operations)

    # Verify final dataset structure.
    assert result["after"]["columns"] == 3

    # Verify sequential transformations.
    assert result["preview"] == [
        {"Name": "alice", "Age": 25, "City": "Chennai"},
        {"Name": "bob", "Age": 30, "City": "Bangalore"},
        {"Name": "charlie", "Age": 35, "City": "Coimbatore"},
    ]

    # Verify original dataset remains unchanged.
    pd.testing.assert_frame_equal(df, original)


def test_datetime_conversion_coerces_invalid_values_to_null_and_reports_them():
    df = pd.DataFrame({
        "OrderDate": [
            "2026-01-05",
            "2026-01-07",
            "not-a-date",
            "2026-02-02",
        ],
        "Sales": [10, 20, 30, 40],
    })
    original = df.copy(deep=True)

    result = generate_cleaning_preview(
        df,
        [{"type": "convert_datetime", "column": "OrderDate"}],
    )

    operation = result["operations"][0]
    assert operation["column"] == "OrderDate"
    assert operation["converted_values"] == 3
    assert operation["invalid_values"] == 1
    assert operation["original_missing_values"] == 0
    assert operation["null_values_after_conversion"] == 1
    assert operation["invalid_value_samples"] == ["not-a-date"]
    assert result["after"]["missing_values"] == 1
    assert result["preview"][2]["OrderDate"] is None
    # Unrelated columns are unchanged.
    assert [row["Sales"] for row in result["preview"]] == [10, 20, 30, 40]
    pd.testing.assert_frame_equal(df, original)


def test_datetime_conversion_preserves_existing_nulls_and_reports_invalids():
    df = pd.DataFrame({
        "OrderDate": ["2026-01-05", None, "invalid"],
    })

    result = generate_cleaning_preview(
        df,
        [{"type": "convert_datetime", "column": "OrderDate"}],
    )

    operation = result["operations"][0]
    assert operation["converted_values"] == 1
    assert operation["invalid_values"] == 1
    assert operation["original_missing_values"] == 1
    assert operation["null_values_after_conversion"] == 2


def test_datetime_conversion_rejects_ambiguous_date_formats():
    df = pd.DataFrame({
        "OrderDate": ["01/02/2026", "03/04/2026"],
    })

    with pytest.raises(CleaningValidationError, match="ambiguous date"):
        generate_cleaning_preview(
            df,
            [{"type": "convert_datetime", "column": "OrderDate"}],
        )
