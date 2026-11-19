from uuid import uuid4

import pytest

from app.services import analytics_executor
from app.services import dataset_versions


@pytest.fixture
def version_files(tmp_path, monkeypatch):
    upload_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    upload_dir.mkdir()
    processed_dir.mkdir()

    monkeypatch.setattr(
        analytics_executor.settings,
        "upload_dir",
        upload_dir,
    )

    monkeypatch.setattr(
        analytics_executor.settings,
        "processed_dir",
        processed_dir,
    )

    original_id = str(uuid4())
    v1_id = str(uuid4())
    v2_id = str(uuid4())

    dataset_versions.register_original_dataset(
        dataset_id=original_id,
        filename="sales.csv",
    )

    dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=v1_id,
        cleaning_plan_id=str(uuid4()),
        filename="cleaned_v1.csv",
    )

    dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=v2_id,
        cleaning_plan_id=str(uuid4()),
        filename="cleaned_v2.csv",
    )

    original_file = upload_dir / f"{original_id}.csv"
    v1_file = processed_dir / f"{v1_id}.csv"
    v2_file = processed_dir / f"{v2_id}.csv"

    original_file.write_text("Sales\n100\n", encoding="utf-8")
    v1_file.write_text("Sales\n200\n", encoding="utf-8")
    v2_file.write_text("Sales\n300\n", encoding="utf-8")

    return {
        "original_id": original_id,
        "v1_id": v1_id,
        "v2_id": v2_id,
        "original_file": original_file,
        "v1_file": v1_file,
        "v2_file": v2_file,
    }


def test_original_dataset_id_resolves_original_file(version_files):
    result = analytics_executor.find_dataset_path(
        dataset_id=version_files["original_id"],
        version="cleaned",
    )

    assert result == version_files["original_file"]


def test_cleaned_v1_id_resolves_exact_v1_file(version_files):
    result = analytics_executor.find_dataset_path(
        dataset_id=version_files["v1_id"],
        version="original",
    )

    assert result == version_files["v1_file"]


def test_cleaned_v2_id_resolves_exact_v2_file(version_files):
    result = analytics_executor.find_dataset_path(
        dataset_id=version_files["v2_id"],
        version="original",
    )

    assert result == version_files["v2_file"]


def test_missing_selected_version_file_raises_error(
    version_files,
):
    version_files["v2_file"].unlink()

    with pytest.raises(
        analytics_executor.DatasetNotFoundError,
        match="selected dataset version file is missing",
    ):
        analytics_executor.find_dataset_path(
            dataset_id=version_files["v2_id"],
        )


def test_unknown_dataset_id_raises_error(version_files):
    unknown_id = str(uuid4())

    with pytest.raises(
        analytics_executor.DatasetNotFoundError,
    ):
        analytics_executor.find_dataset_path(
            dataset_id=unknown_id,
        )