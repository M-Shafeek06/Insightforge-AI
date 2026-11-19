import json
from pathlib import Path

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


class UnsupportedFileTypeError(ValueError):
    pass


def _selected_sheet(path: Path) -> str | int:
    """Read the selected worksheet from the dataset's upload metadata.

    Legacy XLSX datasets without sheet metadata continue to use the first sheet.
    """
    metadata_path = path.parent / f"{path.stem}.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            sheet_name = metadata.get("sheet_name")
            if isinstance(sheet_name, str) and sheet_name:
                return sheet_name
        except (OSError, json.JSONDecodeError):
            pass
    return 0


def load_tabular_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".xlsx":
        metadata_path = path.parent / f"{path.stem}.json"
        header = 0
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                header = 0 if metadata.get("first_row_header", True) else None
            except (OSError, json.JSONDecodeError):
                header = 0
        dataframe = pd.read_excel(path, sheet_name=_selected_sheet(path), header=header)
        if header is None:
            dataframe.columns = [f"Column {index + 1}" for index in range(len(dataframe.columns))]
        return dataframe
    raise UnsupportedFileTypeError(f"Unsupported file type: {suffix}")
