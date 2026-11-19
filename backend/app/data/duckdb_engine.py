from pathlib import Path

import duckdb
import pandas as pd


class DuckDBEngineError(RuntimeError):
    """Raised when DuckDB cannot initialize a dataset connection."""


def connect_read_only(dataset_path: Path) -> duckdb.DuckDBPyConnection:
    """
    Create an in-memory DuckDB connection for analytical queries.

    Supported formats:
    - CSV
    - XLSX
    - Parquet

    The source dataset is never modified.
    """

    dataset_path = Path(dataset_path)

    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Dataset file not found: {dataset_path}"
        )

    connection = duckdb.connect(database=":memory:")

    try:
        extension = dataset_path.suffix.lower()

        if extension == ".csv":
            escaped_path = str(dataset_path).replace("'", "''")

            connection.execute(
                f"""
                CREATE VIEW dataset AS
                SELECT *
                FROM read_csv_auto(
                    '{escaped_path}',
                    header = true,
                    nullstr = ['', 'NA', 'N/A', 'NULL', 'null']
                )
                """
            )

        elif extension == ".xlsx":
            from app.data.loaders.tabular import load_tabular_file
            dataframe = load_tabular_file(dataset_path)

            connection.register(
                "source_dataframe",
                dataframe,
            )

            connection.execute(
                """
                CREATE VIEW dataset AS
                SELECT *
                FROM source_dataframe
                """
            )

        elif extension == ".parquet":
            relation = connection.read_parquet(
                str(dataset_path)
            )
            relation.create_view("dataset")

        else:
            raise DuckDBEngineError(
                f"Unsupported dataset format: {extension}"
            )

        return connection

    except Exception as exc:
        connection.close()

        if isinstance(exc, (FileNotFoundError, DuckDBEngineError)):
            raise

        raise DuckDBEngineError(
            "Unable to initialize DuckDB dataset connection."
        ) from exc