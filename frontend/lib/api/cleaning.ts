export type CleaningOperationType =
  | "drop_duplicates"
  | "drop_column"
  | "fill_missing"
  | "trim_whitespace"
  | "standardize_text"
  | "convert_numeric"
  | "convert_datetime";

export type CleaningOperation = {
  type: CleaningOperationType;
  column?: string;
  columns?: string[];
  strategy?: "mean" | "median" | "mode" | "constant" | "drop_rows";
  value?: string | number | boolean | null;
  case?: "lower" | "upper" | "title";
};

export type CleaningPreview = {
  dataset_id: string;
  plan_id: string;
  status: string;
  approval_status: string;
  [key: string]: unknown;
};

export type CleaningApproval = {
  dataset_id: string;
  plan_id: string;
  status: string;
  approved_at: string;
  message: string;
};

export type CleaningExecution = {
  dataset_id: string;
  plan_id: string;
  cleaned_dataset_id: string;
  status: string;
  output_filename: string;
  original_rows: number;
  cleaned_rows: number;
  execution_results: unknown[];
  output_metrics: Record<string, unknown>;
  executed_at: string;
};

async function readResponse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Cleaning request failed."
    );
  }

  return data as T;
}

export async function generateCleaningPreview(
  datasetId: string,
  operations: CleaningOperation[]
): Promise<CleaningPreview> {
  const response = await fetch(
    `/api/datasets/${datasetId}/cleaning-preview`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operations }),
      cache: "no-store",
    }
  );

  return readResponse<CleaningPreview>(response);
}

export async function approveCleaningPlan(
  datasetId: string,
  planId: string
): Promise<CleaningApproval> {
  const response = await fetch(
    `/api/datasets/${datasetId}/cleaning-plans/${planId}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved: true }),
      cache: "no-store",
    }
  );

  return readResponse<CleaningApproval>(response);
}

export async function executeCleaningPlan(
  datasetId: string,
  planId: string
): Promise<CleaningExecution> {
  const response = await fetch(
    `/api/datasets/${datasetId}/cleaning-plans/${planId}/execute`,
    {
      method: "POST",
      cache: "no-store",
    }
  );

  return readResponse<CleaningExecution>(response);
}