const API_URL = "";

async function readApiError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (detail && typeof detail.code === "string") return detail.code.replaceAll("_", " ");
    if (typeof payload?.message === "string") return payload.message;
    return fallback;
  } catch {
    return fallback;
  }
}

export type ColumnProfile = {
  name: string;
  dtype: string;
  null_count: number;
  unique_count: number;
  min_value: string | number | null;
  max_value: string | number | null;
  semantic_role: string;
};

export type DatasetProfile = {
  dataset_id: string;
  filename: string;
  worksheet_switchable: boolean;
  rows: number;
  columns: number;
  missing_values: number;
  duplicate_rows: number;
  columns_profile: ColumnProfile[];
};

export async function getWorkbookSheets(file: File): Promise<string[]> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_URL}/api/datasets/workbook-sheets`, { method: "POST", body: form });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to inspect Excel worksheets"));
  }
  const payload: { sheets: string[] } = await response.json();
  return payload.sheets;
}

export async function uploadDataset(file: File, sheetName?: string, firstRowHeader = true): Promise<{ dataset_id: string; filename: string }> {
  const form = new FormData();
  form.append("file", file);
  if (sheetName) form.append("sheet_name", sheetName);
  form.append("first_row_header", String(firstRowHeader));
  const response = await fetch(`${API_URL}/api/datasets/upload`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await readApiError(response, "Upload failed"));
  return response.json();
}


export async function getDatasetWorksheetOptions(datasetId: string): Promise<string[]> {
  const response = await fetch(`${API_URL}/api/datasets/${datasetId}/worksheet-options`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to retrieve workbook worksheets"));
  }
  const payload: { sheets: string[] } = await response.json();
  return payload.sheets;
}

export async function selectDatasetWorksheet(
  datasetId: string,
  sheetName: string,
  firstRowHeader = true
): Promise<{ dataset_id: string; filename: string; sheet_name: string }> {
  const form = new FormData();
  form.append("sheet_name", sheetName);
  form.append("first_row_header", String(firstRowHeader));
  const response = await fetch(`${API_URL}/api/datasets/${datasetId}/select-worksheet`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to switch worksheet"));
  }
  return response.json();
}

export async function getDatasetProfile(datasetId: string): Promise<DatasetProfile> {
  const response = await fetch(`${API_URL}/api/datasets/${datasetId}/profile`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readApiError(response, "Profiling failed"));
  return response.json();
}

export type DatasetVersion = {
  dataset_id: string;
  version_number: number;
  version_type: "original" | "cleaned";
  filename: string;
  created_at: string;
  cleaning_plan_id: string | null;
  parent_dataset_id: string | null;
};

export type DatasetVersionRegistry = {
  original_dataset_id: string;
  versions: DatasetVersion[];
  updated_at: string;
};

export async function getDatasetVersions(
  datasetId: string
): Promise<DatasetVersionRegistry> {
  const response = await fetch(
    `${API_URL}/api/datasets/${datasetId}/versions`,
    { cache: "no-store" }
  );

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to retrieve dataset versions"));
  }

  return response.json();
}