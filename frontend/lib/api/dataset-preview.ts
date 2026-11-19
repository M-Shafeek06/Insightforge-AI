const API_URL = "";

export type DatasetPreviewColumn = {
  name: string;
  dtype: string;
  quality: {
    valid: { count: number; percentage: number };
    error: { count: number; percentage: number };
    empty: { count: number; percentage: number };
  };
};

export type DatasetPreviewPagination = {
  page: number;
  page_size: number;
  total_filtered_rows: number;
  total_pages: number;
};

export type DatasetPreviewResponse = {
  dataset_id: string;
  filename: string;
  total_rows: number;
  total_columns: number;
  preview_limit: number;
  preview_rows: number;
  columns: DatasetPreviewColumn[];
  records: Record<string, unknown>[];
  pagination: DatasetPreviewPagination;
  search: string | null;
  sorting: {
    sort_by: string | null;
    sort_order: "asc" | "desc";
  };
};

export type DatasetPreviewParams = {
  page?: number;
  page_size?: number;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
};

export async function getDatasetPreview(
  datasetId: string,
  params: DatasetPreviewParams = {},
): Promise<DatasetPreviewResponse> {
  const query = new URLSearchParams();

  if (params.page !== undefined) {
    query.set("page", String(params.page));
  }

  if (params.page_size !== undefined) {
    query.set("page_size", String(params.page_size));
  }

  if (params.search) {
    query.set("search", params.search);
  }

  if (params.sort_by) {
    query.set("sort_by", params.sort_by);
  }

  if (params.sort_order) {
    query.set("sort_order", params.sort_order);
  }

  const queryString = query.toString();

  const response = await fetch(
    `${API_URL}/api/datasets/${encodeURIComponent(datasetId)}/preview${
      queryString ? `?${queryString}` : ""
    }`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail || "Failed to retrieve dataset preview.",
    );
  }

  return response.json();
}

export type ColumnUniqueValuesResponse = {
  dataset_id: string;
  column: string;
  values: unknown[];
  total_unique_values: number;
  has_null: boolean;
  truncated: boolean;
  limit: number;
};

export async function getColumnUniqueValues(
  datasetId: string,
  columnName: string,
  limit = 100,
): Promise<ColumnUniqueValuesResponse> {
  const response = await fetch(
    `${API_URL}/api/datasets/${encodeURIComponent(datasetId)}/columns/${encodeURIComponent(columnName)}/unique-values?limit=${limit}`,
    { method: "GET", cache: "no-store" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const detail = error?.detail;
    throw new Error(
      typeof detail === "string" ? detail : "Failed to retrieve unique column values.",
    );
  }
  return response.json();
}
