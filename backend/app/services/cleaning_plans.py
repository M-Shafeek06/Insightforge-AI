import hashlib
import json
import math
import os
import tempfile
import time

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pandas as pd

from sqlalchemy.orm import Session

from app.models import Dataset, CleaningPlan
from app.services.settings import settings


# --------------------------------------------------
# JSON SERIALIZATION
# --------------------------------------------------

def to_json_compatible(value):
    """
    Recursively convert Pandas, NumPy and Python values
    into JSON-compatible values.

    Handles:
    - Pandas Timestamp and NaT
    - NumPy scalar values
    - NumPy datetime64
    - Pandas NA
    - Python datetime and date
    - Non-finite floating-point values
    - Nested dictionaries and collections
    """

    if value is None or value is pd.NA or value is pd.NaT:
        return None

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()

    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).isoformat()

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        return to_json_compatible(value.item())

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, dict):
        return {
            str(key): to_json_compatible(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            to_json_compatible(item)
            for item in value
        ]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    return value


# --------------------------------------------------
# CLEANING PLAN STORAGE
# --------------------------------------------------

def get_plan_directory() -> Path:
    directory = settings.processed_dir / "cleaning_plans"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_plan_path(plan_id: str) -> Path:
    try:
        validated_id = str(UUID(plan_id))
    except ValueError as exc:
        raise ValueError(
            "Invalid cleaning plan identifier."
        ) from exc

    return get_plan_directory() / f"{validated_id}.json"


# --------------------------------------------------
# CLEANING PLAN LOCK
# --------------------------------------------------

@contextmanager
def cleaning_plan_lock(plan_id: str):
    """
    Acquire a cross-process lock for a cleaning plan.

    Supports Windows and Unix-based operating systems.
    Lock files are intentionally retained after use.
    """

    validated_id = str(UUID(plan_id))
    lock_path = get_plan_directory() / f"{validated_id}.lock"

    with lock_path.open("a+b") as lock_file:

        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)

            if not lock_file.read(1):
                lock_file.write(b"0")
                lock_file.flush()

            lock_file.seek(0)
            deadline = time.monotonic() + 30

            while True:
                try:
                    msvcrt.locking(
                        lock_file.fileno(),
                        msvcrt.LK_NBLCK,
                        1,
                    )
                    break

                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Timed out waiting for cleaning plan lock."
                        )

                    time.sleep(0.05)

            try:
                yield

            finally:
                lock_file.seek(0)

                msvcrt.locking(
                    lock_file.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )

        else:
            import fcntl

            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX,
            )

            try:
                yield

            finally:
                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_UN,
                )


# --------------------------------------------------
# DATASET FINGERPRINT
# --------------------------------------------------

def calculate_file_fingerprint(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


# --------------------------------------------------
# SAVE CLEANING PLAN
# --------------------------------------------------

def save_cleaning_plan(plan: dict) -> None:
    target = get_plan_path(plan["plan_id"])

    temporary_path = None

    # Ensure all nested values are JSON-compatible.
    serializable_plan = to_json_compatible(plan)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary_file:

            temporary_path = Path(temporary_file.name)

            json.dump(
                serializable_plan,
                temporary_file,
                indent=2,
                allow_nan=False,
            )

            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(
            temporary_path,
            target,
        )

    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

        raise


# --------------------------------------------------
# LOAD CLEANING PLAN
# --------------------------------------------------

def load_cleaning_plan(plan_id: str) -> dict:
    path = get_plan_path(plan_id)

    if not path.is_file():
        raise FileNotFoundError("Cleaning plan not found.")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------
# CREATE CLEANING PLAN
# --------------------------------------------------

def create_cleaning_plan(
    dataset_id: str,
    source_path: Path,
    operations: list,
    preview: dict,
    db: Session | None = None,
):
    validated_dataset_id = str(UUID(dataset_id))

    plan = {
        "plan_id": str(uuid4()),
        "dataset_id": validated_dataset_id,
        "source_filename": source_path.name,
        "source_fingerprint": calculate_file_fingerprint(source_path),
        "operations": operations,
        "preview": preview,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "executed_at": None,
        "cleaned_dataset_id": None,
        "output_metrics": None,
    }

    # Normalize the complete plan once.
    # The same normalized values are used for filesystem
    # and PostgreSQL persistence.
    plan = to_json_compatible(plan)

    save_cleaning_plan(plan)

    try:
        if db is not None:

            dataset = db.get(
                Dataset,
                UUID(validated_dataset_id),
            )

            # Preserve filesystem-only workflows for legacy datasets.
            if dataset is not None:

                db.add(
                    CleaningPlan(
                        plan_id=UUID(plan["plan_id"]),
                        dataset_id=UUID(validated_dataset_id),
                        source_filename=plan["source_filename"],
                        source_fingerprint=plan["source_fingerprint"],
                        operations=plan["operations"],
                        preview=plan["preview"],
                        status="pending",
                        created_at=datetime.fromisoformat(
                            plan["created_at"]
                        ),
                    )
                )

                db.commit()

    except Exception:
        if db is not None:
            db.rollback()

        get_plan_path(plan["plan_id"]).unlink(missing_ok=True)
        raise

    return plan


# --------------------------------------------------
# APPROVE CLEANING PLAN
# --------------------------------------------------

def approve_cleaning_plan(
    dataset_id: str,
    plan_id: str,
    current_fingerprint: str,
    db: Session | None = None,
):
    validated_dataset_id = str(UUID(dataset_id))

    with cleaning_plan_lock(plan_id):

        original_plan = load_cleaning_plan(plan_id)
        plan = original_plan.copy()

        if plan["dataset_id"] != validated_dataset_id:
            raise ValueError(
                "Cleaning plan does not belong to this dataset."
            )

        if plan["status"] != "pending":
            raise ValueError(
                f"Cannot approve a plan with status '{plan['status']}'."
            )

        if plan["source_fingerprint"] != current_fingerprint:
            raise ValueError(
                "Original dataset has changed since the preview was generated."
            )

        plan["status"] = "approved"

        plan["approved_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        save_cleaning_plan(plan)

        try:
            if db is not None:

                dataset = db.get(
                    Dataset,
                    UUID(validated_dataset_id),
                )

                if dataset is not None:

                    db_plan = db.get(
                        CleaningPlan,
                        UUID(plan_id),
                    )

                    if db_plan is None:
                        raise ValueError(
                            "Cleaning plan metadata not found in PostgreSQL."
                        )

                    if db_plan.dataset_id != UUID(validated_dataset_id):
                        raise ValueError(
                            "PostgreSQL cleaning plan belongs to another dataset."
                        )

                    if db_plan.status != "pending":
                        raise ValueError(
                            "PostgreSQL cleaning plan status is inconsistent."
                        )

                    db_plan.status = "approved"

                    db_plan.approved_at = datetime.fromisoformat(
                        plan["approved_at"]
                    )

                    db.commit()

        except Exception:
            if db is not None:
                db.rollback()

            save_cleaning_plan(original_plan)
            raise

        return plan