export type AnalysisPlanningRequest = {
  business_objective: string;
  business_questions: string[];
};

export type RecommendedKPI = {
  name: string;
  description: string;
  required_columns: string[];
  calculation: string;
};

export type RecommendedAnalysis = {
  name: string;
  description: string;
  analysis_method: string;
  operation: "descriptive" | "trend" | "segment_comparison" | "correlation";
  required_columns: string[];
  business_value: string;
};

export type AnalysisQualityWarning = {
  issue_type: string;
  severity: string;
  column: string | null;
  message: string;
  recommendation: string;
};

export type AnalysisPlan = {
  dataset_id: string;
  business_objective: string;
  feasibility_status: string;
  feasibility_reason: string;
  recommended_kpis: RecommendedKPI[];
  recommended_analyses: RecommendedAnalysis[];
  available_columns: string[];
  missing_required_columns: string[];
  quality_warnings: AnalysisQualityWarning[];
};

export type AIBusinessAnalysisResponse = {
  dataset_id: string;
  ai_assisted: boolean;
  refined_objective: string;
  business_questions: string[];
  reasoning_summary: string;
  recommended_focus_areas: string[];
  clarifying_questions: string[];
  analysis_plan: AnalysisPlan;
};

async function handleAnalysisResponse<T>(
  response: Response,
  defaultMessage: string
): Promise<T> {
  if (!response.ok) {
    let message = defaultMessage;

    try {
      const error = await response.json();

      if (typeof error.detail === "string") {
        message = error.detail;
      } else if (Array.isArray(error.detail)) {
        message = error.detail
          .map((item: { msg?: string }) => item.msg ?? "Invalid request")
          .join("; ");
      }
    } catch {
      // Retain default error message.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

// Existing deterministic analysis planner.
export async function createAnalysisPlan(
  datasetId: string,
  request: AnalysisPlanningRequest
): Promise<AnalysisPlan> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/analysis-plan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
    }
  );

  return handleAnalysisResponse<AnalysisPlan>(
    response,
    "Unable to generate the analysis plan."
  );
}

// New Gemini-powered Business Analyst.
export async function createAIBusinessAnalysisPlan(
  datasetId: string,
  request: AnalysisPlanningRequest,
  signal?: AbortSignal
): Promise<AIBusinessAnalysisResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/ai-analysis-plan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
      signal,
    }
  );

  return handleAnalysisResponse<AIBusinessAnalysisResponse>(
    response,
    "Unable to generate AI business analysis."
  );
}

export type SavedArtifactType = "interpretation" | "deterministic_plan" | "ai_business_plan";
export type SavedArtifactResponse = { artifact_id: string; dataset_id: string; artifact_type: SavedArtifactType; title: string; saved_at: string; already_saved: boolean };
export async function saveBusinessArtifact(datasetId: string, request: { artifact_type: SavedArtifactType; title: string; payload: Record<string, unknown>; source_execution_id?: string }): Promise<SavedArtifactResponse> {
  const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/saved-artifacts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), cache: "no-store" });
  return handleAnalysisResponse<SavedArtifactResponse>(response, "Unable to save this business artefact.");
}
