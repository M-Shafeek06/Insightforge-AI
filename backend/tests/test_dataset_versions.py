from uuid import uuid4

import pytest

from app.services import dataset_versions


@pytest.fixture
def version_storage(tmp_path, monkeypatch):
    upload_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    upload_dir.mkdir()
    processed_dir.mkdir()

    monkeypatch.setattr(
        dataset_versions.settings,
        "upload_dir",
        upload_dir,
    )

    monkeypatch.setattr(
        dataset_versions.settings,
        "processed_dir",
        processed_dir,
    )

    return tmp_path


def test_register_original_dataset(version_storage):
    dataset_id = str(uuid4())

    registry = dataset_versions.register_original_dataset(
        dataset_id=dataset_id,
        filename="sales.csv",
    )

    assert registry["original_dataset_id"] == dataset_id
    assert len(registry["versions"]) == 1

    original = registry["versions"][0]

    assert original["dataset_id"] == dataset_id
    assert original["version_number"] == 0
    assert original["version_type"] == "original"
    assert original["filename"] == "sales.csv"


def test_register_multiple_cleaned_versions(version_storage):
    original_id = str(uuid4())

    dataset_versions.register_original_dataset(
        dataset_id=original_id,
        filename="sales.csv",
    )

    first_cleaned_id = str(uuid4())
    second_cleaned_id = str(uuid4())

    first_registry = dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=first_cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename=f"{first_cleaned_id}.csv",
    )

    second_registry = dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=second_cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename=f"{second_cleaned_id}.csv",
    )

    versions = second_registry["versions"]

    assert len(versions) == 3

    assert [
        version["version_number"]
        for version in versions
    ] == [0, 1, 2]

    assert versions[1]["dataset_id"] == first_cleaned_id
    assert versions[2]["dataset_id"] == second_cleaned_id

    assert first_registry["versions"][0]["version_type"] == "original"

def test_sequential_cleaning_preserves_version_lineage(version_storage):
    original_id = str(uuid4())
    first_cleaned_id = str(uuid4())
    second_cleaned_id = str(uuid4())

    # Register V0: Original dataset.
    dataset_versions.register_original_dataset(
        dataset_id=original_id,
        filename="sales.csv",
    )

    # Register V1: First cleaning derived from V0.
    dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=first_cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename="sales_v1.csv",
    )

    # Register V2: Second cleaning derived from V1.
    dataset_versions.register_cleaned_version(
        original_dataset_id=first_cleaned_id,
        cleaned_dataset_id=second_cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename="sales_v2.csv",
    )

    # Retrieve registry using V2.
    registry = dataset_versions.get_dataset_versions(
        second_cleaned_id
    )

    versions = registry["versions"]

    # Verify root original dataset.
    assert registry["original_dataset_id"] == original_id

    # Verify version sequence.
    assert len(versions) == 3

    assert [
        version["version_number"]
        for version in versions
    ] == [0, 1, 2]

    # Verify V0.
    assert versions[0]["dataset_id"] == original_id
    assert versions[0]["version_type"] == "original"

    # Verify V1.
    assert versions[1]["dataset_id"] == first_cleaned_id
    assert versions[1]["parent_dataset_id"] == original_id

    # Verify V2.
    assert versions[2]["dataset_id"] == second_cleaned_id
    assert versions[2]["parent_dataset_id"] == first_cleaned_id
    assert versions[2]["version_type"] == "cleaned"

def test_resolve_registry_using_cleaned_dataset_id(version_storage):
    original_id = str(uuid4())
    cleaned_id = str(uuid4())

    dataset_versions.register_original_dataset(
        dataset_id=original_id,
        filename="sales.csv",
    )

    dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename="cleaned_sales.csv",
    )

    registry = dataset_versions.get_dataset_versions(
        cleaned_id
    )

    assert registry["original_dataset_id"] == original_id
    assert len(registry["versions"]) == 2


def test_duplicate_original_registration_is_rejected(version_storage):
    dataset_id = str(uuid4())

    dataset_versions.register_original_dataset(
        dataset_id=dataset_id,
        filename="sales.csv",
    )

    with pytest.raises(ValueError):
        dataset_versions.register_original_dataset(
            dataset_id=dataset_id,
            filename="sales.csv",
        )


def test_duplicate_cleaned_dataset_is_rejected(version_storage):
    original_id = str(uuid4())
    cleaned_id = str(uuid4())

    dataset_versions.register_original_dataset(
        dataset_id=original_id,
        filename="sales.csv",
    )

    dataset_versions.register_cleaned_version(
        original_dataset_id=original_id,
        cleaned_dataset_id=cleaned_id,
        cleaning_plan_id=str(uuid4()),
        filename="cleaned_sales.csv",
    )

    with pytest.raises(ValueError):
        dataset_versions.register_cleaned_version(
            original_dataset_id=original_id,
            cleaned_dataset_id=cleaned_id,
            cleaning_plan_id=str(uuid4()),
            filename="duplicate.csv",
        )


def test_invalid_dataset_id_is_rejected(version_storage):
    with pytest.raises(ValueError):
        dataset_versions.register_original_dataset(
            dataset_id="invalid-id",
            filename="sales.csv",
        )


def test_missing_registry_is_rejected(version_storage):
    with pytest.raises(FileNotFoundError):
        dataset_versions.get_dataset_versions(
            str(uuid4())
        )