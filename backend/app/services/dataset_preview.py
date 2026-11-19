from __future__ import annotations

import json
import logging
from typing import Any

import duckdb

from app.data.duckdb_engine import (
    DuckDBEngineError,
    connect_read_only,
)
from app.services.analytics_executor import find_dataset_path


logger = logging.getLogger(__name__)

PREVIEW_LIMIT = 1000
DEFAULT_PAGE_SIZE = 10


class DatasetPreviewError(RuntimeError):
    """Raised when a dataset preview cannot be generated."""


def _quote_identifier(identifier: str) -> str:
    """
    Safely quote a SQL identifier.

    Prevents column names containing spaces, special characters,
    or SQL keywords from breaking DuckDB queries.
    """
    return '"' + identifier.replace('"', '""') + '"'


def _get_column_quality(
    connection: duckdb.DuckDBPyConnection,
    columns: list[dict[str, str]],
    total_rows: int,
) -> list[dict[str, Any]]:
    """Return full-dataset valid/error/empty counts for every column.

    Empty values are SQL NULLs. For typed columns, non-empty values that
    cannot be cast to the detected DuckDB type are errors. VARCHAR columns
    have no inferable stricter type contract, so every non-empty value is valid.
    """
    quality: list[dict[str, Any]] = []

    for column in columns:
        name = column["name"]
        dtype = column["dtype"]
        quoted_name = _quote_identifier(name)
        normalized_type = dtype.upper()

        # Text columns have no stricter type contract in the loaded dataset.
        if normalized_type in {"VARCHAR", "TEXT", "STRING", "CHAR", "BPCHAR"}:
            error_expression = "FALSE"
        else:
            # dtype originates from DuckDB DESCRIBE metadata, not user SQL.
            error_expression = (
                f"({quoted_name} IS NOT NULL AND "
                f"TRY_CAST({quoted_name} AS {dtype}) IS NULL)"
            )

        row = connection.execute(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE {quoted_name} IS NOT NULL
                    AND NOT ({error_expression})) AS valid_count,
                COUNT(*) FILTER (WHERE {error_expression}) AS error_count,
                COUNT(*) FILTER (WHERE {quoted_name} IS NULL) AS empty_count
            FROM dataset
            """
        ).fetchone()

        valid_count, error_count, empty_count = (int(value or 0) for value in row)
        denominator = total_rows or 1
        quality.append({
            "valid": {"count": valid_count, "percentage": round(valid_count * 100 / denominator, 2)},
            "error": {"count": error_count, "percentage": round(error_count * 100 / denominator, 2)},
            "empty": {"count": empty_count, "percentage": round(empty_count * 100 / denominator, 2)},
        })

    return quality


def _build_search_condition(
    column_names: list[str],
    search: str,
) -> tuple[str, list[Any]]:
    """
    Build a parameterized case-insensitive search across all columns.
    """

    if not search:
        return "", []

    conditions = [
        f"CAST({_quote_identifier(column)} AS VARCHAR) ILIKE ?"
        for column in column_names
    ]

    search_condition = "WHERE " + " OR ".join(conditions)

    search_pattern = f"%{search}%"

    parameters = [search_pattern] * len(conditions)

    return search_condition, parameters


def get_dataset_preview(
    dataset_id: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str = "",
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    """
    Generate a paginated, searchable and sortable dataset preview.

    Behaviour:
        - Initial preview is limited to the first 1,000 records.
        - Search operates across the entire selected dataset.
        - Sorting operates across the entire selected dataset.
        - Exactly 10 records are returned per page.
        - Original and cleaned versions are resolved independently.
        - Source datasets are never modified.
    """

    # ---------------------------------------------------------
    # 1. Validate request parameters
    # ---------------------------------------------------------

    if page < 1:
        raise ValueError(
            "Page must be greater than or equal to 1."
        )

    if page_size != DEFAULT_PAGE_SIZE:
        raise ValueError(
            "Page size must be exactly 10."
        )

    normalized_sort_order = sort_order.lower()

    if normalized_sort_order not in {"asc", "desc"}:
        raise ValueError(
            "Sort order must be 'asc' or 'desc'."
        )

    normalized_search = (search or "").strip()

    # ---------------------------------------------------------
    # 2. Resolve the exact selected dataset version
    # ---------------------------------------------------------

    try:
        dataset_path = find_dataset_path(dataset_id)

    except Exception:
        logger.exception(
            "Failed to resolve dataset path for dataset_id=%s",
            dataset_id,
        )
        raise

    connection: duckdb.DuckDBPyConnection | None = None

    try:
        # -----------------------------------------------------
        # 3. Initialize read-only DuckDB connection
        # -----------------------------------------------------

        connection = connect_read_only(dataset_path)

        # -----------------------------------------------------
        # 4. Retrieve dataset column metadata
        # -----------------------------------------------------

        column_info = connection.execute(
            "DESCRIBE SELECT * FROM dataset"
        ).fetchall()

        columns = [
            {
                "name": item[0],
                "dtype": item[1],
            }
            for item in column_info
        ]

        column_names = [
            column["name"]
            for column in columns
        ]

        if not column_names:
            raise DatasetPreviewError(
                "The selected dataset contains no columns."
            )

        # -----------------------------------------------------
        # 5. Validate sorting column
        # -----------------------------------------------------

        if sort_by is not None and sort_by not in column_names:
            raise ValueError(
                f"Unknown sorting column: {sort_by}"
            )

        # -----------------------------------------------------
        # 6. Retrieve complete dataset statistics
        # -----------------------------------------------------

        total_rows = connection.execute(
            "SELECT COUNT(*) FROM dataset"
        ).fetchone()[0]

        total_columns = len(columns)
        column_quality = _get_column_quality(
            connection, columns, total_rows
        )
        for column, quality in zip(columns, column_quality):
            column["quality"] = quality

        preview_rows = min(
            total_rows,
            PREVIEW_LIMIT,
        )

        # -----------------------------------------------------
        # 7. Determine preview scope
        # -----------------------------------------------------

        # Without search or sorting:
        # Use only the first 1,000 records.
        #
        # With search or sorting:
        # Operate on the complete dataset.

        use_full_dataset = bool(
            normalized_search or sort_by
        )

        # Generate a collision-free internal row identifier.
        row_alias = "__insightforge_row_number__"

        while row_alias in column_names:
            row_alias += "_"

        source_query = f"""
            SELECT
                *,
                ROW_NUMBER() OVER () AS {_quote_identifier(row_alias)}
            FROM dataset
        """

        source_parameters: list[Any] = []

        if not use_full_dataset:
            source_query += " LIMIT ?"

            source_parameters.append(
                PREVIEW_LIMIT
            )

        # -----------------------------------------------------
        # 8. Build full-column search condition
        # -----------------------------------------------------

        search_condition, search_parameters = (
            _build_search_condition(
                column_names,
                normalized_search,
            )
        )

        # -----------------------------------------------------
        # 9. Build reusable query scope
        # -----------------------------------------------------

        cte = f"""
            WITH source_rows AS (
                {source_query}
            ),
            filtered_rows AS (
                SELECT *
                FROM source_rows
                {search_condition}
            )
        """

        # -----------------------------------------------------
        # 10. Count matching records
        # -----------------------------------------------------

        count_query = (
            cte
            + """
                SELECT COUNT(*)
                FROM filtered_rows
            """
        )

        filtered_rows = connection.execute(
            count_query,
            [
                *source_parameters,
                *search_parameters,
            ],
        ).fetchone()[0]

        total_pages = (
            (filtered_rows + page_size - 1) // page_size
            if filtered_rows > 0
            else 0
        )

        # Prevent requests for pages beyond the available range.
        effective_page = min(
            page,
            max(total_pages, 1),
        )

        offset = (
            effective_page - 1
        ) * page_size

        # -----------------------------------------------------
        # 11. Build sorting condition
        # -----------------------------------------------------

        if sort_by is not None:
            order_clause = (
                f"{_quote_identifier(sort_by)} "
                f"{normalized_sort_order.upper()} NULLS LAST, "
                f"{_quote_identifier(row_alias)} ASC"
            )
        else:
            order_clause = (
                f"{_quote_identifier(row_alias)} ASC"
            )

        # -----------------------------------------------------
        # 12. Retrieve requested page
        # -----------------------------------------------------

        data_query = (
            cte
            + f"""
                SELECT *
                EXCLUDE ({_quote_identifier(row_alias)})
                FROM filtered_rows
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
        )

        dataframe = connection.execute(
            data_query,
            [
                *source_parameters,
                *search_parameters,
                page_size,
                offset,
            ],
        ).fetchdf()

        # -----------------------------------------------------
        # 13. Convert records into JSON-compatible values
        # -----------------------------------------------------

        records = json.loads(
            dataframe.to_json(
                orient="records",
                date_format="iso",
            )
        )

        # -----------------------------------------------------
        # 14. Return preview response
        # -----------------------------------------------------

        return {
            "dataset_id": dataset_id,
            "filename": dataset_path.name,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "preview_limit": PREVIEW_LIMIT,
            "preview_rows": preview_rows,
            "columns": columns,
            "records": records,
            "pagination": {
                "page": effective_page,
                "page_size": page_size,
                "total_filtered_rows": filtered_rows,
                "total_pages": total_pages,
            },
            "search": normalized_search,
            "sorting": {
                "sort_by": sort_by,
                "sort_order": normalized_sort_order,
            },
        }

    # ---------------------------------------------------------
    # 15. Exception handling
    # ---------------------------------------------------------

    except (
        FileNotFoundError,
        ValueError,
        DatasetPreviewError,
    ):
        raise

    except DuckDBEngineError as exc:
        logger.exception(
            "DuckDB initialization failed for dataset_id=%s",
            dataset_id,
        )

        raise DatasetPreviewError(
            "Unable to initialize the dataset preview engine."
        ) from exc

    except Exception as exc:
        logger.exception(
            "Dataset preview execution failed for dataset_id=%s",
            dataset_id,
        )

        raise DatasetPreviewError(
            "Unable to generate the dataset preview."
        ) from exc

    finally:
        if connection is not None:
            connection.close()

MAX_UNIQUE_VALUES = 500


def get_column_unique_values(
    dataset_id: str,
    column_name: str,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Return distinct non-null values for one dataset column.

    Results are bounded to protect the API/UI from very high-cardinality
    columns. The response reports the full distinct count and whether the
    returned list was truncated.
    """
    if limit < 1 or limit > MAX_UNIQUE_VALUES:
        raise ValueError(f"Limit must be between 1 and {MAX_UNIQUE_VALUES}.")

    dataset_path = find_dataset_path(dataset_id)
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = connect_read_only(dataset_path)
        column_names = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM dataset"
            ).fetchall()
        ]
        if column_name not in column_names:
            raise ValueError(f"Unknown column: {column_name}")

        quoted = _quote_identifier(column_name)
        stats = connection.execute(
            f"""
            SELECT
                COUNT(DISTINCT {quoted}),
                COUNT(*) FILTER (WHERE {quoted} IS NULL)
            FROM dataset
            """
        ).fetchone()
        total_unique = int(stats[0] or 0)
        has_null = int(stats[1] or 0) > 0

        rows = connection.execute(
            f"""
            SELECT DISTINCT {quoted} AS value
            FROM dataset
            WHERE {quoted} IS NOT NULL
            ORDER BY value
            LIMIT ?
            """,
            [limit],
        ).fetchdf()

        values = json.loads(
            rows.to_json(orient="values", date_format="iso")
        )
        values = [row[0] for row in values]

        return {
            "dataset_id": dataset_id,
            "column": column_name,
            "values": values,
            "total_unique_values": total_unique,
            "has_null": has_null,
            "truncated": total_unique > len(values),
            "limit": limit,
        }
    except (FileNotFoundError, ValueError):
        raise
    except DuckDBEngineError as exc:
        logger.exception(
            "DuckDB initialization failed for unique values dataset_id=%s",
            dataset_id,
        )
        raise DatasetPreviewError(
            "Unable to initialize the dataset values engine."
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unable to retrieve unique values for dataset_id=%s column=%s",
            dataset_id,
            column_name,
        )
        raise DatasetPreviewError(
            "Unable to retrieve unique column values."
        ) from exc
    finally:
        if connection is not None:
            connection.close()
