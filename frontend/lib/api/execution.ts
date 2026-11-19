export type ExecutionAggregation =
  | "sum"
  | "average"
  | "count"
  | "min"
  | "max"
  | "median";

export type TrendInterval = "day" | "week" | "month" | "year";

// -----------------------------------------------------------------------------
// Request Types
// -----------------------------------------------------------------------------

export type DescriptiveAnalyticsRequest = {
  operation: "descriptive";
  column: string;
};

export type TrendAnalyticsRequest = {
  operation: "trend";
  column: string;
  aggregation: ExecutionAggregation;
  date_column: string;
  interval: TrendInterval;
};

export type SegmentComparisonRequest = {
  operation: "segment_comparison";
  column: string;
  aggregation: ExecutionAggregation;
  group_by: string;
};

export type CorrelationAnalyticsRequest = {
  operation: "correlation";
  column: string;
  second_column: string;
};

export type AnalyticsExecutionRequest =
  | {
      operation: "kpi";
      column: string;
      aggregation: ExecutionAggregation;
      group_by?: string | null;
    }
  | DescriptiveAnalyticsRequest
  | TrendAnalyticsRequest
  | SegmentComparisonRequest
  | CorrelationAnalyticsRequest;

// -----------------------------------------------------------------------------
// Shared Result Types
// -----------------------------------------------------------------------------

export type AnalyticsExecutionGroup = {
  group: string | number | boolean | null;
  value: number | null;
  row_count: number;
  valid_value_count: number;
  null_count: number;
};

// -----------------------------------------------------------------------------
// KPI Analysis Response
// -----------------------------------------------------------------------------

export type AnalyticsExecutionResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "kpi";
  column: string;
  aggregation: ExecutionAggregation;
  value: number;
  row_count: number;
  valid_value_count: number;
  null_count: number;
};

export type GroupedAnalyticsExecutionResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "kpi";
  column: string;
  aggregation: ExecutionAggregation;
  group_by: string;
  groups: AnalyticsExecutionGroup[];
};

// -----------------------------------------------------------------------------
// Descriptive Statistics Response
// -----------------------------------------------------------------------------

export type DescriptiveAnalyticsResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "descriptive";
  column: string;
  row_count: number;
  valid_value_count: number;
  null_count: number;
  statistics: {
    mean: number;
    median: number;
    minimum: number;
    maximum: number;
    standard_deviation: number | null;
  };
};

// -----------------------------------------------------------------------------
// Trend Analysis Response
// -----------------------------------------------------------------------------

export type TrendDataPoint = {
  period: string;
  value: number | null;
  row_count: number;
  valid_value_count: number;
  null_count: number;
};

export type TrendAnalyticsResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "trend";
  column: string;
  date_column: string;
  aggregation: ExecutionAggregation;
  interval: TrendInterval;
  points: TrendDataPoint[];
};

// -----------------------------------------------------------------------------
// Segment Comparison Response
// -----------------------------------------------------------------------------

export type SegmentComparisonResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "segment_comparison";
  column: string;
  aggregation: ExecutionAggregation;
  segment_by: string;
  segments: AnalyticsExecutionGroup[];
};

// -----------------------------------------------------------------------------
// Measure Relationship / Correlation Response
// -----------------------------------------------------------------------------

export type CorrelationDataPoint = {
  x: number;
  y: number;
};

export type CorrelationAnalyticsResponse = {
  execution_id?: string | null;
  dataset_id: string;
  operation: "correlation";
  column: string;
  second_column: string;
  correlation: number;
  observation_count: number;
  strength: string;
  direction: string;
  points: CorrelationDataPoint[];
  sampled: boolean;
};

// -----------------------------------------------------------------------------
// Unified Analytics Result
// -----------------------------------------------------------------------------

export type AnalyticsExecutionResult =
  | AnalyticsExecutionResponse
  | GroupedAnalyticsExecutionResponse
  | DescriptiveAnalyticsResponse
  | TrendAnalyticsResponse
  | SegmentComparisonResponse
  | CorrelationAnalyticsResponse;

// -----------------------------------------------------------------------------
// Execute Dataset Analytics
// -----------------------------------------------------------------------------

export async function executeDatasetAnalytics(
  datasetId: string,
  request: AnalyticsExecutionRequest
): Promise<AnalyticsExecutionResult> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/execute`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
    }
  );

  if (!response.ok) {
    let message = "Unable to execute the requested analysis.";

    try {
      const error: { detail?: unknown } = await response.json();

      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (Array.isArray(error.detail)) {
        message = error.detail
          .map((item: { msg?: string }) => item.msg ?? "Invalid request")
          .join("; ");
      }
    } catch {
      // Preserve the default error message for invalid response bodies.
    }

    throw new Error(message);
  }

  return response.json() as Promise<AnalyticsExecutionResult>;
}

// -----------------------------------------------------------------------------
// Analytics History Types
// -----------------------------------------------------------------------------

export type AnalyticsExecutionHistoryItem = {
  execution_id: string;
  dataset_id: string;
  operation: string;
  request_config: Record<string, unknown>;
  result: AnalyticsExecutionResult;
  created_at: string;
};

export type AnalyticsExecutionHistoryResponse = {
  dataset_id: string;
  total: number;
  limit: number;
  offset: number;
  executions: AnalyticsExecutionHistoryItem[];
};

// -----------------------------------------------------------------------------
// Saved Analytics Types
// -----------------------------------------------------------------------------

export type SavedAnalyticsItem = AnalyticsExecutionHistoryItem & {
  saved_at: string;
};

export type SavedAnalyticsListResponse = {
  dataset_id: string;
  total: number;
  saved_analyses: SavedAnalyticsItem[];
};

export type SavedAnalyticsResponse = {
  execution_id: string;
  dataset_id: string;
  saved: boolean;
  saved_at: string | null;
  message: string;
};

// -----------------------------------------------------------------------------
// Shared API Error Handler
// -----------------------------------------------------------------------------

async function handleApiError(
  response: Response,
  fallback: string
): Promise<never> {
  let message = fallback;

  try {
    const error = await response.json();

    if (typeof error.detail === "string") {
      message = error.detail;
    }
  } catch {
    // Keep fallback message.
  }

  throw new Error(message);
}

// -----------------------------------------------------------------------------
// Get Analytics Execution History
// -----------------------------------------------------------------------------

export async function getAnalyticsExecutionHistory(
  datasetId: string,
  limit = 100,
  offset = 0
): Promise<AnalyticsExecutionHistoryResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/executions?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
      cache: "no-store",
    }
  );

  if (!response.ok) {
    return handleApiError(
      response,
      "Unable to retrieve analytics history."
    );
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// Get Saved Analytics
// -----------------------------------------------------------------------------

export async function getSavedAnalytics(
  datasetId: string
): Promise<SavedAnalyticsListResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/saved-analyses`,
    {
      method: "GET",
      cache: "no-store",
    }
  );

  if (!response.ok) {
    return handleApiError(
      response,
      "Unable to retrieve saved analytics."
    );
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// Save Analytics Execution
// -----------------------------------------------------------------------------

export async function saveAnalyticsExecution(
  datasetId: string,
  executionId: string
): Promise<SavedAnalyticsResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/executions/${encodeURIComponent(executionId)}/save`,
    {
      method: "POST",
      cache: "no-store",
    }
  );

  if (!response.ok) {
    return handleApiError(
      response,
      "Unable to save this analytics execution."
    );
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// Unsave Analytics Execution
// -----------------------------------------------------------------------------

export async function unsaveAnalyticsExecution(
  datasetId: string,
  executionId: string
): Promise<SavedAnalyticsResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/executions/${encodeURIComponent(executionId)}/save`,
    {
      method: "DELETE",
      cache: "no-store",
    }
  );

  if (!response.ok) {
    return handleApiError(
      response,
      "Unable to remove this saved analysis."
    );
  }

  return response.json();
}

export async function downloadAnalyticsReport(
  datasetId: string
): Promise<void> {
  const response = await fetch(
    `/api/datasets/${datasetId}/report`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    let message = "Failed to generate analytics report.";

    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      // Keep the default error message.
    }

    throw new Error(message);
  }

  const blob = await response.blob();

  if (blob.size === 0) {
    throw new Error("The generated PDF is empty.");
  }

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `InsightForge_Analytics_Report_${datasetId}.pdf`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
}


// -----------------------------------------------------------------------------
// AI Analytics Interpretation
// -----------------------------------------------------------------------------

export type AIInsightFinding = {
  title: string;
  observation: string;
  business_impact: string;
};

export type AIInsightRecommendation = {
  action: string;
  rationale: string;
  priority: "high" | "medium" | "low" | string;
};

export type AIInterpretationResponse = {
  dataset_id: string;
  execution_id: string;
  ai_assisted: boolean;
  provider: string;
  model: string;
  executive_summary: string;
  key_findings: AIInsightFinding[];
  business_implications: string[];
  risks_and_limitations: string[];
  recommendations: AIInsightRecommendation[];
};

export async function generateAIInterpretation(
  datasetId: string,
  executionId: string,
  signal?: AbortSignal
): Promise<AIInterpretationResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/executions/${encodeURIComponent(executionId)}/interpret`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal,
    }
  );

  if (!response.ok) {
    return handleApiError(
      response,
      "Unable to generate AI interpretation."
    );
  }

  return response.json() as Promise<AIInterpretationResponse>;
}