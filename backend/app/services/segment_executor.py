from pathlib import Path
import math

import duckdb

from app.data.duckdb_engine import (
    DuckDBEngineError,
    connect_read_only,
)

from app.schemas.execution import (
    AnalyticsExecutionGroup,
    AnalyticsExecutionRequest,
    SegmentComparisonResponse,
)

from app.services.analytics_executor import AnalyticsExecutionError


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_group_value(value):

    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "item"):
        return value.item()

    return value


def execute_segment_comparison(
    path: Path,
    dataset_id: str,
    request: AnalyticsExecutionRequest,
) -> SegmentComparisonResponse:

    connection = None

    try:
        connection = connect_read_only(path)

        group_by = request.group_by
        column = request.column
        aggregation_enum = request.aggregation

        if not group_by:
            raise AnalyticsExecutionError(
                "A grouping column must be selected."
            )

        if aggregation_enum is None:
            raise AnalyticsExecutionError(
                "An aggregation must be selected."
            )

        aggregation = aggregation_enum.value.upper()

        if aggregation not in {
            "COUNT", "SUM", "AVERAGE", "MIN", "MAX", "MEDIAN"
        }:
            raise AnalyticsExecutionError(
                "Unsupported aggregation. Use COUNT, SUM, AVERAGE, MIN, MAX, or MEDIAN."
            )

        if aggregation != "COUNT" and not column:
            raise AnalyticsExecutionError(
                "A numeric measure column is required for this aggregation."
            )

        if column and group_by == column:
            raise AnalyticsExecutionError(
                "The grouping column and measure column must be different."
            )

        schema = connection.execute(
            "DESCRIBE SELECT * FROM dataset"
        ).fetchall()

        column_names = [item[0] for item in schema]

        if len(column_names) != len(set(column_names)):
            raise AnalyticsExecutionError(
                "Dataset contains duplicate column names."
            )

        if group_by not in column_names:
            raise AnalyticsExecutionError(
                f"Grouping column '{group_by}' does not exist."
            )

        if column and column not in column_names:
            raise AnalyticsExecutionError(
                f"Measure column '{column}' does not exist."
            )

        quoted_group = _quote_identifier(group_by)
        quoted_measure = (
            _quote_identifier(column) if column else None
        )

        row_count = connection.execute(
            "SELECT COUNT(*) FROM dataset"
        ).fetchone()[0]

        if row_count == 0:
            raise AnalyticsExecutionError(
                "Cannot compare segments in an empty dataset."
            )

        if aggregation == "COUNT":

            value_expression = (
                f"COUNT({quoted_measure})"
                if quoted_measure else "COUNT(*)"
            )

            valid_expression = value_expression

            null_expression = (
                f"COUNT(*) - COUNT({quoted_measure})"
                if quoted_measure else "0"
            )

            query = f"""
                SELECT
                    {quoted_group} AS group_value,
                    {value_expression} AS metric,
                    COUNT(*) AS row_count,
                    {valid_expression} AS valid_value_count,
                    {null_expression} AS null_count
                FROM dataset
                GROUP BY {quoted_group}
            """

        else:

            converted = (
                f"TRY_CAST({quoted_measure} AS DOUBLE)"
            )

            invalid_count = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM dataset
                WHERE {quoted_measure} IS NOT NULL
                  AND {converted} IS NULL
                """
            ).fetchone()[0]

            if invalid_count:
                raise AnalyticsExecutionError(
                    f"Measure column '{column}' contains non-numeric values."
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
                    f"Measure column '{column}' contains non-finite values."
                )

            if aggregation == "SUM":

                query = f"""
                    SELECT
                        {quoted_group} AS group_value,
                        FSUM({converted}) AS metric,
                        COUNT(*) AS row_count,
                        COUNT({converted}) AS valid_value_count,
                        COUNT(*) - COUNT({converted}) AS null_count
                    FROM dataset
                    GROUP BY {quoted_group}
                """

            elif aggregation in {"MIN", "MAX", "MEDIAN"}:
                aggregate_function = {
                    "MIN": "MIN",
                    "MAX": "MAX",
                    "MEDIAN": "MEDIAN",
                }[aggregation]

                query = f"""
                    SELECT
                        {quoted_group} AS group_value,
                        {aggregate_function}({converted}) AS metric,
                        COUNT(*) AS row_count,
                        COUNT({converted}) AS valid_value_count,
                        COUNT(*) - COUNT({converted}) AS null_count
                    FROM dataset
                    GROUP BY {quoted_group}
                """

            else:

                query = f"""
                    WITH scaled AS (
                        SELECT
                            {quoted_group} AS group_value,
                            {converted} AS measure_value,
                            MAX(ABS({converted}))
                                OVER (
                                    PARTITION BY {quoted_group}
                                ) AS scale
                        FROM dataset
                    )

                    SELECT
                        group_value,
                        AVG(
                            measure_value / NULLIF(scale, 0)
                        ) * MAX(scale) AS metric,
                        COUNT(*) AS row_count,
                        COUNT(measure_value) AS valid_value_count,
                        COUNT(*) - COUNT(measure_value) AS null_count
                    FROM scaled
                    GROUP BY group_value
                """

        results = connection.execute(query).fetchall()

        results.sort(
            key=lambda item: (
                item[0] is None,
                str(_normalize_group_value(item[0])).casefold()
                if item[0] is not None else "",
                type(item[0]).__name__,
            )
        )

        segments = []

        for (
            group_value,
            metric,
            segment_rows,
            valid_count,
            null_count,
        ) in results:

            if metric is not None:
                metric = float(metric)

                if not math.isfinite(metric):
                    raise AnalyticsExecutionError(
                        "The aggregation produced a non-finite result."
                    )

            segments.append(
                AnalyticsExecutionGroup(
                    group=_normalize_group_value(group_value),
                    value=metric,
                    row_count=int(segment_rows),
                    valid_value_count=int(valid_count),
                    null_count=int(null_count),
                )
            )

        return SegmentComparisonResponse(
            dataset_id=dataset_id,
            operation=request.operation,
            column=column,
            aggregation=aggregation_enum,
            segment_by=group_by,
            segments=segments,
        )

    except (
        AnalyticsExecutionError,
        FileNotFoundError,
        DuckDBEngineError,
    ):
        raise

    except duckdb.Error as exc:
        raise AnalyticsExecutionError(
            "DuckDB failed to execute segment comparison."
        ) from exc

    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalyticsExecutionError(
            "Unable to process segment comparison results."
        ) from exc

    finally:
        if connection is not None:
            connection.close()