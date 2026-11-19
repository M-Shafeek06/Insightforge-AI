from sqlalchemy import inspect

from app.db import engine
from app.models import SavedAnalytics


def main() -> None:
    inspector = inspect(engine)

    existing_tables = inspector.get_table_names()

    if "analytics_executions" not in existing_tables:
        raise RuntimeError(
            "The analytics_executions table does not exist. "
            "Initialize analytics persistence first."
        )

    if "saved_analytics" in existing_tables:
        print(
            "Saved analytics table already exists. "
            "No changes required."
        )
        return

    SavedAnalytics.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    print("Saved analytics table created successfully.")

    inspector = inspect(engine)

    print("\nCreated columns:")

    for column in inspector.get_columns("saved_analytics"):
        print(f"- {column['name']}: {column['type']}")


if __name__ == "__main__":
    main()