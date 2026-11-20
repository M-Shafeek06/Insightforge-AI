from pathlib import Path

import duckdb

from app.data.duckdb_engine import (
    DuckDBEngineError,
    connect_read_only,
)
from app.schemas.execution import (
    AnalyticsExecutionRequest,
    TrendAnalyticsResponse,
)
from app.services.analytics_executor import AnalyticsExecutionError


def _quote_identifier(identifier: str) -> str:
    """Safely quote a SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def execute_trend(
    path: Path,
    dataset_id: str,
    request: AnalyticsExecutionRequest,
) -> TrendAnalyticsResponse:
    """
    Execute time-based trend analysis using DuckDB.

    Supported intervals:
    - Day
    - Week
    - Month
    - Quarter
    - Year

    Supported aggregations:
    - COUNT
    - SUM
    - AVERAGE
    - MIN
    - MAX
    - MEDIAN
    """

    connection = None

    try:
        connection = connect_read_only(path)

        date_column = request.date_column
        column = request.column
        interval = request.interval
        aggregation = request.aggregation

        if not date_column:
            raise AnalyticsExecutionError(
                "A date column must be selected for trend analysis."
            )

        if not interval:
            raise AnalyticsExecutionError(
                "A time interval must be selected."
            )

        if not aggregation:
            raise AnalyticsExecutionError(
                "An aggregation must be selected."
            )

        interval = interval.value.lower()
        aggregation = aggregation.value.upper()

        frequencies = {
            "day": "day",
            "week": "week",
            "month": "month",
            "quarter": "quarter",
            "year": "year",
        }

        if interval not in frequencies:
            raise AnalyticsExecutionError(
                "Unsupported interval. Use day, week, month, quarter, or year."
            )

        if aggregation not in {
            "COUNT", "SUM", "AVERAGE", "MIN", "MAX", "MEDIAN"
        }:
            raise AnalyticsExecutionError(
                "Unsupported aggregation. Use COUNT, SUM, AVERAGE, MIN, MAX, or MEDIAN."
            )

        if aggregation != "COUNT" and not column:
            raise AnalyticsExecutionError(
                "A measure column is required for this aggregation."
            )

        if column == date_column:
            raise AnalyticsExecutionError(
                "The date column and measure column must be different."
            )

        # Validate dataset schema.
        schema = connection.execute(
            "DESCRIBE SELECT * FROM dataset"
        ).fetchall()

        column_names = [item[0] for item in schema]

        if len(column_names) != len(set(column_names)):
            raise AnalyticsExecutionError(
                "Dataset contains duplicate column names."
            )

        if date_column not in column_names:
            raise AnalyticsExecutionError(
                f"Date column '{date_column}' does not exist."
            )

        if column and column not in column_names:
            raise AnalyticsExecutionError(
                f"Measure column '{column}' does not exist."
            )

        quoted_date = _quote_identifier(date_column)

        row_count = connection.execute(
            "SELECT COUNT(*) FROM dataset"
        ).fetchone()[0]

        if row_count == 0:
            raise AnalyticsExecutionError(
                "Cannot perform trend analysis on an empty dataset."
            )

        # Parse dates, treating invalid dates as NULL.
        parsed_date = f"TRY_CAST({quoted_date} AS TIMESTAMP)"

        valid_date_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM dataset
            WHERE {parsed_date} IS NOT NULL
            """
        ).fetchone()[0]

        if valid_date_count == 0:
            raise AnalyticsExecutionError(
                f"Date column '{date_column}' contains no valid dates."
            )

        # Build the period expression.
        if interval == "week":
            period_expression = (
                f"DATE_TRUNC('week', {parsed_date}) + INTERVAL '6 days'"
            )
        else:
            period_expression = (
                f"DATE_TRUNC('{frequencies[interval]}', {parsed_date})"
            )

        # Build aggregation and measure-count expressions.
        if aggregation == "COUNT":
            quoted_measure = _quote_identifier(column) if column else None

            aggregate_expression = (
                f"COUNT({quoted_measure})"
                if quoted_measure
                else "COUNT(*)"
            )

            valid_count_expression = aggregate_expression
            null_count_expression = (
                f"COUNT(*) - COUNT({quoted_measure})"
                if quoted_measure
                else "0"
            )

        else:
            quoted_measure = _quote_identifier(column)
            converted_measure = (
                f"TRY_CAST({quoted_measure} AS DOUBLE)"
            )

            invalid_count = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM dataset
                WHERE {parsed_date} IS NOT NULL
                  AND {quoted_measure} IS NOT NULL
                  AND {converted_measure} IS NULL
                """
            ).fetchone()[0]

            if invalid_count > 0:
                raise AnalyticsExecutionError(
                    f"Measure column '{column}' contains non-numeric values."
                )

            non_finite_count = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM dataset
                WHERE {parsed_date} IS NOT NULL
                  AND {converted_measure} IS NOT NULL
                  AND NOT ISFINITE({converted_measure})
                """
            ).fetchone()[0]

            if non_finite_count > 0:
                raise AnalyticsExecutionError(
                    f"Measure column '{column}' contains non-finite values."
                )

            aggregate_functions = {
                "SUM": f"FSUM({converted_measure})",
                "AVERAGE": f"AVG({converted_measure})",
                "MIN": f"MIN({converted_measure})",
                "MAX": f"MAX({converted_measure})",
                "MEDIAN": f"MEDIAN({converted_measure})",
            }
            aggregate_expression = aggregate_functions[aggregation]

            valid_count_expression = (
                f"COUNT({converted_measure})"
            )

            null_count_expression = (
                f"COUNT(*) - COUNT({converted_measure})"
            )

        # Execute the time-based aggregation.
        query = f"""
            SELECT
                {period_expression} AS period,
                {aggregate_expression} AS metric,
                COUNT(*) AS period_row_count,
                {valid_count_expression} AS valid_value_count,
                {null_count_expression} AS null_count
            FROM dataset
            WHERE {parsed_date} IS NOT NULL
            GROUP BY period
            ORDER BY period
        """

        results = connection.execute(query).fetchall()

        points = []

        for (
            period,
            metric,
            period_row_count,
            valid_value_count,
            null_count,
        ) in results:
            points.append(
                {
                    "period": period.isoformat(),
                    "value": (
                        float(metric)
                        if metric is not None
                        else None
                    ),
                    "row_count": int(period_row_count),
                    "valid_value_count": int(valid_value_count),
                    "null_count": int(null_count),
                }
            )

        return TrendAnalyticsResponse(
            dataset_id=dataset_id,
            operation=request.operation,
            column=column,
            date_column=date_column,
            aggregation=request.aggregation,
            interval=request.interval,
            points=points,
        )

    except (
        AnalyticsExecutionError,
        FileNotFoundError,
        DuckDBEngineError,
    ):
        raise

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB failed to execute trend analysis."
        ) from exc

    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyticsExecutionError(
            "Unable to process trend analysis results."
        ) from exc

    finally:
        if connection is not None:
            connection.close()