from sqlalchemy import inspect

from app.db import engine
from app.models import AnalyticsExecution


def main() -> None:
    inspector = inspect(engine)

    existing_tables = inspector.get_table_names()

    if "datasets" not in existing_tables:
        raise RuntimeError(
            "The datasets table does not exist. "
            "Initialize the existing metadata database first."
        )

    if "analytics_executions" in existing_tables:
        print(
            "Analytics executions table already exists. "
            "No changes required."
        )
        return

    AnalyticsExecution.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    print("Analytics executions table created successfully.")

    inspector = inspect(engine)

    columns = inspector.get_columns("analytics_executions")

    print("\nCreated columns:")

    for column in columns:
        print(
            f"- {column['name']}: "
            f"{column['type']}"
        )


if __name__ == "__main__":
    main()