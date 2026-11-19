from __future__ import annotations

import math
from pathlib import Path

import duckdb

from app.data.duckdb_engine import (
    DuckDBEngineError,
    connect_read_only,
)

from app.schemas.execution import (
    AnalyticsExecutionRequest,
    DescriptiveAnalyticsResponse,
    DescriptiveStatistics,
)

from app.services.analytics_executor import AnalyticsExecutionError


def _quote_identifier(identifier: str) -> str:
    """Safely quote a DuckDB SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def execute_descriptive(
    path: Path,
    dataset_id: str,
    request: AnalyticsExecutionRequest,
) -> DescriptiveAnalyticsResponse:

    connection = None

    try:
        connection = connect_read_only(path)

        column = request.column

        if not column:
            raise AnalyticsExecutionError(
                "A column must be selected for descriptive analysis."
            )

        schema = connection.execute(
            "DESCRIBE SELECT * FROM dataset"
        ).fetchall()

        column_names = [item[0] for item in schema]

        if len(column_names) != len(set(column_names)):
            raise AnalyticsExecutionError(
                "Dataset contains duplicate column names."
            )

        if column not in column_names:
            raise AnalyticsExecutionError(
                f"Column '{column}' does not exist in the dataset."
            )

        quoted = _quote_identifier(column)
        converted = f"TRY_CAST({quoted} AS DOUBLE)"

        row_count = connection.execute(
            "SELECT COUNT(*) FROM dataset"
        ).fetchone()[0]

        if row_count == 0:
            raise AnalyticsExecutionError(
                "Cannot perform descriptive analysis on an empty dataset."
            )

        invalid_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM dataset
            WHERE {quoted} IS NOT NULL
              AND {converted} IS NULL
            """
        ).fetchone()[0]

        if invalid_count:
            raise AnalyticsExecutionError(
                f"Column '{column}' contains non-numeric values."
            )

        non_finite_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM dataset
            WHERE {converted} IS NOT NULL
              AND NOT ISFINITE({converted})
            """
        ).fetchone()[0]

        if non_finite_count:
            raise AnalyticsExecutionError(
                f"Column '{column}' contains non-finite numeric values."
            )

        valid_count, null_count = connection.execute(
            f"""
            SELECT
                COUNT({converted}),
                COUNT(*) - COUNT({converted})
            FROM dataset
            """
        ).fetchone()

        if valid_count == 0:
            raise AnalyticsExecutionError(
                f"Column '{column}' contains no valid numeric values."
            )

        # Calculate median without adding extremely large values.
        middle_values = connection.execute(
            f"""
            WITH ordered AS (
                SELECT
                    {converted} AS value,

                    ROW_NUMBER() OVER (
                        ORDER BY {converted}
                    ) AS row_number,

                    COUNT({converted}) OVER () AS value_count

                FROM dataset

                WHERE {converted} IS NOT NULL
            )

            SELECT value

            FROM ordered

            WHERE row_number IN (
                CAST(FLOOR((value_count + 1) / 2.0) AS BIGINT),
                CAST(FLOOR((value_count + 2) / 2.0) AS BIGINT)
            )

            ORDER BY row_number
            """
        ).fetchall()

        if len(middle_values) == 1:

            median = float(middle_values[0][0])

        elif len(middle_values) == 2:

            median = (
                float(middle_values[0][0]) / 2.0
                + float(middle_values[1][0]) / 2.0
            )

        else:
            raise AnalyticsExecutionError(
                "Unable to calculate the median for the selected column."
            )

        # Calculate mean and sample standard deviation using scaled values.
        # Scaling prevents intermediate overflow for very large finite values.
        mean, minimum, maximum, standard_deviation = (
            connection.execute(
                f"""
                WITH scaled AS (
                    SELECT
                        {converted} AS value,

                        MAX(
                            ABS({converted})
                        ) OVER () AS scale

                    FROM dataset
                )

                SELECT
                    (
                        FSUM(
                            value / NULLIF(scale, 0)
                        )
                        / COUNT(value)
                        * MAX(scale)
                    ) AS mean,

                    MIN(value) AS minimum,

                    MAX(value) AS maximum,

                    (
                        STDDEV_SAMP(
                            value / NULLIF(scale, 0)
                        )
                        * MAX(scale)
                    ) AS standard_deviation

                FROM scaled
                """
            ).fetchone()
        )

        statistics = {
            "mean": mean,
            "median": median,
            "minimum": minimum,
            "maximum": maximum,
            "standard_deviation": standard_deviation,
        }

        # Reject non-finite statistical results.
        for name, value in statistics.items():

            if value is not None and not math.isfinite(float(value)):
                raise AnalyticsExecutionError(
                    f"The descriptive {name} calculation produced "
                    "a non-finite result."
                )

        return DescriptiveAnalyticsResponse(
            dataset_id=dataset_id,
            operation=request.operation,
            column=column,
            row_count=int(row_count),
            valid_value_count=int(valid_count),
            null_count=int(null_count),
            statistics=DescriptiveStatistics(
                mean=float(mean),
                median=float(median),
                minimum=float(minimum),
                maximum=float(maximum),
                standard_deviation=(
                    float(standard_deviation)
                    if standard_deviation is not None
                    else None
                ),
            ),
        )

    except (
        AnalyticsExecutionError,
        FileNotFoundError,
        DuckDBEngineError,
    ):
        raise

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB failed to execute descriptive analysis."
        ) from exc

    finally:
        if connection is not None:
            connection.close()