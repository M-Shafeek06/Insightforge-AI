import pandas as pd
from io import BytesIO
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.models import Dataset, DatasetVersion

client = TestClient(app)


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_csv_upload_and_profile(tmp_path, monkeypatch, db_session):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    content = (
        b"Region,Sales,Orders\n"
        b"South,1200,10\n"
        b"North,800,8\n"
        b"South,,12\n"
    )

    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "sales.csv",
                BytesIO(content),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201

    dataset_id = response.json()["dataset_id"]

    # Verify PostgreSQL dataset record
    dataset = db_session.get(Dataset, UUID(dataset_id))

    assert dataset is not None
    assert dataset.filename == "sales.csv"
    assert dataset.storage_location == "raw"

    # Verify original dataset version
    version = db_session.get(DatasetVersion, UUID(dataset_id))

    assert version is not None
    assert version.version_number == 0
    assert version.version_type == "original"

    # Verify existing profiling functionality
    profile = client.get(
        f"/api/datasets/{dataset_id}/profile"
    )

    assert profile.status_code == 200

    data = profile.json()

    assert data["rows"] == 3
    assert data["columns"] == 3
    assert data["missing_values"] == 1
    assert data["duplicate_rows"] == 0

    assert {
        column["name"]
        for column in data["columns_profile"]
    } == {"Region", "Sales", "Orders"}


def test_analysis_plan_success(tmp_path, monkeypatch):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "test-sales-dataset"

    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "OrderDate,Region,Sales,Profit,Orders\n"
        "2026-01-01,South,1200,300,10\n"
        "2026-02-01,North,800,150,8\n"
        "2026-03-01,South,,200,12\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": (
                "Analyze monthly sales and profit performance"
            ),
            "business_questions": [
                "Which regions generate the most sales?",
                "How do sales change over time?",
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["dataset_id"] == dataset_id
    assert (
        data["business_objective"]
        == "Analyze monthly sales and profit performance"
    )

    assert data["feasibility_status"] in {
        "feasible",
        "partially_feasible",
        "not_feasible",
    }

    assert isinstance(data["feasibility_reason"], str)
    assert isinstance(data["recommended_kpis"], list)
    assert isinstance(data["recommended_analyses"], list)
    assert isinstance(data["available_columns"], list)
    assert isinstance(data["missing_required_columns"], list)
    assert isinstance(data["quality_warnings"], list)

    assert set(data["available_columns"]) == {
        "OrderDate",
        "Region",
        "Sales",
        "Profit",
        "Orders",
    }


def test_analysis_plan_missing_dataset_returns_404(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        "/api/datasets/nonexistent-dataset/analysis-plan",
        json={
            "business_objective": "Analyze sales performance",
            "business_questions": [],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_analysis_plan_invalid_request_returns_422(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        "/api/datasets/test-dataset/analysis-plan",
        json={
            "business_objective": "Bad",
            "business_questions": [],
        },
    )

    assert response.status_code == 422


def test_analysis_plan_includes_quality_warnings(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "quality-warning-dataset"

    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "OrderDate,Region,Sales,Profit\n"
        "2026-01-01,South,1200,300\n"
        "2026-02-01,North,,150\n"
        "2026-03-01,South,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": (
                "Analyze sales and profit performance"
            ),
            "business_questions": [],
        },
    )

    assert response.status_code == 200

    data = response.json()
    warnings = data["quality_warnings"]

    assert isinstance(warnings, list)
    assert warnings

    assert all(
        {
            "issue_type",
            "severity",
            "column",
            "message",
            "recommendation",
        }.issubset(warning.keys())
        for warning in warnings
    )

    assert any(
        warning["column"] == "Sales"
        and "missing" in (
            warning["issue_type"] + " " + warning["message"]
        ).lower()
        for warning in warnings
    )

    assert any(
        warning["column"] == "OrderDate"
        and "date" in (
            warning["issue_type"] + " " + warning["message"]
        ).lower()
        for warning in warnings
    )



def test_product_objective_reports_missing_product_column(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "category-sales-dataset"

    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Category,Sales,Profit\n"
        "South,Electronics,1200,300\n"
        "North,Furniture,800,150\n"
        "West,Electronics,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": (
                "Identify the top-performing products"
            ),
            "business_questions": [
                "Which products generate the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["feasibility_status"] == "partially_feasible"
    assert any(
        "product" in column.lower()
        for column in data["missing_required_columns"]
    )
    assert "product" in data["feasibility_reason"].lower()


def test_business_question_prioritizes_relevant_dimension(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "category-priority-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Category,Sales,Profit\n"
        "South,Electronics,1200,300\n"
        "North,Furniture,800,150\n"
        "West,Electronics,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze business performance",
            "business_questions": [
                "Which category generates the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()
    analyses = data["recommended_analyses"]

    assert analyses, "The planner should recommend at least one analysis."

    assert analyses[0]["name"] == "Segment Comparison"

    assert analyses[0]["required_columns"] == [
        "Category",
        "Sales",
    ]

def test_profit_question_selects_profit_measure(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "regional-profit-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Sales,Profit\n"
        "South,1200,300\n"
        "North,800,150\n"
        "West,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze business performance",
            "business_questions": [
                "Which region generates the most profit?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()
    analyses = data["recommended_analyses"]

    assert analyses, "The planner should recommend at least one analysis."

    assert analyses[0]["name"] == "Segment Comparison"

    assert analyses[0]["required_columns"] == [
        "Region",
        "Profit",
    ]

def test_monthly_sales_question_prioritizes_trend_analysis(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "monthly-sales-trend-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "OrderDate,Region,Sales,Profit\n"
        "2026-01-01,South,1200,300\n"
        "2026-02-01,North,800,150\n"
        "2026-03-01,West,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze monthly sales performance",
            "business_questions": [
                "How do sales change over time?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()
    analyses = data["recommended_analyses"]

    assert analyses, "The planner should recommend at least one analysis."

    assert analyses[0]["name"] == "Trend Analysis"

    assert analyses[0]["required_columns"] == [
        "OrderDate",
        "Sales",
    ]

def test_product_objective_is_feasible_when_product_column_exists(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "product-sales-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Product,Region,Sales,Profit\n"
        "Laptop,South,1200,300\n"
        "Phone,North,800,150\n"
        "Tablet,West,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": (
                "Identify the top-performing products"
            ),
            "business_questions": [
                "Which products generate the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["feasibility_status"] == "feasible"
    assert data["missing_required_columns"] == []
    assert "Product" in data["available_columns"]

def test_question_column_prefers_longer_explicit_column_name():
    from app.services.analysis_planner import _question_column

    columns = [
        "Sales",
        "Salesperson",
        "SalesRegion",
    ]

    selected = _question_column(
        columns=columns,
        questions=[
            "Which salesperson generated the most revenue?"
        ],
        candidates=[
            "Sales",
            "Salesperson",
            "SalesRegion",
        ],
    )

    assert selected == "Salesperson"


def test_analysis_plan_without_numeric_measures_is_not_feasible(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "categorical-only-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Category\n"
        "South,Electronics\n"
        "North,Furniture\n"
        "West,Electronics\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze business performance",
            "business_questions": [
                "Which category generates the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["feasibility_status"] == "not_feasible"
    assert data["recommended_kpis"] == []
    assert data["recommended_analyses"] == []


def test_customer_objective_reports_missing_customer_column(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "customer-analysis-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Sales,Profit\n"
        "South,1200,300\n"
        "North,800,150\n"
        "West,900,200\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": (
                "Analyze customer purchasing performance"
            ),
            "business_questions": [
                "Which customers generate the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["feasibility_status"] == "partially_feasible"

    assert any(
        "customer" in column.lower()
        for column in data["missing_required_columns"]
    )

    assert "customer" in data["feasibility_reason"].lower()


def test_question_column_selects_sales_region_over_sales():
    from app.services.analysis_planner import _question_column

    columns = [
        "Sales",
        "Salesperson",
        "SalesRegion",
    ]

    selected = _question_column(
        columns=columns,
        questions=[
            "Which sales region performs best?"
        ],
        candidates=[
            "Sales",
            "Salesperson",
            "SalesRegion",
        ],
    )

    assert selected == "SalesRegion"


def test_analysis_plan_ignores_all_null_numeric_measures(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "all-null-measures-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Sales,Profit\n"
        "South,,\n"
        "North,,\n"
        "West,,\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze business performance",
            "business_questions": [
                "Which region generates the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["recommended_kpis"] == []
    assert data["recommended_analyses"] == []
    assert data["feasibility_status"] == "not_feasible"

def test_analysis_plan_accepts_partially_populated_numeric_measures(
    tmp_path,
    monkeypatch,
):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "partially-populated-measures-dataset"
    dataset_path = upload_dir / f"{dataset_id}.csv"

    dataset_path.write_text(
        "Region,Sales\n"
        "South,1200\n"
        "North,\n"
        "West,900\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/analysis-plan",
        json={
            "business_objective": "Analyze sales performance",
            "business_questions": [
                "Which region generates the most sales?"
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["feasibility_status"] == "feasible"

    assert any(
        "Sales" in kpi["required_columns"]
        for kpi in data["recommended_kpis"]
    )

    assert any(
        "Sales" in analysis["required_columns"]
        for analysis in data["recommended_analyses"]
    )

def test_cleaning_preview_success(tmp_path, monkeypatch):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "550e8400-e29b-41d4-a716-446655440000"

    dataset_file = upload_dir / f"{dataset_id}.csv"
    dataset_file.write_text(
        "Region,Sales\n"
        " South ,100\n"
        "North,\n"
        "South,300\n",
        encoding="utf-8",
    )

    original_content = dataset_file.read_text(encoding="utf-8")

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "trim_whitespace",
                    "column": "Region",
                },
                {
                    "type": "fill_missing",
                    "column": "Sales",
                    "strategy": "mean",
                },
            ]
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["dataset_id"] == dataset_id
    assert data["status"] == "preview_generated"
    assert data["before"]["missing_values"] == 1
    assert data["after"]["missing_values"] == 0

    assert dataset_file.read_text(encoding="utf-8") == original_content


def test_cleaning_preview_invalid_dataset_id():
    response = client.post(
        "/api/datasets/invalid-id/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "drop_duplicates",
                }
            ]
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid dataset identifier."


def test_cleaning_preview_missing_dataset(tmp_path, monkeypatch):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    dataset_id = "550e8400-e29b-41d4-a716-446655440000"

    response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "drop_duplicates",
                }
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_cleaning_preview_rejects_invalid_operation(tmp_path, monkeypatch):
    from app.services import settings as settings_module

    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()

    dataset_id = "550e8400-e29b-41d4-a716-446655440000"

    (upload_dir / f"{dataset_id}.csv").write_text(
        "Region,Sales\nSouth,100\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        settings_module.settings,
        "upload_dir",
        upload_dir,
    )

    response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "invalid_operation",
                    "column": "Sales",
                }
            ]
        },
    )

    assert response.status_code == 422

# --------------------------------------------------
# CLEANING API INTEGRATION TESTS
# --------------------------------------------------

def setup_cleaning_api_environment(tmp_path, monkeypatch):
    from uuid import uuid4

    from app.services import settings as settings_module

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

    dataset_file = upload_dir / f"{dataset_id}.csv"

    dataset_file.write_text(
        "Product,Sales\n"
        "Laptop,1000\n"
        "Laptop,1000\n"
        "Phone,500\n",
        encoding="utf-8",
    )

    return {
        "dataset_id": dataset_id,
        "dataset_file": dataset_file,
        "processed_dir": processed_dir,
    }


def generate_api_cleaning_preview(dataset_id):

    return client.post(
        f"/api/datasets/{dataset_id}/cleaning-preview",
        json={
            "operations": [
                {
                    "type": "drop_duplicates",
                }
            ]
        },
    )


def test_cleaning_api_complete_lifecycle(tmp_path, monkeypatch):

    import json

    environment = setup_cleaning_api_environment(
        tmp_path,
        monkeypatch,
    )

    dataset_id = environment["dataset_id"]

    # 1. Read and preserve the original dataset
    original_df = pd.read_csv(
        environment["dataset_file"]
    )

    original_snapshot = original_df.copy(deep=True)

    # 2. Generate cleaning preview
    preview_response = generate_api_cleaning_preview(
        dataset_id
    )

    assert preview_response.status_code == 200

    preview_data = preview_response.json()

    plan_id = preview_data["plan_id"]

    assert preview_data["approval_status"] == "pending"

    # 3. Approve cleaning plan
    approval_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/approve",
        json={"approved": True},
    )

    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "approved"

    # 4. Execute approved cleaning plan
    execution_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert execution_response.status_code == 200

    execution_data = execution_response.json()

    assert execution_data["status"] == "executed"

    # 5. Validate cleaned dataset
    cleaned_file = (
        environment["processed_dir"]
        / execution_data["output_filename"]
    )

    assert cleaned_file.is_file()

    cleaned_df = pd.read_csv(cleaned_file)

    expected_df = original_snapshot.drop_duplicates()

    pd.testing.assert_frame_equal(
        cleaned_df.reset_index(drop=True),
        expected_df.reset_index(drop=True),
    )

    assert execution_data["original_rows"] == len(original_snapshot)
    assert execution_data["cleaned_rows"] == len(expected_df)

    # 6. Verify original dataset remains unchanged
    current_original_df = pd.read_csv(
        environment["dataset_file"]
    )

    pd.testing.assert_frame_equal(
        current_original_df,
        original_snapshot,
    )

    # 7. Verify execution audit manifest
    plan_file = (
        environment["processed_dir"]
        / "cleaning_plans"
        / f"{plan_id}.json"
    )

    assert plan_file.is_file()

    saved_plan = json.loads(
        plan_file.read_text(encoding="utf-8")
    )

    assert saved_plan["status"] == "executed"

    assert saved_plan["cleaned_dataset_id"] == (
        execution_data["cleaned_dataset_id"]
    )

    assert saved_plan["execution_results"]
    assert saved_plan["output_metrics"]

def test_cleaning_api_rejects_unapproved_execution(
    tmp_path,
    monkeypatch,
):

    environment = setup_cleaning_api_environment(
        tmp_path,
        monkeypatch,
    )

    dataset_id = environment["dataset_id"]

    preview_response = generate_api_cleaning_preview(
        dataset_id
    )

    plan_id = preview_response.json()["plan_id"]

    response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert response.status_code == 409


def test_cleaning_api_rejects_repeated_execution(
    tmp_path,
    monkeypatch,
):

    environment = setup_cleaning_api_environment(
        tmp_path,
        monkeypatch,
    )

    dataset_id = environment["dataset_id"]

    preview_response = generate_api_cleaning_preview(
        dataset_id
    )

    plan_id = preview_response.json()["plan_id"]

    approval_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/approve",
        json={
            "approved": True,
        },
    )

    assert approval_response.status_code == 200

    first_execution = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert first_execution.status_code == 200

    second_execution = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert second_execution.status_code == 409


def test_cleaning_api_rejects_modified_original_dataset(
    tmp_path,
    monkeypatch,
):

    environment = setup_cleaning_api_environment(
        tmp_path,
        monkeypatch,
    )

    dataset_id = environment["dataset_id"]

    preview_response = generate_api_cleaning_preview(
        dataset_id
    )

    plan_id = preview_response.json()["plan_id"]

    approval_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/approve",
        json={
            "approved": True,
        },
    )

    assert approval_response.status_code == 200

    # Modify original dataset after approval
    environment["dataset_file"].write_text(
        "Product,Sales\nTablet,800\n",
        encoding="utf-8",
    )

    execution_response = client.post(
        f"/api/datasets/{dataset_id}/cleaning-plans/{plan_id}/execute"
    )

    assert execution_response.status_code == 409