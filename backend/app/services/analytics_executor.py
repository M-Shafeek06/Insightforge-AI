from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pandas as pd

from app.data.duckdb_engine import (
    connect_read_only,
    DuckDBEngineError,
)
from app.schemas.execution import (
    Aggregation,
    AnalyticsExecutionGroup,
    AnalyticsExecutionRequest,
    AnalyticsExecutionResponse,
    ExecutionOperation,
    GroupedAnalyticsExecutionResponse,
)
from app.services.dataset_versions import get_dataset_versions
from app.services.settings import settings
from app.services.storage import resolve_dataset_path


class AnalyticsExecutionError(ValueError):
    """Raised when an analytical operation cannot be executed."""


class DatasetNotFoundError(FileNotFoundError):
    """Raised when the requested dataset does not exist."""


NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "UHUGEINT",
    "FLOAT",
    "REAL",
    "DOUBLE",
    "DECIMAL",
}


def _stable_mean(values: pd.Series):
    """Calculate a numerically stable mean."""

    valid_values = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if valid_values.empty:
        return None

    numeric_values = [
        float(value)
        for value in valid_values
    ]

    scale = max(
        abs(value)
        for value in numeric_values
    )

    if scale == 0:
        return 0.0

    normalized_mean = math.fsum(
        value / scale
        for value in numeric_values
    ) / len(numeric_values)

    result = normalized_mean * scale

    if not math.isfinite(result):
        raise AnalyticsExecutionError(
            "The aggregation produced a non-finite result."
        )

    return result


def _quote_identifier(identifier: str) -> str:
    """Safely quote a DuckDB SQL identifier."""

    return '"' + identifier.replace('"', '""') + '"'


def _get_columns(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, str]:

    rows = connection.execute(
        "DESCRIBE SELECT * FROM dataset"
    ).fetchall()

    return {
        row[0]: row[1].upper()
        for row in rows
    }


def _validate_dataset_columns(
    columns: dict[str, str],
    request: AnalyticsExecutionRequest,
) -> None:

    if request.column not in columns:
        raise AnalyticsExecutionError(
            f"Column '{request.column}' does not exist in the dataset."
        )

    if (
        request.group_by is not None
        and request.group_by not in columns
    ):
        raise AnalyticsExecutionError(
            f"Grouping column '{request.group_by}' "
            "does not exist in the dataset."
        )


def _validate_numeric_column(
    connection: duckdb.DuckDBPyConnection,
    column: str,
) -> None:
    """
    Validate numeric values using TRY_CAST.

    Numeric values stored as text are accepted when every non-null
    value can be converted to DOUBLE.
    """

    quoted_column = _quote_identifier(column)

    raw_count, valid_count, invalid_count = connection.execute(
        f"""
        SELECT
            COUNT({quoted_column}),
            COUNT(TRY_CAST({quoted_column} AS DOUBLE)),
            COUNT(*) FILTER (
                WHERE {quoted_column} IS NOT NULL
                  AND TRY_CAST({quoted_column} AS DOUBLE) IS NULL
            )
        FROM dataset
        """
    ).fetchone()

    # Check invalid values first so text-only columns receive
    # the correct numeric-column validation error.
    if invalid_count > 0:
        raise AnalyticsExecutionError(
            f"Aggregation requires a numeric column: '{column}'."
        )

    if raw_count == 0 or valid_count == 0:
        raise AnalyticsExecutionError(
            "The selected column contains no valid values."
        )
    
    if invalid_count > 0:
        raise AnalyticsExecutionError(
            f"Aggregation requires a numeric column: '{column}'."
        )


def _validate_finite_values(
    connection: duckdb.DuckDBPyConnection,
    column: str,
    *,
    context: str = "selected",
) -> None:
    """
    Reject NaN and infinite values.

    The TRY_CAST expression also supports numeric values stored as text.
    """

    quoted_column = _quote_identifier(column)

    invalid_count = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM dataset
        WHERE {quoted_column} IS NOT NULL
          AND TRY_CAST({quoted_column} AS DOUBLE) IS NOT NULL
          AND NOT ISFINITE(
              TRY_CAST({quoted_column} AS DOUBLE)
          )
        """
    ).fetchone()[0]

    if invalid_count > 0:

        if context == "grouping":
            message = (
                "The grouping column contains non-finite numeric values."
            )
        else:
            message = (
                "The selected column contains non-finite numeric values."
            )

        raise AnalyticsExecutionError(message)


def _validate_numeric_grouping_column(
    connection: duckdb.DuckDBPyConnection,
    column: str,
    columns: dict[str, str],
) -> None:
    """
    Check numeric grouping columns for non-finite values.

    Also recognizes numeric-looking VARCHAR columns, without treating
    ordinary text categories as numeric columns.
    """

    column_type = (
        columns[column].split("(")[0].strip()
    )

    if column_type in NUMERIC_TYPES:
        _validate_finite_values(
            connection,
            column,
            context="grouping",
        )
        return

    quoted_column = _quote_identifier(column)

    raw_count, valid_count, invalid_count = connection.execute(
        f"""
        SELECT
            COUNT({quoted_column}),
            COUNT(TRY_CAST({quoted_column} AS DOUBLE)),
            COUNT(*) FILTER (
                WHERE {quoted_column} IS NOT NULL
                  AND TRY_CAST({quoted_column} AS DOUBLE) IS NULL
            )
        FROM dataset
        """
    ).fetchone()

    if (
        raw_count > 0
        and valid_count > 0
        and invalid_count == 0
    ):
        _validate_finite_values(
            connection,
            column,
            context="grouping",
        )


def _get_dataset_connection(
    path: Path,
) -> duckdb.DuckDBPyConnection:

    try:
        connection = connect_read_only(path)

        row_count = connection.execute(
            "SELECT COUNT(*) FROM dataset"
        ).fetchone()[0]

        if row_count == 0:
            connection.close()

            raise AnalyticsExecutionError(
                "Cannot execute analytics on an empty dataset."
            )

        return connection

    except (
        FileNotFoundError,
        AnalyticsExecutionError,
    ):
        raise

    except DuckDBEngineError as exc:
        raise AnalyticsExecutionError(
            "Unable to initialize the analytical engine."
        ) from exc


def find_dataset_path(
    dataset_id: str,
    upload_dir: Path | None = None,
    version: str = "original",
) -> Path:
    """Resolve the exact dataset version identified by ``dataset_id``.

    The frontend passes the ID of the currently selected version. The
    version registry can be found using either the original dataset ID or
    any registered cleaned-version ID. Therefore, do not choose a version
    based on the legacy ``version`` flag: doing so can silently execute
    analytics against the original dataset after the user selected V1/V2.

    ``version`` remains in the signature for backward compatibility with
    existing callers, but the selected dataset ID is authoritative.
    Legacy datasets without a version registry continue to use the
    original storage resolver.
    """

    try:
        registry = get_dataset_versions(dataset_id)

        selected = next(
            (
                item
                for item in registry["versions"]
                if item["dataset_id"] == dataset_id
            ),
            None,
        )

        if selected is None:
            # A registry was found, but the requested ID is not one of its
            # registered versions. Never substitute the original/latest file.
            raise DatasetNotFoundError(
                "The requested dataset version is not registered."
            )

        selected_id = selected["dataset_id"]
        directories = (
            upload_dir or settings.upload_dir,
            settings.processed_dir,
        )

        for directory in directories:
            for extension in (".csv", ".xlsx"):
                path = directory / f"{selected_id}{extension}"
                if path.is_file():
                    return path

        raise DatasetNotFoundError(
            "The selected dataset version file is missing."
        )

    except ValueError:
        # Preserve support for legacy non-UUID dataset identifiers.
        try:
            return resolve_dataset_path(dataset_id)
        except FileNotFoundError as exc:
            raise DatasetNotFoundError(
                "Dataset not found."
            ) from exc

    except FileNotFoundError as exc:
        # A valid UUID may belong to a legacy dataset that predates version
        # registries. Resolve only the exact requested ID; never substitute
        # a different registered version.
        if isinstance(exc, DatasetNotFoundError):
            raise

        try:
            return resolve_dataset_path(dataset_id)
        except FileNotFoundError as fallback_exc:
            raise DatasetNotFoundError(
                "Dataset not found."
            ) from fallback_exc


def execute_kpi(
    path: Path,
    dataset_id: str,
    request: AnalyticsExecutionRequest,
) -> AnalyticsExecutionResponse:

    if request.aggregation is None:
        raise AnalyticsExecutionError(
            "An aggregation is required for KPI execution."
        )

    connection = _get_dataset_connection(path)

    try:
        columns = _get_columns(connection)

        _validate_dataset_columns(
            columns,
            request,
        )

        column = _quote_identifier(request.column)

        row_count, valid_value_count, null_count = (
            connection.execute(
                f"""
                SELECT
                    COUNT(*),
                    COUNT({column}),
                    COUNT(*) - COUNT({column})
                FROM dataset
                """
            ).fetchone()
        )

        if request.aggregation == Aggregation.COUNT:

            result = valid_value_count

        else:

            _validate_numeric_column(
                connection,
                request.column,
            )

            _validate_finite_values(
                connection,
                request.column,
            )

            if request.aggregation == Aggregation.SUM:

                result = connection.execute(
                    f"""
                    SELECT
                        FSUM(
                            TRY_CAST({column} AS DOUBLE)
                        )
                    FROM dataset
                    """
                ).fetchone()[0]

            elif request.aggregation == Aggregation.AVERAGE:

                result = connection.execute(
                    f"""
                    WITH scaled AS (
                        SELECT
                            TRY_CAST({column} AS DOUBLE) AS value,
                            MAX(
                                ABS(
                                    TRY_CAST({column} AS DOUBLE)
                                )
                            ) OVER () AS scale
                        FROM dataset
                    )

                    SELECT
                        FSUM(
                            value / NULLIF(scale, 0)
                        )
                        / COUNT(value)
                        * MAX(scale)
                    FROM scaled
                    """
                ).fetchone()[0]

            elif request.aggregation == Aggregation.MIN:

                result = connection.execute(
                    f"""
                    SELECT MIN(TRY_CAST({column} AS DOUBLE))
                    FROM dataset
                    """
                ).fetchone()[0]

            elif request.aggregation == Aggregation.MAX:

                result = connection.execute(
                    f"""
                    SELECT MAX(TRY_CAST({column} AS DOUBLE))
                    FROM dataset
                    """
                ).fetchone()[0]

            elif request.aggregation == Aggregation.MEDIAN:

                result = connection.execute(
                    f"""
                    SELECT MEDIAN(TRY_CAST({column} AS DOUBLE))
                    FROM dataset
                    """
                ).fetchone()[0]

            else:
                raise AnalyticsExecutionError(
                    "The requested aggregation is not supported."
                )

            if result is None:
                result = 0.0

        numeric_result = float(result)

        if not math.isfinite(numeric_result):
            raise AnalyticsExecutionError(
                "The aggregation produced a non-finite result."
            )

        return AnalyticsExecutionResponse(
            dataset_id=dataset_id,
            operation=ExecutionOperation.KPI,
            column=request.column,
            aggregation=request.aggregation,
            value=numeric_result,
            row_count=row_count,
            valid_value_count=valid_value_count,
            null_count=null_count,
        )

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB could not execute the KPI analysis."
        ) from exc

    finally:
        connection.close()


def execute_grouped_kpi(
    path: Path,
    dataset_id: str,
    request: AnalyticsExecutionRequest,
) -> GroupedAnalyticsExecutionResponse:

    if request.aggregation is None:
        raise AnalyticsExecutionError(
            "An aggregation is required for grouped execution."
        )

    if request.group_by is None:
        raise AnalyticsExecutionError(
            "A grouping column is required for grouped execution."
        )

    connection = _get_dataset_connection(path)

    try:
        columns = _get_columns(connection)

        _validate_dataset_columns(
            columns,
            request,
        )

        value_column = _quote_identifier(request.column)
        group_column = _quote_identifier(request.group_by)

        if request.aggregation != Aggregation.COUNT:

            _validate_numeric_column(
                connection,
                request.column,
            )

            _validate_finite_values(
                connection,
                request.column,
            )

        _validate_numeric_grouping_column(
            connection,
            request.group_by,
            columns,
        )

        if request.aggregation == Aggregation.COUNT:

            aggregation_sql = (
                f"COUNT({value_column})"
            )

            query = f"""
                SELECT
                    {group_column},
                    {aggregation_sql} AS value,
                    COUNT(*) AS row_count,
                    COUNT({value_column}) AS valid_value_count,
                    COUNT(*) - COUNT({value_column}) AS null_count
                FROM dataset
                GROUP BY {group_column}
                ORDER BY
                    {group_column} IS NULL,
                    CAST({group_column} AS VARCHAR)
            """

        elif request.aggregation == Aggregation.SUM:

            aggregation_sql = (
                f"FSUM(TRY_CAST({value_column} AS DOUBLE))"
            )

            query = f"""
                SELECT
                    {group_column},
                    {aggregation_sql} AS value,
                    COUNT(*) AS row_count,
                    COUNT({value_column}) AS valid_value_count,
                    COUNT(*) - COUNT({value_column}) AS null_count
                FROM dataset
                GROUP BY {group_column}
                ORDER BY
                    {group_column} IS NULL,
                    CAST({group_column} AS VARCHAR)
            """

        elif request.aggregation == Aggregation.AVERAGE:

            query = f"""
                WITH scaled AS (
                    SELECT
                        {group_column} AS group_key,

                        TRY_CAST(
                            {value_column} AS DOUBLE
                        ) AS measure_value,

                        MAX(
                            ABS(
                                TRY_CAST(
                                    {value_column} AS DOUBLE
                                )
                            )
                        ) OVER (
                            PARTITION BY {group_column}
                        ) AS scale

                    FROM dataset
                )

                SELECT
                    group_key,

                    (
                        FSUM(
                            measure_value / NULLIF(scale, 0)
                        )
                        / COUNT(measure_value)
                        * MAX(scale)
                    ) AS value,

                    COUNT(*) AS row_count,

                    COUNT(measure_value) AS valid_value_count,

                    COUNT(*) - COUNT(measure_value) AS null_count

                FROM scaled

                GROUP BY group_key

                ORDER BY
                    group_key IS NULL,
                    CAST(group_key AS VARCHAR)
            """

        elif request.aggregation in {
            Aggregation.MIN,
            Aggregation.MAX,
            Aggregation.MEDIAN,
        }:
            aggregate_functions = {
                Aggregation.MIN: "MIN",
                Aggregation.MAX: "MAX",
                Aggregation.MEDIAN: "MEDIAN",
            }
            aggregate_function = aggregate_functions[request.aggregation]

            query = f"""
                SELECT
                    {group_column} AS group_key,
                    {aggregate_function}(
                        TRY_CAST({value_column} AS DOUBLE)
                    ) AS value,
                    COUNT(*) AS row_count,
                    COUNT(TRY_CAST({value_column} AS DOUBLE)) AS valid_value_count,
                    COUNT(*) - COUNT(
                        TRY_CAST({value_column} AS DOUBLE)
                    ) AS null_count
                FROM dataset
                GROUP BY {group_column}
                ORDER BY
                    {group_column} IS NULL,
                    CAST({group_column} AS VARCHAR)
            """

        else:
            raise AnalyticsExecutionError(
                "The requested aggregation is not supported."
            )

        rows = connection.execute(query).fetchall()

        groups = []

        for (
            group_value,
            result,
            group_row_count,
            valid_value_count,
            null_count,
        ) in rows:

            if result is not None:

                result = float(result)

                if not math.isfinite(result):
                    raise AnalyticsExecutionError(
                        "The aggregation produced a non-finite result."
                    )

            if group_value is not None:

                if hasattr(group_value, "isoformat"):
                    group_value = group_value.isoformat()

                elif hasattr(group_value, "item"):
                    group_value = group_value.item()

                if not isinstance(
                    group_value,
                    (str, int, float, bool),
                ):
                    group_value = str(group_value)

            groups.append(
                AnalyticsExecutionGroup(
                    group=group_value,
                    value=result,
                    row_count=group_row_count,
                    valid_value_count=valid_value_count,
                    null_count=null_count,
                )
            )

        return GroupedAnalyticsExecutionResponse(
            dataset_id=dataset_id,
            operation=ExecutionOperation.KPI,
            column=request.column,
            aggregation=request.aggregation,
            group_by=request.group_by,
            groups=groups,
        )

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB could not execute the grouped KPI analysis."
        ) from exc

    finally:
        connection.close()