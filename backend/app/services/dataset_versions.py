import json
import os
import tempfile
import time

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.services.settings import settings


def get_version_directory() -> Path:
    """
    Store dataset version metadata separately from raw and
    processed dataset files.
    """
    directory = (
        settings.upload_dir.parent
        / "metadata"
        / "dataset_versions"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


def validate_dataset_id(dataset_id: str) -> str:
    try:
        return str(UUID(dataset_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(
            "Invalid dataset identifier."
        ) from exc


def get_version_registry_path(original_dataset_id: str) -> Path:
    validated_id = validate_dataset_id(
        original_dataset_id
    )

    return (
        get_version_directory()
        / f"{validated_id}.json"
    )


@contextmanager
def dataset_versions_lock(original_dataset_id: str):
    """
    Cross-process lock for a dataset's version registry.
    Supports Windows and Unix-based systems.
    """
    validated_id = validate_dataset_id(
        original_dataset_id
    )

    lock_path = (
        get_version_directory()
        / f"{validated_id}.lock"
    )

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
                            "Timed out waiting for dataset version lock."
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


def save_version_registry(registry: dict) -> None:
    """
    Persist registry JSON atomically to avoid partial writes.
    """
    original_dataset_id = validate_dataset_id(
        registry["original_dataset_id"]
    )

    target = get_version_registry_path(
        original_dataset_id
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary_file:

            temporary_path = Path(
                temporary_file.name
            )

            json.dump(
                registry,
                temporary_file,
                indent=2,
            )

            temporary_file.flush()

            os.fsync(
                temporary_file.fileno()
            )

        os.replace(
            temporary_path,
            target,
        )

    except Exception:

        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True
            )

        raise


def load_version_registry(
    original_dataset_id: str,
) -> dict:

    path = get_version_registry_path(
        original_dataset_id
    )

    if not path.is_file():
        raise FileNotFoundError(
            "Dataset version registry not found."
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def register_original_dataset(
    dataset_id: str,
    filename: str,
) -> dict:

    validated_id = validate_dataset_id(
        dataset_id
    )

    with dataset_versions_lock(validated_id):

        registry_path = get_version_registry_path(
            validated_id
        )

        if registry_path.exists():
            raise ValueError(
                "Original dataset is already registered."
            )

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        registry = {
            "original_dataset_id": validated_id,
            "versions": [
                {
                    "dataset_id": validated_id,
                    "version_number": 0,
                    "version_type": "original",
                    "filename": filename,
                    "created_at": created_at,
                    "cleaning_plan_id": None,
                    "parent_dataset_id": None,
                }
            ],
            "updated_at": created_at,
        }

        save_version_registry(registry)

        return registry


def ensure_original_dataset_registered(
    dataset_id: str,
    filename: str,
) -> dict:
    """
    Ensure legacy or directly-created datasets have
    an original V0 registry entry.

    Existing registries are preserved.
    """
    validated_id = validate_dataset_id(
        dataset_id
    )

    with dataset_versions_lock(validated_id):

        registry_path = get_version_registry_path(
            validated_id
        )

        if registry_path.exists():
            return load_version_registry(
                validated_id
            )

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        registry = {
            "original_dataset_id": validated_id,
            "versions": [
                {
                    "dataset_id": validated_id,
                    "version_number": 0,
                    "version_type": "original",
                    "filename": filename,
                    "created_at": created_at,
                    "cleaning_plan_id": None,
                    "parent_dataset_id": None,
                }
            ],
            "updated_at": created_at,
        }

        save_version_registry(registry)

        return registry


def register_cleaned_version(
    original_dataset_id: str,
    cleaned_dataset_id: str,
    cleaning_plan_id: str,
    filename: str,
) -> dict:
    """
    Register a cleaned dataset version under its original
    dataset lineage.

    The supplied original_dataset_id represents the dataset
    currently being cleaned. It may be V0, V1, V2, etc.

    The root original dataset ID is resolved from the registry.
    The supplied dataset ID becomes the immediate parent.
    """

    source_id = validate_dataset_id(
        original_dataset_id
    )

    cleaned_id = validate_dataset_id(
        cleaned_dataset_id
    )

    plan_id = validate_dataset_id(
        cleaning_plan_id
    )

    if source_id == cleaned_id:
        raise ValueError(
            "A cleaned version must have a different dataset identifier."
        )

    # Resolve the complete version lineage using the
    # currently selected source dataset.
    registry = get_dataset_versions(source_id)

    root_id = validate_dataset_id(
        registry["original_dataset_id"]
    )

    # Lock the root registry, not the individual version.
    with dataset_versions_lock(root_id):

        # Reload the registry after acquiring the lock.
        registry = load_version_registry(root_id)

        versions = registry["versions"]

        existing_ids = {
            version["dataset_id"]
            for version in versions
        }

        if source_id not in existing_ids:
            raise ValueError(
                "Source dataset is not registered in this version lineage."
            )

        if cleaned_id in existing_ids:
            raise ValueError(
                "Dataset version is already registered."
            )

        existing_plan_ids = {
            version["cleaning_plan_id"]
            for version in versions
            if version["cleaning_plan_id"] is not None
        }

        if plan_id in existing_plan_ids:
            raise ValueError(
                "Cleaning plan is already registered."
            )

        source_version = next(
            (
                version
                for version in versions
                if version["dataset_id"] == source_id
            ),
            None,
        )

        if source_version is None:
            raise ValueError(
                "Source dataset version not found."
            )

        next_version_number = (
            max(
                version["version_number"]
                for version in versions
            )
            + 1
        )

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        versions.append(
            {
                "dataset_id": cleaned_id,
                "version_number": next_version_number,
                "version_type": "cleaned",
                "filename": filename,
                "created_at": created_at,
                "cleaning_plan_id": plan_id,

                # Preserve the original dataset lineage.
                "parent_dataset_id": source_id,
            }
        )

        registry["updated_at"] = created_at

        save_version_registry(registry)

        return registry

def get_dataset_versions(dataset_id: str) -> dict:
    """
    Resolve the version group using either the original
    dataset ID or one of its cleaned dataset IDs.
    """
    validated_id = validate_dataset_id(
        dataset_id
    )

    directory = get_version_directory()

    for registry_path in directory.glob("*.json"):

        with registry_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            registry = json.load(file)

        registered_ids = {
            version["dataset_id"]
            for version in registry["versions"]
        }

        if validated_id in registered_ids:
            return registry

    raise FileNotFoundError(
        "Dataset version registry not found."
    )


def unregister_cleaned_version(
    original_dataset_id: str,
    cleaned_dataset_id: str,
    cleaning_plan_id: str,
) -> dict:

    original_id = validate_dataset_id(
        original_dataset_id
    )

    cleaned_id = validate_dataset_id(
        cleaned_dataset_id
    )

    plan_id = validate_dataset_id(
        cleaning_plan_id
    )

    with dataset_versions_lock(original_id):

        registry = load_version_registry(
            original_id
        )

        original_versions = registry["versions"]

        updated_versions = [
            version
            for version in original_versions
            if not (
                version["dataset_id"] == cleaned_id
                and version["cleaning_plan_id"] == plan_id
                and version["version_type"] == "cleaned"
            )
        ]

        if len(updated_versions) == len(original_versions):
            return registry

        registry["versions"] = updated_versions

        registry["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        save_version_registry(registry)

        return registry