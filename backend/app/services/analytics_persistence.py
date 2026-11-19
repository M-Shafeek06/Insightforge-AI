from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models import AnalyticsExecution, Dataset


def save_analytics_execution(
    db: Session,
    dataset_id: str,
    request_config: dict,
    result: dict,
) -> AnalyticsExecution | None:
    """
    Persist analytics results for registered UUID-backed datasets.

    Legacy filesystem-only dataset identifiers are not persisted.
    """

    try:
        parsed_dataset_id = UUID(dataset_id)
    except (ValueError, TypeError):
        return None

    dataset = db.get(Dataset, parsed_dataset_id)

    if dataset is None:
        raise ValueError(
            f"Dataset {dataset_id} is not registered in the database."
        )

    execution = AnalyticsExecution(
        execution_id=uuid4(),
        dataset_id=parsed_dataset_id,
        operation=request_config["operation"],
        request_config=jsonable_encoder(request_config),
        result=jsonable_encoder(result),
    )

    try:
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution

    except Exception:
        db.rollback()
        raise