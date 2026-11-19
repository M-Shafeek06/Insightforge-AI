from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


class CleaningValidationError(ValueError):
    """Raised when a cleaning operation is invalid or unsafe."""


# Column names that commonly represent identifiers rather than measurements.
IDENTIFIER_PATTERN = re.compile(
    r"(^|[_\W])"
    r"(id|identifier|code|postal|postcode|zip|phone|mobile|"
    r"account|ssn|sku)"
    r"([_\W]|$)",
    flags=re.IGNORECASE,
)

# Numeric-looking dates such as 01/02/2026 can be ambiguous.
AMBIGUOUS_DATE_PATTERN = re.compile(
    r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$"
)


def dataset_metrics(df: pd.DataFrame) -> dict[str, int]:
    """Return basic data-quality metrics for a dataset."""

    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }


def _validate_column(df: pd.DataFrame, column: str) -> None:
    if not df.columns.is_unique:
        raise CleaningValidationError(
            "Dataset contains duplicate column names."
        )

    if column not in df.columns:
        raise CleaningValidationError(
            f"Column '{column}' does not exist."
        )


def _require_column(operation: dict[str, Any]) -> str:
    column = operation.get("column")

    if not isinstance(column, str) or not column.strip():
        raise CleaningValidationError(
            "A valid column is required."
        )

    return column


def _is_text_column(series: pd.Series) -> bool:
    """Return True only when the non-null values are strings."""

    if not (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return False

    non_null = series.dropna()

    return all(isinstance(value, str) for value in non_null)


def _is_identifier_column(column: str) -> bool:
    """Identify columns that should not be automatically converted."""

    normalized = column.strip().replace(" ", "_")

    return bool(IDENTIFIER_PATTERN.search(normalized))


def _validate_numeric_conversion(
    series: pd.Series,
    column: str,
) -> pd.Series:
    """Validate a text-to-numeric conversion without losing information."""

    if not _is_text_column(series):
        raise CleaningValidationError(
            f"Numeric conversion is only allowed for text columns. "
            f"'{column}' is not a suitable text column."
        )

    if series.dropna().empty:
        raise CleaningValidationError(
            f"Column '{column}' has no values to convert."
        )

    converted = pd.to_numeric(
        series,
        errors="coerce",
    )

    invalid_mask = series.notna() & converted.isna()

    if invalid_mask.any():
        raise CleaningValidationError(
            f"Cannot safely convert '{column}': "
            f"{int(invalid_mask.sum())} invalid value(s) found."
        )

    finite_mask = converted.dropna().map(
        lambda value: np.isfinite(value)
    )

    if not finite_mask.all():
        raise CleaningValidationError(
            f"Cannot safely convert '{column}': "
            "infinite numeric values are not allowed."
        )

    return converted


def _validate_datetime_conversion(
    series: pd.Series,
    column: str,
) -> pd.Series:
    """Validate text-to-datetime conversion conservatively."""

    if not _is_text_column(series):
        raise CleaningValidationError(
            f"Datetime conversion is only allowed for text columns. "
            f"'{column}' is not a suitable text column."
        )

    non_null = series.dropna()

    if non_null.empty:
        raise CleaningValidationError(
            f"Column '{column}' has no values to convert."
        )

    # Reject pure numeric strings because they may be IDs,
    # timestamps, or measurements rather than calendar dates.
    numeric_only_mask = non_null.str.fullmatch(r"\s*[+-]?\d+(\.\d+)?\s*")

    if numeric_only_mask.any():
        raise CleaningValidationError(
            f"Cannot safely convert '{column}' to datetime: "
            "numeric-only values are not accepted as dates."
        )

    # Reject ambiguous dates such as 01/02/2026.
    for value in non_null:
        match = AMBIGUOUS_DATE_PATTERN.match(value)

        if match:
            first = int(match.group(1))
            second = int(match.group(2))

            if (
                1 <= first <= 12
                and 1 <= second <= 12
                and first != second
            ):
                raise CleaningValidationError(
                    f"Cannot safely convert '{column}': "
                    f"ambiguous date value '{value}' found. "
                    "Use an unambiguous date format such as YYYY-MM-DD."
                )

    # Invalid non-empty values are converted to NaT rather than blocking the
    # entire cleaning plan. The operation result reports the exact invalid
    # count, and the before/after preview makes the resulting NULLs visible.
    # The source DataFrame remains untouched because all operations run on a
    # deep copy.
    try:
        converted = pd.to_datetime(
            series,
            errors="coerce",
            format="mixed",
        )
    except (ValueError, TypeError, OverflowError) as exc:
        raise CleaningValidationError(
            f"Unable to parse date values in '{column}'."
        ) from exc

    return converted


def _validate_constant_value(
    series: pd.Series,
    value: Any,
    column: str,
) -> Any:
    """Prevent incompatible constant values from changing column types."""

    if value is None:
        raise CleaningValidationError(
            "Constant imputation requires a non-null value."
        )

    if pd.api.types.is_bool_dtype(series):
        if not isinstance(value, bool):
            raise CleaningValidationError(
                f"Constant value for '{column}' must be boolean."
            )

    elif pd.api.types.is_numeric_dtype(series):
        if isinstance(value, bool) or not isinstance(
            value,
            (int, float, np.integer, np.floating),
        ):
            raise CleaningValidationError(
                f"Constant value for numeric column '{column}' "
                "must be numeric."
            )

        if not np.isfinite(value):
            raise CleaningValidationError(
                f"Constant value for '{column}' must be finite."
            )

    elif pd.api.types.is_datetime64_any_dtype(series):
        try:
            value = pd.to_datetime(value, errors="raise")
        except (ValueError, TypeError, OverflowError):
            raise CleaningValidationError(
                f"Constant value for datetime column '{column}' "
                "must be a valid date."
            )

    elif _is_text_column(series):
        if not isinstance(value, str):
            raise CleaningValidationError(
                f"Constant value for text column '{column}' "
                "must be text."
            )

    return value


def _apply_operation(
    df: pd.DataFrame,
    operation: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply one cleaning operation to an in-memory DataFrame."""

    operation_type = operation.get("type")

        # 1. Drop selected columns
    if operation_type == "drop_column":
        columns_to_drop = operation.get("columns")

        if (
            not isinstance(columns_to_drop, list)
            or not columns_to_drop
        ):
            raise CleaningValidationError(
                "At least one column must be selected for removal."
            )

        if not df.columns.is_unique:
            raise CleaningValidationError(
                "Dataset contains duplicate column names."
            )

        if any(
            not isinstance(column, str) or not column.strip()
            for column in columns_to_drop
        ):
            raise CleaningValidationError(
                "Every selected column must have a valid name."
            )

        if len(columns_to_drop) != len(set(columns_to_drop)):
            raise CleaningValidationError(
                "Duplicate column selections are not allowed."
            )

        missing_columns = [
            column
            for column in columns_to_drop
            if column not in df.columns
        ]

        if missing_columns:
            raise CleaningValidationError(
                f"Columns do not exist: {missing_columns}"
            )

        if len(columns_to_drop) >= len(df.columns):
            raise CleaningValidationError(
                "Cannot remove every column from the dataset. "
                "At least one column must remain."
            )

        result = df.drop(
            columns=columns_to_drop
        ).copy()

        return result, {
            "type": operation_type,
            "columns_removed": columns_to_drop,
            "columns_removed_count": len(columns_to_drop),
            "columns_remaining": len(result.columns),
            "message": (
                f"Successfully removed {len(columns_to_drop)} "
                f"column(s): {', '.join(columns_to_drop)}."
            ),
            "warning": (
                "Removed columns will not be available in the "
                "cleaned dataset. Review the preview before approval."
            ),
        }

    # 1. Remove duplicate rows
    if operation_type == "drop_duplicates":
        before = len(df)
        result = df.drop_duplicates().copy()

        removed = int(before - len(result))

        return result, {
            "type": operation_type,
            "rows_affected": removed,
            "warning": (
                "Duplicate rows will be permanently excluded "
                "from the cleaned dataset."
                if removed > 0
                else None
            ),
            "message": f"Removed {removed} duplicate rows.",
        }

    # All remaining operations require a valid column.
    column = _require_column(operation)
    _validate_column(df, column)

    series = df[column]

    # 2. Handle missing values
    if operation_type == "fill_missing":
        strategy = operation.get("strategy")
        missing_count = int(series.isna().sum())

        if missing_count == 0:
            return df, {
                "type": operation_type,
                "column": column,
                "rows_affected": 0,
                "message": "No missing values found.",
            }

        if strategy == "mean":
            if not pd.api.types.is_numeric_dtype(series):
                raise CleaningValidationError(
                    f"Mean imputation requires numeric column '{column}'."
                )

            if series.dropna().empty:
                raise CleaningValidationError(
                    f"Column '{column}' has no values for mean imputation."
                )

            value = series.mean()

        elif strategy == "median":
            if not pd.api.types.is_numeric_dtype(series):
                raise CleaningValidationError(
                    f"Median imputation requires numeric column '{column}'."
                )

            if series.dropna().empty:
                raise CleaningValidationError(
                    f"Column '{column}' has no values for median imputation."
                )

            value = series.median()

        elif strategy == "mode":
            modes = series.mode(dropna=True)

            if modes.empty:
                raise CleaningValidationError(
                    f"Column '{column}' has no values for mode imputation."
                )

            value = modes.iloc[0]

        elif strategy == "constant":
            if "value" not in operation:
                raise CleaningValidationError(
                    "Constant imputation requires a value."
                )

            value = _validate_constant_value(
                series,
                operation["value"],
                column,
            )

        elif strategy == "drop_rows":
            before = len(df)
            result = df.dropna(subset=[column]).copy()

            removed = int(before - len(result))
            percentage = (
                round((removed / before) * 100, 2)
                if before > 0
                else 0
            )

            return result, {
                "type": operation_type,
                "column": column,
                "rows_affected": removed,
                "rows_removed_percentage": percentage,
                "warning": (
                    f"This operation removes {percentage}% "
                    "of the original rows."
                    if removed > 0
                    else None
                ),
                "message": (
                    f"Removed {removed} rows with missing values "
                    f"in '{column}'."
                ),
            }

        else:
            raise CleaningValidationError(
                "Unsupported missing-value strategy."
            )

        result = df.copy()
        result[column] = result[column].fillna(value)

        return result, {
            "type": operation_type,
            "column": column,
            "strategy": strategy,
            "rows_affected": missing_count,
            "message": (
                f"Filled {missing_count} missing values "
                f"in '{column}' using {strategy}."
            ),
        }

    # 3. Trim whitespace
    if operation_type == "trim_whitespace":
        if not _is_text_column(series):
            raise CleaningValidationError(
                f"Whitespace trimming requires a text column: '{column}'."
            )

        result = df.copy()
        original = result[column].copy()

        result[column] = result[column].map(
            lambda value: value.strip()
            if isinstance(value, str)
            else value
        )

        changed = int(
            (
                original.fillna("").astype(str)
                != result[column].fillna("").astype(str)
            ).sum()
        )

        return result, {
            "type": operation_type,
            "column": column,
            "rows_affected": changed,
            "message": (
                f"Trimmed leading and trailing whitespace "
                f"in {changed} values."
            ),
        }

    # 4. Standardize text
    if operation_type == "standardize_text":
        if not _is_text_column(series):
            raise CleaningValidationError(
                f"Text standardization requires a text column: '{column}'."
            )

        case = operation.get("case", "lower")

        transformations = {
            "lower": str.lower,
            "upper": str.upper,
            "title": str.title,
        }

        if case not in transformations:
            raise CleaningValidationError(
                "Case must be lower, upper, or title."
            )

        result = df.copy()
        original = result[column].copy()

        result[column] = result[column].map(
            lambda value: transformations[case](value.strip())
            if isinstance(value, str)
            else value
        )

        changed = int(
            (
                original.fillna("").astype(str)
                != result[column].fillna("").astype(str)
            ).sum()
        )

        return result, {
            "type": operation_type,
            "column": column,
            "case": case,
            "rows_affected": changed,
            "message": (
                f"Standardized {changed} text values "
                f"using {case} case."
            ),
        }

    # 5. Convert to numeric
    if operation_type == "convert_numeric":
        if _is_identifier_column(column):
            raise CleaningValidationError(
                f"Numeric conversion is blocked for '{column}' "
                "because its name suggests an identifier or code. "
                "This protects IDs, phone numbers, postal codes, "
                "account numbers, and similar values."
            )

        converted = _validate_numeric_conversion(
            series,
            column,
        )

        result = df.copy()
        result[column] = converted

        return result, {
            "type": operation_type,
            "column": column,
            "rows_affected": int(series.notna().sum()),
            "warning": (
                "The text values will be converted into numeric "
                "values. Review the preview before approval."
            ),
            "message": f"Converted '{column}' to numeric values.",
        }

    # 6. Convert to datetime
    if operation_type == "convert_datetime":
        converted = _validate_datetime_conversion(
            series,
            column,
        )

        invalid_mask = series.notna() & converted.isna()
        invalid_count = int(invalid_mask.sum())
        converted_count = int(converted.notna().sum())
        original_missing_count = int(series.isna().sum())

        result = df.copy()
        result[column] = converted

        warning = (
            f"{invalid_count} non-empty value(s) in '{column}' could not "
            "be interpreted as dates and will become NULL in the cleaned "
            "version. Review the invalid-value count and preview before approval."
            if invalid_count
            else "The selected column will be converted to datetime values. "
                 "Review the preview before approval."
        )

        invalid_samples = [
            str(value)[:100]
            for value in series[invalid_mask].drop_duplicates().head(5).tolist()
        ]

        return result, {
            "type": operation_type,
            "column": column,
            "rows_affected": converted_count,
            "converted_values": converted_count,
            "invalid_values": invalid_count,
            "original_missing_values": original_missing_count,
            "invalid_value_samples": invalid_samples,
            "null_values_after_conversion": int(result[column].isna().sum()),
            "warning": warning,
            "message": (
                f"Converted {converted_count} value(s) in '{column}' to "
                f"datetime. {invalid_count} invalid non-empty value(s) "
                "were set to NULL."
            ),
        }

    raise CleaningValidationError(
        f"Unsupported cleaning operation: {operation_type}"
    )


def apply_cleaning_operations(
    df: pd.DataFrame,
    operations: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Apply cleaning operations to a separate DataFrame copy.

    Returns:
        Cleaned DataFrame and operation results.

    The original DataFrame is never modified.
    """

    if not df.columns.is_unique:
        raise CleaningValidationError(
            "Dataset contains duplicate column names."
        )

    if not operations:
        raise CleaningValidationError(
            "At least one cleaning operation is required."
        )

    cleaned = df.copy(deep=True)
    operation_results: list[dict[str, Any]] = []

    for operation in operations:
        cleaned, result = _apply_operation(
            cleaned,
            operation,
        )

        operation_results.append(result)

    return cleaned, operation_results


def generate_cleaning_preview(
    df: pd.DataFrame,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Apply proposed operations to a copy of the dataset.

    The original DataFrame is never modified or persisted.
    """

    original = df.copy(deep=True)

    preview, operation_results = apply_cleaning_operations(
        df,
        operations,
    )

    preview_records = preview.head(10).astype(object)

    preview_records = preview_records.where(
        pd.notna(preview_records),
        None,
    )

    return {
        "before": dataset_metrics(original),
        "after": dataset_metrics(preview),
        "operations": operation_results,
        "preview": preview_records.to_dict(orient="records"),
        "preview_rows": min(10, len(preview)),
        "total_rows_after_cleaning": len(preview),
    }