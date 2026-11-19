from __future__ import annotations

import math
from pathlib import Path

import duckdb

from app.data.duckdb_engine import (
    connect_read_only,
    DuckDBEngineError,
)
from app.schemas.execution import (
    CorrelationAnalyticsResponse,
    CorrelationDataPoint,
    ExecutionOperation,
)
from app.services.analytics_executor import AnalyticsExecutionError


MAX_CORRELATION_CHART_POINTS = 1000


def execute_correlation(
    path: Path,
    dataset_id: str,
    column: str,
    second_column: str,
) -> CorrelationAnalyticsResponse:
    """Calculate Pearson correlation using DuckDB."""

    if column == second_column:
        raise AnalyticsExecutionError(
            "Select two different columns for correlation analysis."
        )

    connection = None

    try:
        connection = connect_read_only(path)

        column_info = connection.execute(
            "DESCRIBE SELECT * FROM dataset"
        ).fetchall()

        columns = {
            item[0]: item[1].upper()
            for item in column_info
        }

        for requested_column in (column, second_column):
            if requested_column not in columns:
                raise AnalyticsExecutionError(
                    f"Column '{requested_column}' does not exist "
                    "in the dataset."
                )

            data_type = columns[requested_column].split("(")[0].strip()

            if data_type not in {
                "TINYINT", "SMALLINT", "INTEGER", "BIGINT",
                "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER",
                "UBIGINT", "UHUGEINT", "FLOAT", "REAL",
                "DOUBLE", "DECIMAL",
            }:
                raise AnalyticsExecutionError(
                    f"Column '{requested_column}' must contain numeric "
                    "values for correlation analysis."
                )

        quoted_first = '"' + column.replace('"', '""') + '"'
        quoted_second = '"' + second_column.replace('"', '""') + '"'

        invalid_values = connection.execute(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE {quoted_first} IS NOT NULL
                    AND NOT isfinite({quoted_first})
                ),
                COUNT(*) FILTER (
                    WHERE {quoted_second} IS NOT NULL
                    AND NOT isfinite({quoted_second})
                )
            FROM dataset
            """
        ).fetchone()

        if invalid_values[0] or invalid_values[1]:
            raise AnalyticsExecutionError(
                "Selected columns contain non-finite numeric values."
            )

        row_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM dataset
            WHERE {quoted_first} IS NOT NULL
              AND {quoted_second} IS NOT NULL
            """
        ).fetchone()[0]

        if row_count < 2:
            raise AnalyticsExecutionError(
                "Correlation requires at least two rows with valid "
                "values in both selected columns."
            )

        statistics = connection.execute(
            f"""
            SELECT
                MIN({quoted_first}),
                MAX({quoted_first}),
                MIN({quoted_second}),
                MAX({quoted_second}),
                MAX(ABS({quoted_first})),
                MAX(ABS({quoted_second}))
            FROM dataset
            WHERE {quoted_first} IS NOT NULL
              AND {quoted_second} IS NOT NULL
            """
        ).fetchone()

        first_min, first_max, second_min, second_max, first_scale, second_scale = statistics

        if first_min == first_max:
            raise AnalyticsExecutionError(
                f"Column '{column}' is constant among valid paired "
                "observations; correlation is undefined."
            )

        if second_min == second_max:
            raise AnalyticsExecutionError(
                f"Column '{second_column}' is constant among valid paired "
                "observations; correlation is undefined."
            )

        if first_scale == 0 or second_scale == 0:
            raise AnalyticsExecutionError(
                "Correlation is undefined for a constant column."
            )

        coefficient = connection.execute(
            f"""
            SELECT corr(
                {quoted_first} / ?,
                {quoted_second} / ?
            )
            FROM dataset
            WHERE {quoted_first} IS NOT NULL
              AND {quoted_second} IS NOT NULL
            """,
            [float(first_scale), float(second_scale)],
        ).fetchone()[0]

        if coefficient is None or not math.isfinite(float(coefficient)):
            raise AnalyticsExecutionError(
                "Correlation could not be calculated reliably "
                "for these columns."
            )

        coefficient = max(-1.0, min(1.0, float(coefficient)))

        absolute_coefficient = abs(coefficient)

        if absolute_coefficient < 0.1:
            strength = "negligible"
        elif absolute_coefficient < 0.3:
            strength = "weak"
        elif absolute_coefficient < 0.7:
            strength = "moderate"
        else:
            strength = "strong"

        if coefficient > 0:
            direction = "positive"
        elif coefficient < 0:
            direction = "negative"
        else:
            direction = "none"

        sampled = row_count > MAX_CORRELATION_CHART_POINTS

        if sampled:
            sample_query = f"""
                SELECT
                    {quoted_first},
                    {quoted_second}
                FROM (
                    SELECT
                        {quoted_first},
                        {quoted_second},
                        ROW_NUMBER() OVER () AS row_number
                    FROM dataset
                    WHERE {quoted_first} IS NOT NULL
                      AND {quoted_second} IS NOT NULL
                )
                WHERE (
                    (row_number - 1) * ?
                    // ?
                ) != (
                    (row_number - 2) * ?
                    // ?
                )
                ORDER BY row_number
                LIMIT ?
            """

            # Deterministic bounded chart sample.
            positions = [
                (index * (row_count - 1))
                // (MAX_CORRELATION_CHART_POINTS - 1)
                for index in range(MAX_CORRELATION_CHART_POINTS)
            ]

            points_rows = connection.execute(
                f"""
                SELECT
                    {quoted_first},
                    {quoted_second}
                FROM (
                    SELECT
                        {quoted_first},
                        {quoted_second},
                        ROW_NUMBER() OVER () - 1 AS row_number
                    FROM dataset
                    WHERE {quoted_first} IS NOT NULL
                      AND {quoted_second} IS NOT NULL
                ) AS paired
                WHERE row_number IN (
                    SELECT UNNEST(?::BIGINT[])
                )
                ORDER BY row_number
                """,
                [positions],
            ).fetchall()

        else:
            points_rows = connection.execute(
                f"""
                SELECT
                    {quoted_first},
                    {quoted_second}
                FROM dataset
                WHERE {quoted_first} IS NOT NULL
                  AND {quoted_second} IS NOT NULL
                """
            ).fetchall()

        points = [
            CorrelationDataPoint(
                x=float(x_value),
                y=float(y_value),
            )
            for x_value, y_value in points_rows
        ]

        return CorrelationAnalyticsResponse(
            dataset_id=dataset_id,
            operation=ExecutionOperation.CORRELATION,
            column=column,
            second_column=second_column,
            correlation=coefficient,
            observation_count=row_count,
            strength=strength,
            direction=direction,
            points=points,
            sampled=sampled,
        )

    except DuckDBEngineError as exc:
        raise AnalyticsExecutionError(
            "Unable to initialize DuckDB for correlation analysis."
        ) from exc

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB could not execute correlation analysis."
        ) from exc

    finally:
        if connection is not None:
            connection.close()