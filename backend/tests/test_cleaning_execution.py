import json
from uuid import uuid4

import pandas as pd
import pytest

from app.services import settings as settings_module

from app.services.cleaning_plans import (
    approve_cleaning_plan,
    create_cleaning_plan,
)

from app.services.cleaning_execution import (
    CleaningExecutionError,
    execute_cleaning_plan,
)

from app.services import cleaning_execution as cleaning_execution_module
from app.services.cleaning_plans import load_cleaning_plan
from app.services.dataset_versions import get_dataset_versions


@pytest.fixture
def cleaning_environment(tmp_path, monkeypatch):

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

    dataset_id = str(uuid4())

    source_path = upload_dir / f"{dataset_id}.csv"

    original_df = pd.DataFrame({
        "Product": ["Laptop", "Laptop", "Phone"],
        "Sales": [1000, 1000, 500],
    })

    original_df.to_csv(
        source_path,
        index=False,
    )

    operations = [
        {
            "type": "drop_duplicates",
        }
    ]

    plan = create_cleaning_plan(
        dataset_id=dataset_id,
        source_path=source_path,
        operations=operations,
        preview={},
    )

    return {
        "dataset_id": dataset_id,
        "plan_id": plan["plan_id"],
        "source_path": source_path,
        "processed_dir": processed_dir,
        "original_df": original_df,
    }


def approve_test_plan(environment):

    from app.services.cleaning_plans import (
        calculate_file_fingerprint,
    )

    fingerprint = calculate_file_fingerprint(
        environment["source_path"]
    )

    return approve_cleaning_plan(
        dataset_id=environment["dataset_id"],
        plan_id=environment["plan_id"],
        current_fingerprint=fingerprint,
    )


def test_unapproved_plan_cannot_execute(cleaning_environment):

    environment = cleaning_environment

    with pytest.raises(
        CleaningExecutionError,
        match="Only approved",
    ):
        execute_cleaning_plan(
            dataset_id=environment["dataset_id"],
            plan_id=environment["plan_id"],
        )


def test_approved_plan_executes_successfully(cleaning_environment):

    environment = cleaning_environment

    approve_test_plan(environment)

    result = execute_cleaning_plan(
        dataset_id=environment["dataset_id"],
        plan_id=environment["plan_id"],
    )

    assert result["status"] == "executed"
    assert result["original_rows"] == 3
    assert result["cleaned_rows"] == 2

    cleaned_path = (
        environment["processed_dir"]
        / result["output_filename"]
    )

    assert cleaned_path.is_file()

    cleaned_df = pd.read_csv(cleaned_path)

    assert len(cleaned_df) == 2


def test_original_dataset_is_never_modified(cleaning_environment):

    environment = cleaning_environment

    original_content = (
        environment["source_path"].read_bytes()
    )

    approve_test_plan(environment)

    execute_cleaning_plan(
        dataset_id=environment["dataset_id"],
        plan_id=environment["plan_id"],
    )

    assert (
        environment["source_path"].read_bytes()
        == original_content
    )


def test_executed_plan_cannot_execute_again(cleaning_environment):

    environment = cleaning_environment

    approve_test_plan(environment)

    execute_cleaning_plan(
        dataset_id=environment["dataset_id"],
        plan_id=environment["plan_id"],
    )

    with pytest.raises(
        CleaningExecutionError,
        match="Only approved",
    ):
        execute_cleaning_plan(
            dataset_id=environment["dataset_id"],
            plan_id=environment["plan_id"],
        )


def test_modified_original_dataset_is_rejected(cleaning_environment):

    environment = cleaning_environment

    approve_test_plan(environment)

    modified_df = pd.DataFrame({
        "Product": ["Tablet"],
        "Sales": [800],
    })

    modified_df.to_csv(
        environment["source_path"],
        index=False,
    )

    with pytest.raises(
        CleaningExecutionError,
        match="changed since",
    ):
        execute_cleaning_plan(
            dataset_id=environment["dataset_id"],
            plan_id=environment["plan_id"],
        )


def test_execution_results_are_saved_in_plan(cleaning_environment):

    environment = cleaning_environment

    approve_test_plan(environment)

    result = execute_cleaning_plan(
        dataset_id=environment["dataset_id"],
        plan_id=environment["plan_id"],
    )

    plan_path = (
        environment["processed_dir"]
        / "cleaning_plans"
        / f"{environment['plan_id']}.json"
    )

    assert plan_path.is_file()

    with plan_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        saved_plan = json.load(file)

    assert saved_plan["status"] == "executed"

    assert (
        saved_plan["cleaned_dataset_id"]
        == result["cleaned_dataset_id"]
    )

    assert saved_plan["executed_at"] is not None
    assert saved_plan["execution_results"]

def test_execution_failure_rolls_back_version_and_output(
    cleaning_environment,
    monkeypatch,
):
    environment = cleaning_environment

    approve_test_plan(environment)

    original_content = environment["source_path"].read_bytes()

    real_save_cleaning_plan = (
        cleaning_execution_module.save_cleaning_plan
    )

    def simulate_save_failure(plan):
        if plan.get("status") == "executed":
            raise RuntimeError("Simulated plan persistence failure")

        return real_save_cleaning_plan(plan)

    monkeypatch.setattr(
        cleaning_execution_module,
        "save_cleaning_plan",
        simulate_save_failure,
    )

    with pytest.raises(
        CleaningExecutionError,
        match="Unable to complete",
    ):
        execute_cleaning_plan(
            dataset_id=environment["dataset_id"],
            plan_id=environment["plan_id"],
        )

    # 1. Original dataset must remain unchanged.
    assert (
        environment["source_path"].read_bytes()
        == original_content
    )

    # 2. No cleaned CSV output should remain.
    assert list(
        environment["processed_dir"].glob("*.csv")
    ) == []

    # 3. Version registry must contain only V0.
    registry = get_dataset_versions(
        environment["dataset_id"]
    )

    assert len(registry["versions"]) == 1
    assert (
        registry["versions"][0]["dataset_id"]
        == environment["dataset_id"]
    )

    # 4. Cleaning plan must be restored to approved.
    restored_plan = load_cleaning_plan(
        environment["plan_id"]
    )

    assert restored_plan["status"] == "approved"
    assert restored_plan.get("cleaned_dataset_id") is None
    assert restored_plan.get("executed_at") is None