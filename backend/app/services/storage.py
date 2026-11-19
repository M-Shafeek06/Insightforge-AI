from pathlib import Path

from app.services.settings import settings

settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.processed_dir.mkdir(parents=True, exist_ok=True)


def dataset_path(dataset_id: str, suffix: str) -> Path:
    return settings.upload_dir / f"{dataset_id}{suffix}"


def resolve_dataset_path(dataset_id: str) -> Path:
    """
    Locate a dataset in either raw uploads or processed storage.
    Supports CSV and XLSX files.
    """

    matching_files = []

    for directory in (
        settings.upload_dir,
        settings.processed_dir,
    ):
        for extension in (".csv", ".xlsx"):
            path = directory / f"{dataset_id}{extension}"

            if path.is_file():
                matching_files.append(path)

    if not matching_files:
        raise FileNotFoundError("Dataset not found.")

    if len(matching_files) > 1:
        raise ValueError(
            "Multiple files were found for this dataset identifier."
        )

    return matching_files[0]