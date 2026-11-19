import pytest

from sqlalchemy import select

from app.services.cleaning_execution import (
    CleaningExecutionError,
    execute_cleaning_plan,
)

from app.services.cleaning_plans import load_cleaning_plan
from app.services.dataset_versions import get_dataset_versions

from io import BytesIO
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    CleaningExecution,
    CleaningPlan,
    Dataset,
    DatasetVersion,
)
from app.services import settings as settings_module


client = TestClient(app)


def test_postgres_cleaning_complete_lifecycle(
    tmp_path,
    monkeypatch,
    db_session,
):
    # 1. Isolate filesystem storage
    upload_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    upload_dir.mkdir()
    processed_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    monkeypatch.setattr(
        settings_module.settings,
        "processed_dir",
        processed_dir,
    )

    # 2. Upload a real CSV through the API
    content = (
        b"Product,Sales\n"
        b"Laptop,1000\n"
        b"Laptop,1000\n"
        b"Phone,500\n"
    )

    upload_response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "postgres_integration.csv",
                BytesIO(content),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 201, upload_response.text

    dataset_id = upload_response.json()["dataset_id"]
    dataset_uuid = UUID(dataset_id)

    # 3. Verify original dataset persistence
    original_dataset = db_session.get(
        Dataset,
        dataset_uuid,
    )

    assert original_dataset is not None
    assert original_dataset.filename == "postgres_integration.csv"

    original_version = db_session.get(
        DatasetVersion,
        dataset_uuid,
    )

    assert original_version is not None
    assert original_version.version_type == "original"
    assert original_version.version_number == 0

    # 4. Generate cleaning preview
    preview_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "drop_duplicates",
                }
            ]
        },
    )

    assert preview_response.status_code == 200, preview_response.text

    plan_id = preview_response.json()["plan_id"]
    plan_uuid = UUID(plan_id)

    plan = db_session.get(
        CleaningPlan,
        plan_uuid,
    )

    assert plan is not None
    assert plan.status == "pending"

    # 5. Approve cleaning plan
    approval_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/approve",
        json={"approved": True},
    )

    assert approval_response.status_code == 200, approval_response.text
    assert approval_response.json()["status"] == "approved"

    db_session.refresh(plan)
    assert plan.status == "approved"

    # 6. Execute cleaning
    execution_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert execution_response.status_code == 200, execution_response.text

    execution_data = execution_response.json()

    assert execution_data["status"] == "executed"

    cleaned_dataset_id = UUID(
        execution_data["cleaned_dataset_id"]
    )

    # 7. Verify cleaning plan persistence
    db_session.refresh(plan)

    assert plan.status == "executed"
    assert plan.cleaned_dataset_id == cleaned_dataset_id
    assert plan.execution_results is not None
    assert plan.output_metrics is not None

    # 8. Verify cleaned dataset persistence
    cleaned_dataset = db_session.get(
        Dataset,
        cleaned_dataset_id,
    )

    assert cleaned_dataset is not None
    assert cleaned_dataset.storage_location == "processed"

    # 9. Verify cleaned dataset version
    cleaned_version = db_session.get(
        DatasetVersion,
        cleaned_dataset_id,
    )

    assert cleaned_version is not None
    assert cleaned_version.version_type == "cleaned"
    assert cleaned_version.original_dataset_id == dataset_uuid
    assert cleaned_version.version_number == 1
    assert cleaned_version.cleaning_plan_id == plan_uuid

    # 10. Verify execution audit record
    execution = db_session.get(
        CleaningExecution,
        plan_uuid,
    )

    assert execution is not None
    assert execution.dataset_id == dataset_uuid
    assert execution.cleaned_dataset_id == cleaned_dataset_id
    assert execution.execution_results is not None

    # 11. Verify physical cleaned file
    output_file = processed_dir / execution_data["output_filename"]

    assert output_file.is_file()

    print("\nPOSTGRESQL CLEANING INTEGRATION VERIFIED")
    print(f"Original Dataset: {dataset_uuid}")
    print(f"Cleaning Plan: {plan_uuid}")
    print(f"Cleaned Dataset: {cleaned_dataset_id}")
    print(f"Cleaned Version: {cleaned_version.version_number}")
    print("Cleaning Execution: Persisted successfully")

def test_postgres_cleaning_execution_commit_failure_rolls_back(
    tmp_path,
    monkeypatch,
    db_session,
):
    # 1. Isolate filesystem storage.
    upload_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    upload_dir.mkdir()
    processed_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    monkeypatch.setattr(
        settings_module.settings,
        "processed_dir",
        processed_dir,
    )

    # 2. Upload original dataset.
    content = (
        b"Product,Sales\n"
        b"Laptop,1000\n"
        b"Laptop,1000\n"
        b"Phone,500\n"
    )

    upload_response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "rollback_test.csv",
                BytesIO(content),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 201

    dataset_id = upload_response.json()["dataset_id"]
    dataset_uuid = UUID(dataset_id)

    original_path = upload_dir / f"{dataset_id}.csv"
    original_content = original_path.read_bytes()

    # 3. Create cleaning plan.
    preview_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {"type": "drop_duplicates"}
            ]
        },
    )

    assert preview_response.status_code == 200

    plan_id = preview_response.json()["plan_id"]
    plan_uuid = UUID(plan_id)

    # 4. Approve cleaning plan.
    approval_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/approve",
        json={"approved": True},
    )

    assert approval_response.status_code == 200

    # 5. Record initial database state.
    initial_dataset_count = db_session.query(Dataset).count()
    initial_version_count = db_session.query(DatasetVersion).count()
    initial_execution_count = db_session.query(CleaningExecution).count()

    # 6. Simulate PostgreSQL commit failure.
    def simulate_commit_failure():
        raise RuntimeError("Simulated PostgreSQL commit failure")

    monkeypatch.setattr(
        db_session,
        "commit",
        simulate_commit_failure,
    )

    # 7. Execute cleaning and expect failure.
    with pytest.raises(
        CleaningExecutionError,
        match="Unable to complete",
    ):
        execute_cleaning_plan(
            dataset_id=dataset_id,
            plan_id=plan_id,
            db=db_session,
        )

    # 8. Verify database rollback.
    assert db_session.query(Dataset).count() == initial_dataset_count

    assert (
        db_session.query(DatasetVersion).count()
        == initial_version_count
    )

    assert (
        db_session.query(CleaningExecution).count()
        == initial_execution_count
    )

    restored_plan = db_session.get(
        CleaningPlan,
        plan_uuid,
    )

    assert restored_plan.status == "approved"
    assert restored_plan.cleaned_dataset_id is None

    # 9. Verify filesystem rollback.
    assert original_path.read_bytes() == original_content

    assert list(processed_dir.glob("*.csv")) == []

    # 10. Verify version registry rollback.
    registry = get_dataset_versions(dataset_id)

    assert registry["original_dataset_id"] == dataset_id
    assert len(registry["versions"]) == 1

    assert registry["versions"][0]["version_type"] == "original"

    # 11. Verify JSON cleaning plan restoration.
    json_plan = load_cleaning_plan(plan_id)

    assert json_plan["status"] == "approved"
    assert json_plan.get("cleaned_dataset_id") is None
    assert json_plan.get("executed_at") is None

    print("\nPOSTGRESQL ROLLBACK VERIFIED")
    print("Database transaction: Rolled back")
    print("Version registry: Restored")
    print("Cleaned output: Removed")
    print("Original dataset: Preserved")
    print("Cleaning plan: Restored to approved")