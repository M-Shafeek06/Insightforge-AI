from fastapi.testclient import TestClient

from app.main import app
from app.services import settings as settings_module


client = TestClient(app)


def configure_test_storage(tmp_path, monkeypatch):
    """Configure isolated storage directories for each test."""

    upload_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    upload_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

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


def upload_csv(filename, content):
    """Upload a CSV file and return its dataset ID."""

    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                filename,
                content,
                "text/csv",
            )
        },
    )

    assert response.status_code == 201, (
        f"CSV upload failed: {response.status_code} - {response.text}"
    )

    dataset_id = response.json().get("dataset_id")

    assert dataset_id, "Dataset ID was not returned after upload."

    return dataset_id


def test_csv_profile_marks_worksheet_switching_unavailable(
    tmp_path,
    monkeypatch,
    db_session,
):
    """CSV datasets must not support Excel worksheet switching."""

    configure_test_storage(tmp_path, monkeypatch)

    csv_content = (
        b"Region,Sales\n"
        b"North,10\n"
        b"South,20\n"
    )

    dataset_id = upload_csv(
        "sample.csv",
        csv_content,
    )

    response = client.get(
        f"/api/datasets/{dataset_id}/profile"
    )

    assert response.status_code == 200, response.text

    profile = response.json()

    assert profile["worksheet_switchable"] is False


def test_unique_values_endpoint_returns_distinct_values_and_null_flag(
    tmp_path,
    monkeypatch,
    db_session,
):
    """Unique-values endpoint must return distinct values and NULL status."""

    configure_test_storage(tmp_path, monkeypatch)

    csv_content = (
        b"Region,Sales\n"
        b"North,10\n"
        b"South,20\n"
        b"North,30\n"
        b",40\n"
    )

    dataset_id = upload_csv(
        "regions.csv",
        csv_content,
    )

    response = client.get(
        f"/api/datasets/{dataset_id}/columns/Region/unique-values"
    )

    assert response.status_code == 200, response.text

    payload = response.json()

    assert payload["values"] == ["North", "South"], (
        f"Unexpected unique values: {payload['values']}"
    )

    assert payload["total_unique_values"] == 2

    assert payload["has_null"] is True

    assert payload["truncated"] is False


def test_unique_values_endpoint_rejects_unknown_column(
    tmp_path,
    monkeypatch,
    db_session,
):
    """Unknown columns must return HTTP 400."""

    configure_test_storage(tmp_path, monkeypatch)

    csv_content = (
        b"Region,Sales\n"
        b"North,10\n"
    )

    dataset_id = upload_csv(
        "sample.csv",
        csv_content,
    )

    response = client.get(
        f"/api/datasets/{dataset_id}/columns/Unknown/unique-values"
    )

    assert response.status_code == 400, (
        f"Expected HTTP 400, received {response.status_code}: {response.text}"
    )