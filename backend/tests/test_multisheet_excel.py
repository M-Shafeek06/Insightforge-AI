from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.data.loaders.tabular import load_tabular_file
from app.services import settings as settings_module

client = TestClient(app)


def _workbook_bytes():
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"Region": ["North", "South"], "Sales": [100, 200]}).to_excel(writer, sheet_name="Sales Data", index=False)
        pd.DataFrame({"Customer": ["A", "B"], "Orders": [3, 5]}).to_excel(writer, sheet_name="Customers", index=False)
        pd.DataFrame({"Field": ["Region", "Sales"], "Definition": ["Sales territory", "Net sales"]}).to_excel(writer, sheet_name="Data Dictionary", index=False)
    return buffer.getvalue()


def test_workbook_sheet_discovery_returns_all_sheet_names():
    response = client.post("/api/datasets/workbook-sheets", files={"file": ("multi.xlsx", _workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 200
    assert response.json()["sheets"] == ["Sales Data", "Customers", "Data Dictionary"]


def test_multisheet_upload_requires_explicit_selection(tmp_path, monkeypatch, db_session):
    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()
    monkeypatch.setattr(settings_module.settings, "upload_dir", upload_dir)
    response = client.post("/api/datasets/upload", files={"file": ("multi.xlsx", _workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "sheet_selection_required"


def test_selected_worksheet_is_used_by_common_loader(tmp_path, monkeypatch, db_session):
    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()
    monkeypatch.setattr(settings_module.settings, "upload_dir", upload_dir)
    response = client.post("/api/datasets/upload", data={"sheet_name": "Customers"}, files={"file": ("multi.xlsx", _workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 201
    dataset_id = response.json()["dataset_id"]
    dataset_path = upload_dir / f"{dataset_id}.xlsx"
    dataframe = load_tabular_file(dataset_path)
    assert list(dataframe.columns) == ["Customer", "Orders"]
    assert dataframe["Customer"].tolist() == ["A", "B"]
    profile = client.get(f"/api/datasets/{dataset_id}/profile")
    assert profile.status_code == 200
    assert profile.json()["columns"] == 2
    assert profile.json()["worksheet_switchable"] is True


def test_upload_can_treat_first_row_as_data_not_headers(tmp_path, monkeypatch, db_session):
    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()
    monkeypatch.setattr(settings_module.settings, "upload_dir", upload_dir)
    response = client.post(
        "/api/datasets/upload",
        data={"sheet_name": "Sales Data", "first_row_header": "false"},
        files={"file": ("multi.xlsx", _workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201
    dataset_id = response.json()["dataset_id"]
    dataframe = load_tabular_file(upload_dir / f"{dataset_id}.xlsx")
    assert list(dataframe.columns) == ["Column 1", "Column 2"]
    assert dataframe.iloc[0].tolist() == ["Region", "Sales"]


def test_switching_worksheet_creates_a_new_independent_dataset(tmp_path, monkeypatch, db_session):
    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()
    monkeypatch.setattr(settings_module.settings, "upload_dir", upload_dir)

    initial = client.post(
        "/api/datasets/upload",
        data={"sheet_name": "Sales Data", "first_row_header": "true"},
        files={"file": ("multi.xlsx", _workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert initial.status_code == 201
    original_id = initial.json()["dataset_id"]

    options = client.get(f"/api/datasets/{original_id}/worksheet-options")
    assert options.status_code == 200
    assert options.json()["sheets"] == ["Sales Data", "Customers", "Data Dictionary"]
    original_profile = client.get(f"/api/datasets/{original_id}/profile")
    assert original_profile.json()["worksheet_switchable"] is True

    switched = client.post(
        f"/api/datasets/{original_id}/select-worksheet",
        data={"sheet_name": "Customers", "first_row_header": "true"},
    )
    assert switched.status_code == 201
    new_id = switched.json()["dataset_id"]
    assert new_id != original_id

    # The newly selected worksheet must retain access to the shared source workbook.
    switched_options = client.get(f"/api/datasets/{new_id}/worksheet-options")
    assert switched_options.status_code == 200
    assert switched_options.json()["sheets"] == ["Sales Data", "Customers", "Data Dictionary"]

    dataframe = load_tabular_file(upload_dir / f"{new_id}.xlsx")
    assert list(dataframe.columns) == ["Customer", "Orders"]
    assert dataframe["Customer"].tolist() == ["A", "B"]

    # Switching must not mutate the original worksheet selection.
    original_dataframe = load_tabular_file(upload_dir / f"{original_id}.xlsx")
    assert list(original_dataframe.columns) == ["Region", "Sales"]

    # Switching back must resolve the original stable worksheet dataset ID.
    switched_back = client.post(
        f"/api/datasets/{new_id}/select-worksheet",
        data={"sheet_name": "Sales Data", "first_row_header": "true"},
    )
    assert switched_back.status_code == 201
    assert switched_back.json()["dataset_id"] == original_id

    # Re-selecting an already-created worksheet must not create another dataset.
    selected_again = client.post(
        f"/api/datasets/{original_id}/select-worksheet",
        data={"sheet_name": "Customers", "first_row_header": "true"},
    )
    assert selected_again.status_code == 201
    assert selected_again.json()["dataset_id"] == new_id

    dictionary = client.post(
        f"/api/datasets/{new_id}/select-worksheet",
        data={"sheet_name": "Data Dictionary", "first_row_header": "true"},
    )
    assert dictionary.status_code == 201
    dictionary_id = dictionary.json()["dataset_id"]
    assert dictionary_id not in {original_id, new_id}

    # Returning from the third sheet resolves both prior worksheet IDs.
    return_to_customers = client.post(
        f"/api/datasets/{dictionary_id}/select-worksheet",
        data={"sheet_name": "Customers", "first_row_header": "true"},
    )
    assert return_to_customers.json()["dataset_id"] == new_id
    return_to_sales = client.post(
        f"/api/datasets/{new_id}/select-worksheet",
        data={"sheet_name": "Sales Data", "first_row_header": "true"},
    )
    assert return_to_sales.json()["dataset_id"] == original_id

    # Both worksheet datasets retain their own source metadata and data.
    customers = load_tabular_file(upload_dir / f"{new_id}.xlsx")
    sales = load_tabular_file(upload_dir / f"{original_id}.xlsx")
    assert customers["Customer"].tolist() == ["A", "B"]
    assert sales["Region"].tolist() == ["North", "South"]
    dictionary_frame = load_tabular_file(upload_dir / f"{dictionary_id}.xlsx")
    assert dictionary_frame["Field"].tolist() == ["Region", "Sales"]



def _single_sheet_workbook_bytes():
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"Region": ["North", "South"], "Sales": [100, 200]}).to_excel(
            writer,
            sheet_name="Sheet1",
            index=False,
        )
    return buffer.getvalue()


def test_single_sheet_xlsx_can_open_switcher_and_reselect_its_only_sheet(
    tmp_path,
    monkeypatch,
    db_session,
):
    upload_dir = tmp_path / "raw"
    upload_dir.mkdir()
    monkeypatch.setattr(settings_module.settings, "upload_dir", upload_dir)

    uploaded = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "single.xlsx",
                _single_sheet_workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["dataset_id"]

    profile = client.get(f"/api/datasets/{dataset_id}/profile")
    assert profile.status_code == 200
    assert profile.json()["worksheet_switchable"] is True

    options = client.get(f"/api/datasets/{dataset_id}/worksheet-options")
    assert options.status_code == 200, options.text
    assert options.json()["sheets"] == ["Sheet1"]

    selected = client.post(
        f"/api/datasets/{dataset_id}/select-worksheet",
        data={"sheet_name": "Sheet1", "first_row_header": "true"},
    )
    assert selected.status_code == 201, selected.text
    assert selected.json()["dataset_id"] == dataset_id
