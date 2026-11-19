"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ThemeToggle from "@/components/theme/ThemeToggle";
import CleaningPanel from "@/components/data-profile/CleaningPanel";
import type { CleaningExecution } from "@/lib/api/cleaning";
import DatasetViewer from "@/components/data-profile/DatasetViewer";

import AnalyticsExecutionPanel, {
  type AnalysisConfigurationRequest,
} from "@/components/analytics/AnalyticsExecutionPanel";

import {
  getDatasetProfile,
  getDatasetVersions,
  uploadDataset,
  getWorkbookSheets,
  getDatasetWorksheetOptions,
  selectDatasetWorksheet,
  type DatasetProfile,
  type DatasetVersionRegistry,
} from "@/lib/api/datasets";

import {
  getDatasetQuality,
  type DatasetQuality,
  type QualityIssue,
} from "@/lib/api/quality";

import {
  createAIBusinessAnalysisPlan,
  type AnalysisPlan,
  type AnalysisQualityWarning,
  type AIBusinessAnalysisResponse,
  saveBusinessArtifact,
} from "@/lib/api/analysis";
import { downloadAnalyticsReport } from "@/lib/api/execution";

const ACTIVE_DATASET_KEY = "insightforge-active-dataset";
const PENDING_BROWSER_REFRESH_KEY = "insightforge-pending-browser-refresh";

function getStatusStyle(status: string): string {
  switch (status.toLowerCase()) {
    case "excellent":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "good":
      return "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300";
    case "fair":
      return "border-yellow-500/40 bg-yellow-500/10 text-yellow-800 dark:text-yellow-300";
    case "poor":
      return "border-orange-500/40 bg-orange-500/10 text-orange-800 dark:text-orange-300";
    case "critical":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    default:
      return "border-[var(--border)] bg-[var(--surface-secondary)] text-[var(--foreground)]";
  }
}

function getSeverityStyle(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "high":
      return "border-orange-500/40 bg-orange-500/10 text-orange-800 dark:text-orange-300";
    case "medium":
      return "border-yellow-500/40 bg-yellow-500/10 text-yellow-800 dark:text-yellow-300";
    case "low":
      return "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300";
    default:
      return "border-[var(--border)] bg-[var(--surface-secondary)] text-[var(--foreground)]";
  }
}

const SEVERITY_PRIORITY: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

/**
 * Returns every quality finding for display.
 * Findings are not deduplicated by column, so lower-severity findings
 * remain visible even when the same column has a higher-severity finding.
 */
function getQualityIssuesForDisplay(issues: QualityIssue[]): QualityIssue[] {
  const issueTypePriority = (issueType: string): number => {
    switch (issueType.toLowerCase()) {
      case "empty_column":
        return 2;
      case "missing_values":
        return 1;
      default:
        return 0;
    }
  };

  return issues
    .filter((issue) =>
      ["critical", "high", "medium", "low"].includes(
        issue.severity.toLowerCase()
      )
    )
    .slice()
    .sort((a, b) => {
      const severityDifference =
        (SEVERITY_PRIORITY[b.severity.toLowerCase()] ?? 0) -
        (SEVERITY_PRIORITY[a.severity.toLowerCase()] ?? 0);

      if (severityDifference !== 0) return severityDifference;

      const issueTypeDifference =
        issueTypePriority(b.issue_type) - issueTypePriority(a.issue_type);

      if (issueTypeDifference !== 0) return issueTypeDifference;

      return (a.column ?? "").localeCompare(b.column ?? "");
    });
}

function QualityIssueCard({ issue }: { issue: QualityIssue }) {
  const severityAccent: Record<string, string> = {
    critical: "border-l-red-500",
    high: "border-l-orange-500",
    medium: "border-l-amber-500",
    low: "border-l-blue-500",
  };

  return (
    <article
      className={`quality-issue-card flex h-full flex-col rounded-xl border border-[var(--border)] border-l-4 ${
        severityAccent[issue.severity.toLowerCase()] ?? "border-l-[var(--accent)]"
      } bg-[var(--surface-secondary)] px-3.5 py-3 shadow-sm transition-all duration-200 sm:px-4 sm:py-3.5`}
    >
      <div className="flex flex-col justify-between gap-2.5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-md border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${getSeverityStyle(issue.severity)}`}
            >
              {issue.severity}
            </span>

            <span className="text-xs font-medium capitalize tracking-wide text-[var(--foreground-secondary)]">
              {issue.issue_type.replaceAll("_", " ")}
            </span>
          </div>

          <h4 className="mt-1.5 text-sm font-bold tracking-tight text-[var(--foreground)]">
            {issue.column ?? "Dataset"}
          </h4>

          <p className="mt-1 max-w-4xl text-xs leading-5 text-[var(--foreground-secondary)]">
            {issue.message}
          </p>
        </div>

        <div className="quality-impact-metric grid min-w-[108px] shrink-0 grid-cols-2 items-center gap-x-2 gap-y-0.5 rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] px-2.5 py-2 sm:grid-cols-1 sm:text-right">
          <p className="text-base font-bold tabular-nums text-[var(--foreground)]">
            {issue.affected_rows.toLocaleString()}
          </p>
          <p className="text-[10px] font-medium text-[var(--foreground-secondary)] sm:order-2">
            Affected rows
          </p>
          <p className="col-span-2 text-[10px] font-semibold tabular-nums text-[var(--foreground-secondary)] sm:col-span-1">
            {issue.affected_percentage.toLocaleString(undefined, {
              maximumFractionDigits: 2,
            })}% of dataset
          </p>
        </div>
      </div>

      <div className="quality-recommendation mt-auto flex flex-col gap-1.5 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent-soft)] px-3 py-2 pt-2.5 sm:flex-row sm:items-start sm:gap-3">
        <div className="flex shrink-0 items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" aria-hidden="true" />
          <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--accent-strong)]">
            Recommended action
          </p>
        </div>
        <p className="text-xs leading-5 text-[var(--foreground)]">
          {issue.recommendation}
        </p>
      </div>
    </article>
  );
}

function AnalysisQualityWarningCard({
  warning,
}: {
  warning: AnalysisQualityWarning;
}) {
  return (
    <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full border px-2.5 py-1 text-xs font-semibold uppercase ${getSeverityStyle(warning.severity)}`}
        >
          {warning.severity}
        </span>

        <span className="text-xs text-[var(--foreground-secondary)]">
          {warning.issue_type.replaceAll("_", " ")}
        </span>
      </div>

      <h4 className="mt-3 font-semibold">
        {warning.column ?? "Dataset"}
      </h4>

      <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
        {warning.message}
      </p>

      <div className="mt-3 rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-cyan-700 dark:text-cyan-400">
          Recommendation
        </p>

        <p className="mt-1 text-sm leading-6">
          {warning.recommendation}
        </p>
      </div>
    </article>
  );
}

function AnalysisPlanResults({
  plan,
  onConfigureAnalysis,
}: {
  plan: AnalysisPlan;
  onConfigureAnalysis: (
    analysis: AnalysisPlan["recommended_analyses"][number]
  ) => void;
}) {
  const feasibilityLabel = plan.feasibility_status.replaceAll("_", " ");

  return (
    <div className="mt-6 space-y-6">
      <section className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground-secondary)]">
              Feasibility assessment
            </p>

            <h4 className="mt-2 text-xl font-semibold capitalize">
              {feasibilityLabel}
            </h4>

            <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
              {plan.feasibility_reason}
            </p>
          </div>

          <span
            className={`inline-flex w-fit rounded-full border px-3 py-1.5 text-xs font-semibold uppercase ${getStatusStyle(
              plan.feasibility_status === "feasible"
                ? "good"
                : plan.feasibility_status === "partially_feasible"
                  ? "fair"
                  : "poor"
            )}`}
          >
            {feasibilityLabel}
          </span>
        </div>
      </section>

      <section>
        <div className="mb-4">
          <h4 className="text-lg font-semibold">Recommended KPIs</h4>
          <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
            Suggested business metrics based on the available dataset columns.
          </p>
        </div>

        {plan.recommended_kpis.length === 0 ? (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5 text-sm text-[var(--foreground-secondary)]">
            No suitable KPI recommendations were identified for this dataset.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {plan.recommended_kpis.map((kpi, index) => (
              <article
                key={`${kpi.name}-${index}`}
                className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
              >
                <h5 className="font-semibold">{kpi.name}</h5>

                <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
                  {kpi.description}
                </p>

                <div className="mt-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground-secondary)]">
                    Calculation definition
                  </p>

                  <code className="mt-2 block break-all rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] p-3 text-sm">
                    {kpi.calculation}
                  </code>
                </div>

                <div className="mt-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground-secondary)]">
                    Required columns
                  </p>

                  <div className="mt-2 flex flex-wrap gap-2">
                    {kpi.required_columns.map((column) => (
                      <span
                        key={column}
                        className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs"
                      >
                        {column}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-4">
          <h4 className="text-lg font-semibold">Recommended Analyses</h4>
          <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
            Proposed analytical methods. These analyses have not been executed.
          </p>
        </div>

        {plan.recommended_analyses.length === 0 ? (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5 text-sm text-[var(--foreground-secondary)]">
            No suitable analysis methods were identified.
          </div>
        ) : (
          <div className="space-y-4">
            {plan.recommended_analyses.map((analysis, index) => (
              <article
                key={`${analysis.name}-${index}`}
                className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
              >
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div>
                    <h5 className="font-semibold">{analysis.name}</h5>

                    <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
                      {analysis.description}
                    </p>
                  </div>

                  <span className="inline-flex w-fit rounded-full border border-cyan-500/30 bg-cyan-500/5 px-3 py-1 text-xs font-medium text-cyan-700 dark:text-cyan-300">
                    {analysis.analysis_method}
                  </span>
                </div>

                <div className="mt-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground-secondary)]">
                    Required columns
                  </p>

                  <div className="mt-2 flex flex-wrap gap-2">
                    {analysis.required_columns.map((column) => (
                      <span
                        key={column}
                        className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs"
                      >
                        {column}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-5">
                  <button
                    type="button"
                    onClick={() => onConfigureAnalysis(analysis)}
                    className="inline-flex items-center justify-center rounded-lg bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
                  >
                    Configure Analysis
                  </button>
                </div>

                <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground-secondary)]">
                    Business value
                  </p>

                  <p className="mt-2 text-sm leading-6">
                    {analysis.business_value}
                  </p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-4">
          <h4 className="text-lg font-semibold">Available Columns</h4>
          <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
            Columns detected by the analysis planner.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {plan.available_columns.map((column) => (
            <span
              key={column}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-2 text-sm"
            >
              {column}
            </span>
          ))}
        </div>
      </section>

      {plan.missing_required_columns.length > 0 && (
        <section className="rounded-xl border border-orange-500/40 bg-orange-500/5 p-5">
          <h4 className="font-semibold">Missing Required Columns</h4>

          <p className="mt-2 text-sm text-[var(--foreground-secondary)]">
            Some recommended analyses require columns that are not available.
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {plan.missing_required_columns.map((column) => (
              <span
                key={column}
                className="rounded-full border border-orange-500/40 px-3 py-1 text-xs"
              >
                {column}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Quality findings are presented once in the dedicated Data Quality section. */}
    </div>
  );
}

export default function ProfileView() {
  const [versionRegistry, setVersionRegistry] =
    useState<DatasetVersionRegistry | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);  
  const [versionError, setVersionError] = useState<string | null>(null);
  const [switchingVersion, setSwitchingVersion] = useState(false);
  const [quality, setQuality] = useState<DatasetQuality | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingWorkbook, setPendingWorkbook] = useState<File | null>(null);
  const [workbookSheets, setWorkbookSheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState("");
  const [firstRowHeader, setFirstRowHeader] = useState(true);
  const [worksheetDialogMode, setWorksheetDialogMode] = useState<"upload" | "switch">("upload");
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  const [businessObjective, setBusinessObjective] = useState("");
  const [businessQuestions, setBusinessQuestions] = useState<string[]>([""]);
  const [analysisPlan, setAnalysisPlan] = useState<AnalysisPlan | null>(null);

  const [aiAnalysis, setAiAnalysis] =
    useState<AIBusinessAnalysisResponse | null>(null);

  const [aiPlanning, setAiPlanning] = useState(false);
  const aiPlanningAbortRef = useRef<AbortController | null>(null);
  const [savingAIPlan, setSavingAIPlan] = useState(false);
  const [aiPlanSaved, setAiPlanSaved] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [reportDownloadError, setReportDownloadError] = useState<string | null>(null);

  const [planningError, setPlanningError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      aiPlanningAbortRef.current?.abort();
    };
  }, []);
  const [requestedAnalysis, setRequestedAnalysis] =
    useState<AnalysisConfigurationRequest | null>(null);

  // Refresh confirmation state.
  const [refreshDialogOpen, setRefreshDialogOpen] = useState(false);
  const [refreshingWorkspace, setRefreshingWorkspace] = useState(false);
  const refreshCancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!refreshDialogOpen) return;

    refreshCancelButtonRef.current?.focus();

    function handleDialogKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !refreshingWorkspace) {
        event.preventDefault();
        setRefreshDialogOpen(false);
      }
    }

    window.addEventListener("keydown", handleDialogKeyDown);

    return () => {
      window.removeEventListener("keydown", handleDialogKeyDown);
    };
  }, [refreshDialogOpen, refreshingWorkspace]);

  // Ask the browser to confirm document unloads.
  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      try {
        window.sessionStorage.setItem(PENDING_BROWSER_REFRESH_KEY, "1");
      } catch {
        // If storage is unavailable, the browser prompt can still be shown.
      }

      event.preventDefault();
      event.returnValue = "";
    }

    function clearCanceledUnloadMarker() {
      window.setTimeout(() => {
        if (document.visibilityState === "visible") {
          try {
            window.sessionStorage.removeItem(PENDING_BROWSER_REFRESH_KEY);
          } catch {
            // Ignore storage restrictions.
          }
        }
      }, 100);
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("focus", clearCanceledUnloadMarker);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("focus", clearCanceledUnloadMarker);
    };
  }, []);

  // Intercept common browser refresh shortcuts.
  useEffect(() => {
    function handleRefreshShortcut(event: KeyboardEvent) {
      if (typeof event.key !== "string") return;
        const key = event.key.toLowerCase();

      const isRefreshShortcut =
        event.key === "F5" ||
        ((event.ctrlKey || event.metaKey) && key === "r");

      if (!isRefreshShortcut || event.altKey) return;

      event.preventDefault();
      event.stopPropagation();
      setRefreshDialogOpen(true);
    }

    window.addEventListener("keydown", handleRefreshShortcut, true);

    return () => {
      window.removeEventListener("keydown", handleRefreshShortcut, true);
    };
  }, []);

  function cancelWorkspaceRefresh() {
    if (refreshingWorkspace) return;
    setRefreshDialogOpen(false);
  }

  function confirmWorkspaceRefresh() {
    if (refreshingWorkspace) return;

    setRefreshingWorkspace(true);

    try {
      window.sessionStorage.removeItem(ACTIVE_DATASET_KEY);
      window.location.reload();
    } catch {
      setRefreshingWorkspace(false);
      setRefreshDialogOpen(false);
      setError(
        "Unable to reset the workspace. Please try refreshing again."
      );
    }
  }

  function handleConfigureAnalysis(
    analysis: AnalysisPlan["recommended_analyses"][number]
  ) {
    if (!profile) return;

    const validOperations = [
      "descriptive",
      "trend",
      "segment_comparison",
      "correlation",
    ] as const;

    if (!validOperations.includes(analysis.operation)) {
      setPlanningError(
        "This recommendation uses an unsupported analysis operation."
      );
      return;
    }

    const requiredColumnCount =
      analysis.operation === "descriptive" ? 1 : 2;

    const availableColumns = new Set(
      profile.columns_profile.map((column) => column.name)
    );

    if (
      analysis.required_columns.length !== requiredColumnCount ||
      new Set(analysis.required_columns).size !== requiredColumnCount ||
      analysis.required_columns.some(
        (column) => !availableColumns.has(column)
      )
    ) {
      setPlanningError(
        "This recommendation cannot be configured because its required columns are unavailable or invalid."
      );
      return;
    }

    setPlanningError(null);

    setRequestedAnalysis((previous) => ({
      id: (previous?.id ?? 0) + 1,
      dataset_id: profile.dataset_id,
      operation: analysis.operation,
      columns: [...analysis.required_columns],
    }));

    window.setTimeout(() => {
      document
        .getElementById("analytics-execution-panel")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }

  async function loadDataset(datasetId: string) {
    setLoading(true);
    setError(null);
    setQualityError(null);
    setPlanningError(null);
    // Keep the current profile mounted while the next version loads.
    // This preserves AnalyticsExecutionPanel's per-version result cache.
    setVersionRegistry(null);
    setVersionError(null);
    setQuality(null);
    setAnalysisPlan(null);
    setAiAnalysis(null);
    setRequestedAnalysis(null);
    setBusinessObjective("");
    setBusinessQuestions([""]);

    try {
      const result = await getDatasetProfile(datasetId);
      setProfile(result);

      try {
        const registry = await getDatasetVersions(datasetId);
        setVersionRegistry(registry);
        setVersionError(null);
      } catch (err) {
        setVersionRegistry(null);
        setVersionError(
          err instanceof Error ? err.message : "Unable to load dataset versions."
        );
      }

      try {
        const qualityResult = await getDatasetQuality(datasetId);
        setQuality(qualityResult);
      } catch (err) {
        setQualityError(
          err instanceof Error
            ? err.message
            : "Unable to assess dataset quality."
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to restore the saved dataset."
      );

      setVersionRegistry(null);
      setProfile(null);
      window.sessionStorage.removeItem(ACTIVE_DATASET_KEY);
    } finally {
      setLoading(false);
    }
  }

  async function handleVersionChange(datasetId: string) {
    if (!datasetId || datasetId === profile?.dataset_id || switchingVersion) return;

    setSwitchingVersion(true);
    try {
      window.sessionStorage.setItem(ACTIVE_DATASET_KEY, datasetId);
      await loadDataset(datasetId);
    } finally {
      setSwitchingVersion(false);
    }
  }

    async function handleCleaningComplete(result: CleaningExecution) {
    const cleanedDatasetId = result.cleaned_dataset_id;

    if (!cleanedDatasetId) {
      setError(
        "Cleaning completed, but the cleaned dataset ID was not returned."
      );
      return;
    }

    try {
      window.sessionStorage.setItem(
        ACTIVE_DATASET_KEY,
        cleanedDatasetId
      );
    } catch {
      setError(
        "Cleaning completed, but the active dataset session could not be updated."
      );
      return;
    }

    // Automatically activate the cleaned dataset.
    await loadDataset(cleanedDatasetId);
  }

  useEffect(() => {
    let cancelled = false;

    async function restoreDataset() {
      try {
        const pendingBrowserUnload = window.sessionStorage.getItem(
          PENDING_BROWSER_REFRESH_KEY
        );

        if (pendingBrowserUnload === "1") {
          window.sessionStorage.removeItem(PENDING_BROWSER_REFRESH_KEY);
          window.sessionStorage.removeItem(ACTIVE_DATASET_KEY);
          return;
        }

        const savedDatasetId = window.sessionStorage.getItem(
          ACTIVE_DATASET_KEY
        );

        if (!savedDatasetId || cancelled) {
          return;
        }

        await loadDataset(savedDatasetId);
      } finally {
        if (!cancelled) {
          setRestoring(false);
        }
      }
    }

    void restoreDataset();

    return () => {
      cancelled = true;
    };
  }, []);

  async function processUpload(file: File, sheetName?: string, useFirstRowAsHeader = true) {
    setLoading(true);
    setError(null);
    setQualityError(null);
    setPlanningError(null);
    setProfile(null);
    setVersionRegistry(null);
    setVersionError(null);
    setQuality(null);
    setAnalysisPlan(null);
    setAiAnalysis(null);
    setRequestedAnalysis(null);
    setBusinessObjective("");
    setBusinessQuestions([""]);
    try {
      const uploaded = await uploadDataset(file, sheetName, useFirstRowAsHeader);
      window.sessionStorage.setItem(ACTIVE_DATASET_KEY, uploaded.dataset_id);
      await loadDataset(uploaded.dataset_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while processing the dataset.");
    } finally {
      setLoading(false);
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    if (file.name.toLowerCase().endsWith(".xlsx")) {
      setLoading(true);
      setError(null);
      try {
        const sheets = await getWorkbookSheets(file);
        if (sheets.length >= 1) {
          setPendingWorkbook(file);
          setWorkbookSheets(sheets);
          setSelectedSheet(sheets[0]);
          setFirstRowHeader(true);
          setWorksheetDialogMode("upload");
          return;
        }
        await processUpload(file, sheets[0], true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to inspect the Excel workbook.");
      } finally {
        setLoading(false);
      }
      return;
    }
    await processUpload(file);
  }

  async function confirmWorksheetSelection() {
    if (!selectedSheet) return;
    if (worksheetDialogMode === "upload") {
      if (!pendingWorkbook) return;
      const file = pendingWorkbook;
      setPendingWorkbook(null);
      setWorkbookSheets([]);
      await processUpload(file, selectedSheet, firstRowHeader);
      return;
    }

    if (!profile) return;
    setLoading(true);
    setError(null);
    try {
      const selected = await selectDatasetWorksheet(
        profile.dataset_id,
        selectedSheet,
        firstRowHeader
      );
      window.sessionStorage.setItem(ACTIVE_DATASET_KEY, selected.dataset_id);
      setPendingWorkbook(null);
      setWorkbookSheets([]);
      await loadDataset(selected.dataset_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to switch worksheet.");
    } finally {
      setLoading(false);
    }
  }

  async function openWorksheetSwitcher() {
    if (!profile || loading || switchingVersion) return;
    setLoading(true);
    setError(null);
    try {
      const sheets = await getDatasetWorksheetOptions(profile.dataset_id);
      setWorkbookSheets(sheets);
      setSelectedSheet(sheets[0] ?? "");
      setFirstRowHeader(true);
      setWorksheetDialogMode("switch");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load workbook worksheets.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateAIBusinessAnalysis(
  event: FormEvent<HTMLFormElement>
) {
  event.preventDefault();

  if (!profile) return;

  const objective = businessObjective.trim();

  if (objective.length < 5) {
    setPlanningError(
      "Enter a business objective containing at least 5 characters."
    );
    return;
  }

  if (objective.length > 1000) {
    setPlanningError(
      "The business objective cannot exceed 1,000 characters."
    );
    return;
  }

  const questions = businessQuestions
    .map((question) => question.trim())
    .filter(Boolean);

  if (questions.length > 20) {
    setPlanningError(
      "You can submit a maximum of 20 business questions."
    );
    return;
  }

  aiPlanningAbortRef.current?.abort();
  const controller = new AbortController();
  aiPlanningAbortRef.current = controller;
  setAiPlanning(true);
  setPlanningError(null);

  try {
    const result = await createAIBusinessAnalysisPlan(
      profile.dataset_id,
      {
        business_objective: objective,
        business_questions: questions,
      },
      controller.signal
    );

    setAiAnalysis(result);
    setAnalysisPlan(result.analysis_plan);
    setAiPlanSaved(false);
  } catch (err) {
    if (controller.signal.aborted || (err instanceof Error && err.name === "AbortError")) {
      setPlanningError(null);
    } else {
      setPlanningError(
        err instanceof Error
          ? err.message
          : "Unable to generate AI business analysis."
      );
    }
  } finally {
    if (aiPlanningAbortRef.current === controller) {
      aiPlanningAbortRef.current = null;
      setAiPlanning(false);
    }
  }
}

  function handleCancelAIPlanning() {
    aiPlanningAbortRef.current?.abort();
    aiPlanningAbortRef.current = null;
    setAiPlanning(false);
    setPlanningError(null);
  }

  async function handleSaveAIPlan() {
    if (!profile || !aiAnalysis || savingAIPlan || aiPlanSaved) return;
    setSavingAIPlan(true); setPlanningError(null);
    try {
      await saveBusinessArtifact(profile.dataset_id, { artifact_type: "ai_business_plan", title: `AI Business Analysis Plan — ${aiAnalysis.refined_objective}`, payload: aiAnalysis as unknown as Record<string, unknown> });
      setAiPlanSaved(true);
    } catch (error) { setPlanningError(error instanceof Error ? error.message : "Unable to save AI business plan."); }
    finally { setSavingAIPlan(false); }
  }

  async function handleDownloadSavedReport() {
    if (!profile || downloadingReport) return;
    setDownloadingReport(true); setReportDownloadError(null);
    try { await downloadAnalyticsReport(profile.dataset_id); }
    catch (error) { setReportDownloadError(error instanceof Error ? error.message : "Unable to download PDF report."); }
    finally { setDownloadingReport(false); }
  }

  function updateBusinessQuestion(index: number, value: string) {
    setBusinessQuestions((current) =>
      current.map((question, currentIndex) =>
        currentIndex === index ? value : question
      )
    );
  }

  function addBusinessQuestion() {
    setBusinessQuestions((current) => {
      if (current.length >= 20) {
        return current;
      }

      return [...current, ""];
    });
  }

  function removeBusinessQuestion(index: number) {
    setBusinessQuestions((current) => {
      const updated = current.filter(
        (_, currentIndex) => currentIndex !== index
      );

      return updated.length > 0 ? updated : [""];
    });
  }

  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeNav, setActiveNav] = useState("workspace");

  // Track the section currently visible in the workspace.
  useEffect(() => {
    if (!profile) {
      setActiveNav("workspace");
      return;
    }

    const sectionMap: Record<string, string> = {
      "dataset-overview": "overview",
      "dataset-preview": "overview",
      "data-quality": "quality",
      "data-cleaning": "cleaning",
      "analytics-execution-panel": "analysis",
      "analysis-planner": "planner",
      "column-intelligence": "columns",
    };

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleSections = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) =>
              a.boundingClientRect.top - b.boundingClientRect.top
          );

        if (visibleSections.length > 0) {
          const sectionId = visibleSections[0].target.id;
          const navId = sectionMap[sectionId];

          if (navId) {
            setActiveNav(navId);
          }
        }
      },
      {
        rootMargin: "-15% 0px -70% 0px",
        threshold: 0,
      }
    );

    Object.keys(sectionMap).forEach((sectionId) => {
      const section = document.getElementById(sectionId);

      if (section) {
        observer.observe(section);
      }
    });

    return () => observer.disconnect();
  }, [profile]);

  const navigateToSection = (sectionId: string, navId: string) => {
    setActiveNav(navId);
    setMobileNavOpen(false);

    if (sectionId === "workspace") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    document.getElementById(sectionId)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const isInitializing = restoring && !profile && !error;

  return (
    <>
      {workbookSheets.length > 0 && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4" role="dialog" aria-modal="true" aria-labelledby="worksheet-dialog-title">
          <div className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-2xl">
            <h2 id="worksheet-dialog-title" className="text-lg font-semibold">
              {worksheetDialogMode === "upload" ? "Choose a worksheet" : "Change worksheet"}
            </h2>
            <p className="mt-2 text-sm text-[var(--foreground-secondary)]">
              {worksheetDialogMode === "upload"
                ? "Select the worksheet you want to analyse."
                : "A new dataset will be created from the selected worksheet. Your current worksheet and its saved analytics will remain unchanged."}
            </p>
            <label htmlFor="workbook-sheet-select" className="mt-5 block text-sm font-medium">Worksheet</label>
            <select id="workbook-sheet-select" value={selectedSheet} onChange={(event) => setSelectedSheet(event.target.value)} className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-3 text-sm">
              {workbookSheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}
            </select>
            <label className="mt-5 flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={firstRowHeader}
                onChange={(event) => setFirstRowHeader(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-cyan-600"
              />
              <span>
                <span className="block font-medium">Use first row as column headers</span>
                <span className="mt-1 block text-xs text-[var(--foreground-secondary)]">
                  Turn this off when the worksheet does not contain a header row.
                </span>
              </span>
            </label>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => { setPendingWorkbook(null); setWorkbookSheets([]); }} className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm">Cancel</button>
              <button type="button" onClick={() => void confirmWorksheetSelection()} disabled={!selectedSheet || loading} className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">
                {worksheetDialogMode === "upload" ? "Upload worksheet" : "Switch worksheet"}
              </button>
            </div>
          </div>
        </div>
      )}
      <main className="app-pattern min-h-screen bg-[var(--background)] px-4 py-6 text-[var(--foreground)] transition-colors duration-200 sm:px-6 lg:px-8">
      <nav
        id="insightforge-navbar"
        aria-label="Main navigation"
        className="insightforge-navbar sticky top-0 z-50 -mx-4 -mt-6 mb-8 px-4 py-4 sm:-mx-6 sm:px-6 sm:py-4 lg:-mx-8 lg:px-8"
      >
        <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => navigateToSection("workspace", "workspace")}
            className="group flex min-w-0 items-center gap-3 rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
            aria-label="InsightForge AI workspace home"
          >
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-base font-black tracking-tight text-white shadow-lg shadow-cyan-500/20">
              IF
            </span>

            <span className="min-w-0">
              <span className="block truncate text-base font-extrabold tracking-tight text-[var(--foreground)] sm:text-lg">
                InsightForge{" "}
                <span className="text-cyan-600 dark:text-cyan-400">
                  AI
                </span>
              </span>

              <span className="hidden text-[11px] font-medium tracking-wide text-[var(--foreground-secondary)] sm:block">
                BUSINESS INTELLIGENCE
              </span>
            </span>
          </button>

          {/* Desktop navigation */}
          <div className="navbar-links-scroll hidden min-w-0 flex-1 items-center justify-center gap-1 lg:flex">
            {[
              { id: "workspace", label: "Workspace", target: "workspace" },
              { id: "overview", label: "Overview", target: "dataset-overview" },
              { id: "quality", label: "Data quality", target: "data-quality" },
              { id: "cleaning", label: "Cleaning", target: "data-cleaning" },
              {
                id: "planner",
                label: "Business planner",
                target: "analysis-planner",
              },
              {
                id: "analysis",
                label: "Analysis",
                target: "analytics-execution-panel",
              },
              {
                id: "columns",
                label: "Columns",
                target: "column-intelligence",
              },
            ].map((item) => {
              const disabled = !profile && item.id !== "workspace";
              const active = activeNav === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => navigateToSection(item.target, item.id)}
                  className={`navbar-link relative rounded-lg px-4 py-3 text-sm font-bold transition-colors ${
                    active
                      ? "is-active text-cyan-700 dark:text-cyan-300"
                      : "text-[var(--foreground-secondary)] hover:text-[var(--foreground)]"
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  {item.label}

                  {active && (
                    <span className="absolute inset-x-3 -bottom-1 h-1 rounded-full bg-cyan-500" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-bold text-[var(--foreground-secondary)] xl:inline-flex">
              <span
                className={`h-2 w-2 rounded-full ${
                  profile
                    ? "bg-emerald-500"
                    : "bg-[var(--foreground-secondary)]/40"
                }`}
              />
              {profile ? "Dataset loaded" : "Workspace ready"}
            </span>

            {/* Application-controlled refresh button */}
            <button
              type="button"
              onClick={() => setRefreshDialogOpen(true)}
              aria-label="Refresh workspace and clear the active dataset"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 text-sm font-semibold text-[var(--foreground)] transition-colors hover:border-cyan-500/50 hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                className="h-4 w-4"
                aria-hidden="true"
              >
                <path
                  d="M20 7v5h-5M4 17v-5h5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M5.6 9A7 7 0 0 1 17.4 6L20 12M4 12l2.6 6A7 7 0 0 0 18.4 15"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>

              <span className="hidden sm:inline">Refresh</span>
            </button>

            <span className="theme-toggle-icon-only">
              <ThemeToggle />
            </span>

            <button
              type="button"
              onClick={() => setMobileNavOpen((open) => !open)}
              aria-label={
                mobileNavOpen
                  ? "Close navigation menu"
                  : "Open navigation menu"
              }
              aria-expanded={mobileNavOpen}
              aria-controls="insightforge-mobile-navigation"
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] text-[var(--foreground)] transition-colors hover:bg-[var(--surface-muted)] lg:hidden"
            >
              {mobileNavOpen ? (
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="h-5 w-5"
                  aria-hidden="true"
                >
                  <path
                    d="m6 6 12 12M18 6 6 18"
                    strokeLinecap="round"
                  />
                </svg>
              ) : (
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="h-5 w-5"
                  aria-hidden="true"
                >
                  <path
                    d="M4 7h16M4 12h16M4 17h16"
                    strokeLinecap="round"
                  />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile navigation */}
        {mobileNavOpen && (
          <div
            id="insightforge-mobile-navigation"
            className="mx-auto mt-3 grid max-w-[1600px] grid-cols-2 gap-2 border-t border-[var(--border)] pt-3 sm:grid-cols-3 lg:hidden"
          >
            {[
              { id: "workspace", label: "Workspace", target: "workspace" },
              { id: "overview", label: "Overview", target: "dataset-overview" },
              { id: "quality", label: "Data quality", target: "data-quality" },
              { id: "cleaning", label: "Cleaning", target: "data-cleaning" },
              {
                id: "planner",
                label: "Business planner",
                target: "analysis-planner",
              },
              {
                id: "analysis",
                label: "Analysis",
                target: "analytics-execution-panel",
              },
              {
                id: "columns",
                label: "Columns",
                target: "column-intelligence",
              },
            ].map((item) => {
              const disabled = !profile && item.id !== "workspace";
              const active = activeNav === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => navigateToSection(item.target, item.id)}
                  className={`rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                    active
                      ? "border-cyan-500/30 text-cyan-700 dark:text-cyan-300"
                      : "border-[var(--border)] text-[var(--foreground-secondary)]"
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        )}
      </nav>

      <div id="workspace" className="mx-auto w-full max-w-[1600px] space-y-6">
        <section
          className="workspace-upload-panel"
          aria-label="Dataset workspace and upload"
        >
          <header className="workspace-intro">
            <div className="workspace-eyebrow">
              <span className="workspace-eyebrow-dot" />
              YOUR DATA WORKSPACE
            </div>

            <h1>
              Turn raw data into <span>clear decisions.</span>
            </h1>

            <p className="workspace-description">
              Profile datasets, identify data-quality issues, and uncover
              useful business signals in one focused workspace.
            </p>

            <div
              className="workspace-capabilities"
              aria-label="Workspace capabilities"
            >
              <span>
                <i aria-hidden="true">01</i> Profile
              </span>
              <span>
                <i aria-hidden="true">02</i> Validate
              </span>
              <span>
                <i aria-hidden="true">03</i> Analyze
              </span>
            </div>
          </header>

          <div className="workspace-upload glass-panel-interactive">
            <button
              type="button"
              className="upload-icon-button"
              aria-label="Choose a CSV or XLSX dataset to upload"
              disabled={loading || restoring}
              onClick={() => document.getElementById("dataset-file-input")?.click()}
            >
              <span className="upload-icon-wrap" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  className="h-7 w-7"
                >
                  <path
                    d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
            </button>

            <span className="upload-title">Upload your dataset</span>

            <span className="upload-description">
              Click the upload icon to choose a file from your device.
            </span>

            <span className="upload-formats">
              <b>CSV</b>
              <b>XLSX</b>
              <span>Up to 50 MB</span>
            </span>

            <input
              id="dataset-file-input"
              className="sr-only"
              type="file"
              accept=".csv,.xlsx"
              disabled={loading || restoring}
              onChange={(event) => {
                const file = event.target.files?.[0];
                void handleFile(file);
                event.currentTarget.value = "";
              }}
            />
          </div>
        </section>

        {isInitializing && (
          <div
            role="status"
            className="mb-6 rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4 text-sm text-[var(--foreground-secondary)]"
          >
            Checking for your current session dataset...
          </div>
        )}

        {loading && (
          <div
            role="status"
            className="mt-6 rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4 text-sm text-cyan-700 dark:text-cyan-300"
          >
            {profile
              ? "Refreshing dataset quality assessment..."
              : "Uploading or restoring dataset, generating its profile, and assessing data quality..."}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-6 rounded-lg border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-300"
          >
            <p className="font-semibold">Dataset unavailable</p>
            <p className="mt-1">{error}</p>
            <p className="mt-2 text-sm">
              Upload the dataset again to start a new analysis.
            </p>
          </div>
        )}

        {profile && (
          <section className="mt-10 space-y-8">
            <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
              <div>
                <p className="text-sm text-[var(--foreground-secondary)]">
                  Analyzed dataset
                </p>

                <h2 className="mt-1 text-2xl font-semibold">
                  {profile.filename}
                </h2>
              </div>

              <div className="flex flex-col gap-3 md:items-end">
                <p className="break-all font-mono text-xs text-[var(--foreground-secondary)]">
                  Dataset ID: {profile.dataset_id}
                </p>
                {profile.worksheet_switchable && (
                  <button
                    type="button"
                    onClick={() => void openWorksheetSwitcher()}
                    disabled={loading || switchingVersion}
                    className="w-fit rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition hover:border-cyan-500 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Change worksheet
                  </button>
                )}

                {versionRegistry && versionRegistry.versions.length > 0 && (
                  <div className="flex flex-col gap-1.5 md:items-end">
                    <label htmlFor="dataset-version-selector" className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)]">
                      Active dataset version
                    </label>
                    <select
                      id="dataset-version-selector"
                      value={profile.dataset_id}
                      disabled={loading || switchingVersion}
                      onChange={(event) => void handleVersionChange(event.target.value)}
                      className="min-w-[260px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm text-[var(--foreground)] outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-wait disabled:opacity-60"
                    >
                      {versionRegistry.versions
                        .slice()
                        .sort((a, b) => a.version_number - b.version_number)
                        .map((version) => (
                          <option key={version.dataset_id} value={version.dataset_id}>
                            {`V${version.version_number} · ${version.version_type === "original" ? "Original" : "Cleaned"} · ${version.filename}`}
                          </option>
                        ))}
                    </select>
                    {switchingVersion && (
                      <span className="text-xs text-cyan-600 dark:text-cyan-400">Switching dataset version...</span>
                    )}
                  </div>
                )}

                {versionError && (
                  <p className="text-xs text-orange-700 dark:text-orange-300">
                    Version history unavailable: {versionError}
                  </p>
                )}
              </div>
            </div>

            {/* 1. Unified Dataset Overview & Preview */}
            <section
              id="dataset-overview"
              className="scroll-mt-28 space-y-7"
              aria-labelledby="dataset-overview-heading"
            >
              <div>
                <h3
                  id="dataset-overview-heading"
                  className="text-xl font-semibold tracking-tight"
                >
                  Dataset Overview &amp; Preview
                </h3>
                <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
                  Review dataset health metrics and explore the underlying records in one place.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Rows", profile.rows.toLocaleString()],
                  ["Columns", profile.columns.toLocaleString()],
                  ["Missing values", profile.missing_values.toLocaleString()],
                  ["Duplicate rows", profile.duplicate_rows.toLocaleString()],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="glass-panel-interactive rounded-xl border border-[var(--border)] p-5 transition-colors duration-200"
                  >
                    <p className="text-sm text-[var(--foreground-secondary)]">
                      {label}
                    </p>
                    <p className="mt-2 text-2xl font-bold">{value}</p>
                  </div>
                ))}
              </div>

              <DatasetViewer datasetId={profile.dataset_id} />
            </section>

            {/* 2. Data Quality */}
              <section
                id="data-quality"
                className="scroll-mt-28"
                aria-labelledby="data-quality-heading"
              >
                <div className="mb-5">
                  <h3
                    id="data-quality-heading"
                    className="text-xl font-semibold"
                  >
                    Data Quality
                  </h3>

                  <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
                    Deterministic quality assessment, severity classification,
                    and explainable recommendations to improve dataset reliability.
                  </p>
                </div>

                {/* Quality Assessment Error */}
                {qualityError && (
                  <div
                    role="alert"
                    className="rounded-xl border border-red-500/40 bg-red-500/5 p-5"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-600 dark:text-red-400">
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          className="h-5 w-5"
                          aria-hidden="true"
                        >
                          <path
                            d="M12 9v4m0 4h.01M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3l-7.5-13.1a2 2 0 0 0-3.4 0Z"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </div>

                      <div>
                        <p className="font-semibold text-red-700 dark:text-red-300">
                          Quality assessment unavailable
                        </p>

                        <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
                          {qualityError}
                        </p>

                        <p className="mt-2 text-xs leading-5 text-[var(--foreground-secondary)]">
                          Dataset profiling succeeded. You can continue reviewing
                          your dataset profile while investigating the quality
                          assessment issue.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Quality Assessment Loading */}
                {!quality && !qualityError && loading && (
                  <div
                    role="status"
                    className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-5"
                  >
                    <p className="font-medium text-cyan-700 dark:text-cyan-300">
                      Assessing dataset quality...
                    </p>

                    <p className="mt-2 text-sm text-[var(--foreground-secondary)]">
                      Running deterministic quality checks and evaluating
                      potential data-quality issues.
                    </p>
                  </div>
                )}

                {/* Quality Assessment Results */}
                {quality && (
                  <div className="space-y-5">

                    {/* Quality Score and Severity Breakdown */}
                    <div className="grid gap-5 lg:grid-cols-[1fr_2fr]">

                      {/* Overall Quality Score */}
                      <div className="glass-panel rounded-2xl border border-[var(--border)] p-6 transition-colors duration-200">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium text-[var(--foreground-secondary)]">
                            Overall Quality Score
                          </p>

                          <span className="rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] px-2.5 py-1 text-xs font-semibold text-[var(--foreground-secondary)]">
                            Quality Index
                          </span>
                        </div>

                        <div className="mt-5 flex items-end gap-2">
                          <span className="text-5xl font-bold tracking-tight">
                            {quality.overall_score}
                          </span>

                          <span className="pb-1.5 text-lg text-[var(--foreground-secondary)]">
                            / 100
                          </span>
                        </div>

                        <div
                          className="mt-5 h-2.5 overflow-hidden rounded-full bg-[var(--border)]"
                          role="progressbar"
                          aria-label="Overall dataset quality score"
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={quality.overall_score}
                        >
                          <div
                            className="h-full rounded-full bg-cyan-500 transition-all duration-500 dark:bg-cyan-400"
                            style={{
                              width: `${Math.min(
                                100,
                                Math.max(0, quality.overall_score)
                              )}%`,
                            }}
                          />
                        </div>

                        <div className="mt-4">
                          <span
                            className={`inline-flex rounded-full border px-3 py-1.5 text-sm font-semibold ${getStatusStyle(
                              quality.quality_status
                            )}`}
                          >
                            {quality.quality_status}
                          </span>
                        </div>

                        <div className="mt-5 border-t border-[var(--border)] pt-4">
                          <p className="text-sm leading-6 text-[var(--foreground-secondary)]">
                            The quality score reflects issues identified by the
                            current deterministic assessment rules. No changes
                            are made to your original dataset during this process.
                          </p>
                        </div>
                      </div>

                      {/* Issue Breakdown */}
                      <div className="glass-panel rounded-2xl border border-[var(--border)] p-6 transition-colors duration-200">
                        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                          <div>
                            <h4 className="font-semibold">
                              Issue Breakdown
                            </h4>

                            <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
                              Distribution of detected data-quality issues.
                            </p>
                          </div>

                          <span className="inline-flex w-fit rounded-full border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground-secondary)]">
                            {quality.summary.total_issues} Total Issues
                          </span>
                        </div>

                        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                          {[
                            {
                              label: "Critical",
                              count: quality.summary.critical,
                              style:
                                "border-red-500/40 bg-red-500/5 text-red-700 dark:text-red-300",
                            },
                            {
                              label: "High",
                              count: quality.summary.high,
                              style:
                                "border-orange-500/40 bg-orange-500/5 text-orange-800 dark:text-orange-300",
                            },
                            {
                              label: "Medium",
                              count: quality.summary.medium,
                              style:
                                "border-yellow-500/40 bg-yellow-500/5 text-yellow-800 dark:text-yellow-300",
                            },
                            {
                              label: "Low",
                              count: quality.summary.low,
                              style:
                                "border-blue-500/40 bg-blue-500/5 text-blue-700 dark:text-blue-300",
                            },
                          ].map((item) => (
                            <div
                              key={item.label}
                              className={`rounded-xl border p-4 transition-colors duration-200 ${item.style}`}
                            >
                              <p className="text-sm font-medium">
                                {item.label}
                              </p>

                              <p className="mt-2 text-2xl font-bold">
                                {item.count}
                              </p>

                              <p className="mt-1 text-xs opacity-75">
                                Detected
                              </p>
                            </div>
                          ))}
                        </div>

                        <div className="mt-5 border-t border-[var(--border)] pt-4">
                          <p className="text-xs leading-5 text-[var(--foreground-secondary)]">
                            Severity indicates the relative priority of each
                            finding. All severity levels, including low, are
                            retained and shown in the quality findings below.
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Actionable Quality Issues */}
                    {(() => {
                      const visibleIssues = getQualityIssuesForDisplay(
                        quality.issues
                      );
                      const displayedIssueCount = visibleIssues.length;

                      return (
                        <div className="quality-findings-panel rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-3.5 shadow-sm transition-colors duration-200 sm:p-4">
                          <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                            <div>
                              <h4 className="text-base font-bold tracking-tight">
                                Quality Findings &amp; Recommended Actions
                              </h4>

                              <p className="mt-1 text-xs leading-5 text-[var(--foreground-secondary)]">
                                Prioritized findings with affected-row impact and clear next steps. All detected severity levels are retained.
                              </p>
                            </div>

                            <span className="inline-flex w-fit shrink-0 rounded-full border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground-secondary)]">
                              {displayedIssueCount} Quality{" "}
                              {displayedIssueCount === 1 ? "Finding" : "Findings"}
                            </span>
                          </div>

                          {visibleIssues.length === 0 ? (
                            <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-6">
                              <p className="font-semibold text-emerald-700 dark:text-emerald-300">
                                No quality issues detected
                              </p>

                              <p className="mt-2 text-sm leading-6 text-[var(--foreground-secondary)]">
                                The quality assessment did not identify any
                                findings across the supported severity levels.
                              </p>
                            </div>
                          ) : (
                            <div className="quality-findings-grid grid grid-cols-1 items-stretch gap-3 lg:grid-cols-2">
                              {visibleIssues.map((issue, index) => (
                                <QualityIssueCard
                                  key={`${issue.issue_type}-${issue.column ?? "dataset"}-${index}`}
                                  issue={issue}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                )}
              </section>
            {/* 4. Intelligent Data Cleaning */}
            <section
              id="data-cleaning"
              className="scroll-mt-28"
              aria-labelledby="data-cleaning-heading"
            >
              <div className="mb-5">
                <h3
                  id="data-cleaning-heading"
                  className="text-xl font-semibold"
                >
                  Intelligent Data Cleaning
                </h3>

                <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--foreground-secondary)]">
                  Review cleaning operations, generate before-and-after
                  previews, approve your cleaning plan, and execute changes
                  without modifying your original dataset.
                </p>
              </div>

              <CleaningPanel
                  datasetId={profile.dataset_id}
                  columns={profile.columns_profile}
                  onCleaningComplete={handleCleaningComplete}
                />
            </section>

            {/* AI Business Analysis Planner — its own navigation destination. */}
            <section
              id="analysis-planner"
              aria-labelledby="analysis-planner-heading"
              className="glass-panel-elevated scroll-mt-28 rounded-2xl border border-[var(--border)] p-5 sm:p-7"
            >
              <div className="mb-6">
                <h3
                  id="analysis-planner-heading"
                  className="mt-2 scroll-mt-32 text-2xl font-semibold"
                >
                  Business Analysis Planner
                </h3>

                <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--foreground-secondary)]">
                  Describe the business outcome you want to investigate.
                  InsightForge AI will inspect the available columns and
                  recommend relevant KPIs and analytical methods.
                </p>
              </div>

              <form
                onSubmit={handleCreateAIBusinessAnalysis}
                className="space-y-6"
              >
                <div>
                  <label
                    htmlFor="business-objective"
                    className="mb-2 block text-sm font-semibold"
                  >
                    Business objective
                    <span className="ml-1 text-red-500">*</span>
                  </label>

                  <textarea
                    id="business-objective"
                    value={businessObjective}
                    onChange={(event) =>
                      setBusinessObjective(event.target.value)
                    }
                    minLength={5}
                    maxLength={1000}
                    required
                    rows={3}
                    placeholder="Example: Analyze monthly sales and profit performance."
                    className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] px-4 py-3 text-sm outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
                  />

                  <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                    {businessObjective.length}/1000 characters. Minimum 5.
                  </p>
                </div>

                <div>
                  <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                    <div>
                      <h4 className="text-sm font-semibold">
                        Business questions
                      </h4>

                      <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
                        Optional. Add up to 20 questions you want to investigate.
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={addBusinessQuestion}
                      disabled={aiPlanning || businessQuestions.length >= 20}
                      className="w-fit rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-medium transition hover:border-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      + Add question
                    </button>
                  </div>

                  <div className="space-y-3">
                    {businessQuestions.map((question, index) => (
                      <div
                        key={index}
                        className="flex items-start gap-2"
                      >
                        <label
                          htmlFor={`business-question-${index}`}
                          className="sr-only"
                        >
                          Business question {index + 1}
                        </label>

                        <input
                          id={`business-question-${index}`}
                          type="text"
                          maxLength={1000}
                          value={question}
                          onChange={(event) =>
                            updateBusinessQuestion(index, event.target.value)
                          }
                          disabled={aiPlanning}
                          placeholder={`Question ${index + 1}, e.g. Which region generates the most sales?`}
                          className="min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-2.5 text-sm outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
                        />

                        {businessQuestions.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeBusinessQuestion(index)}
                            disabled={aiPlanning}
                            aria-label={`Remove business question ${index + 1}`}
                            className="rounded-lg border border-[var(--border)] px-3 py-2.5 text-sm transition hover:border-red-500 hover:text-red-600 disabled:opacity-50"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {planningError && (
                  <div
                    role="alert"
                    className="rounded-xl border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-300"
                  >
                    <p className="font-semibold">
                      Unable to generate AI business analysis
                    </p>
                    <p className="mt-1">{planningError}</p>
                  </div>
                )}

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="max-w-xl text-xs leading-5 text-[var(--foreground-secondary)]">
                    InsightForge AI uses your dataset structure and business context to prepare an AI-assisted analysis brief. Recommendations are guidance; calculations run only when you execute an analysis.
                  </p>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <button
                      type="submit"
                      disabled={aiPlanning || loading || !businessObjective.trim()}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-500/10 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {aiPlanning ? (
                        <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> AI is analyzing...</>
                      ) : (
                        <><span aria-hidden="true">✦</span> Generate AI Business Analysis</>
                      )}
                    </button>
                    {aiPlanning && (
                      <button type="button" onClick={handleCancelAIPlanning} className="rounded-lg border border-red-500/50 px-4 py-3 text-sm font-semibold text-red-600 transition hover:bg-red-500/10 dark:text-red-300">
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              </form>



              {aiAnalysis && (
                <section className="mt-8 space-y-5 border-t border-[var(--border)] pt-8">

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h4 className="text-xl font-semibold">
                        AI Business Analyst Results
                      </h4>

                      <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
                        AI-generated business intelligence grounded in the columns and records available in your dataset.
                      </p>
                    </div>

                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                      ✦ AI Assisted
                    </span>
                  </div>

                  <article className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-cyan-700 dark:text-cyan-300">
                      Refined Business Objective
                    </p>

                    <p className="mt-3 text-base font-medium leading-7">
                      {aiAnalysis.refined_objective}
                    </p>
                  </article>

                  <div className="grid gap-5 lg:grid-cols-2">

                    <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5">
                      <h5 className="font-semibold">
                        Generated Business Questions
                      </h5>

                      <ol className="mt-4 space-y-3">
                        {aiAnalysis.business_questions.map((question, index) => (
                          <li
                            key={index}
                            className="flex gap-3 text-sm leading-6"
                          >
                            <span className="font-semibold text-cyan-600 dark:text-cyan-400">
                              {index + 1}.
                            </span>

                            <span>{question}</span>
                          </li>
                        ))}
                      </ol>
                    </article>

                    <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5">
                      <h5 className="font-semibold">
                        AI Reasoning Summary
                      </h5>

                      <p className="mt-3 text-sm leading-7 text-[var(--foreground-secondary)]">
                        {aiAnalysis.reasoning_summary}
                      </p>
                    </article>

                  </div>

                  <article className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-5">
                    <h5 className="font-semibold">
                      Recommended Business Focus Areas
                    </h5>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      {aiAnalysis.recommended_focus_areas.map((area, index) => (
                        <div
                          key={index}
                          className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm font-medium"
                        >
                          <span className="mr-2 text-cyan-600 dark:text-cyan-400">
                            {String(index + 1).padStart(2, "0")}
                          </span>

                          {area}
                        </div>
                      ))}
                    </div>
                  </article>

                  {aiAnalysis.clarifying_questions.length > 0 && (
                    <article className="rounded-xl border border-orange-500/30 bg-orange-500/5 p-5">
                      <h5 className="font-semibold">
                        Additional Business Clarifications
                      </h5>

                      <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
                        Questions that could improve the accuracy and relevance
                        of your analysis.
                      </p>

                      <ul className="mt-4 space-y-3">
                        {aiAnalysis.clarifying_questions.map((question, index) => (
                          <li
                            key={index}
                            className="flex gap-3 text-sm leading-6"
                          >
                            <span className="text-orange-600 dark:text-orange-400">
                              ?
                            </span>

                            {question}
                          </li>
                        ))}
                      </ul>
                    </article>
                  )}
                  <div className="mt-5 flex justify-end">
                    <button type="button" onClick={handleSaveAIPlan} disabled={!aiAnalysis || savingAIPlan || aiPlanSaved} className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-sm font-semibold text-emerald-700 disabled:opacity-50 dark:text-emerald-300">
                      {savingAIPlan ? "Saving..." : aiPlanSaved ? "✓ AI Plan Saved" : "Save AI Plan"}
                    </button>
                  </div>
                </section>
              )}

              {aiAnalysis && analysisPlan && (
                <div className="mt-8 border-t border-[var(--border)] pt-8">
                  <div className="mb-6">
                    <h4 className="text-xl font-semibold">
                      AI-Recommended Analysis Framework
                    </h4>

                    <p className="mt-2 text-sm text-[var(--foreground-secondary)]">
                      Recommendations for: {analysisPlan.business_objective}
                    </p>
                  </div>

                  <AnalysisPlanResults
                    plan={analysisPlan}
                    onConfigureAnalysis={handleConfigureAnalysis}
                  />

                </div>
              )}
            </section>

            {/* Analysis execution is kept independent from business planning. */}
            <section
              id="analytics-execution-panel"
              className="glass-panel-elevated scroll-mt-28 rounded-2xl border border-[var(--border)] p-5 sm:p-7"
              aria-label="Execute analysis"
            >
              <AnalyticsExecutionPanel
                profile={profile}
                requestedAnalysis={requestedAnalysis}
              />

              <div className="mt-8 border-t border-[var(--border)] pt-6">
                <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
                  <div>
                    <h4 className="text-lg font-semibold">Saved Business Intelligence Report</h4>
                    <p className="mt-1 text-sm text-[var(--foreground-secondary)]">Only explicitly saved analyses, AI business plans and interpretations are included.</p>
                  </div>
                  <button type="button" onClick={handleDownloadSavedReport} disabled={downloadingReport || !profile} className="inline-flex items-center justify-center rounded-lg bg-cyan-500 px-5 py-3 text-sm font-semibold text-slate-950 disabled:opacity-50">
                    {downloadingReport ? "Generating PDF..." : "↓ Download PDF Report"}
                  </button>
                </div>
                {reportDownloadError && <p role="alert" className="mt-3 text-sm text-red-600">{reportDownloadError}</p>}
              </div>
            </section>

            {/* 6. Column Intelligence */}
            <section id="column-intelligence" className="scroll-mt-28">
              <div className="mb-4">
                <h3 className="text-xl font-semibold">
                  Column Intelligence
                </h3>

                <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
                  Column types, semantic roles, missing values, uniqueness,
                  and value ranges.
                </p>
              </div>

              <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[800px] text-left text-sm">
                    <thead className="bg-[var(--surface-secondary)] text-[var(--foreground-secondary)]">
                      <tr>
                        <th className="px-5 py-3">Column</th>
                        <th className="px-5 py-3">Type</th>
                        <th className="px-5 py-3">Semantic role</th>
                        <th className="px-5 py-3">Nulls</th>
                        <th className="px-5 py-3">Unique</th>
                        <th className="px-5 py-3">Range</th>
                      </tr>
                    </thead>

                    <tbody>
                      {profile.columns_profile.map((column) => (
                        <tr
                          key={column.name}
                          className="border-t border-[var(--border)]"
                        >
                          <td className="px-5 py-4 font-medium">
                            {column.name}
                          </td>

                          <td className="px-5 py-4 font-mono text-xs text-[var(--foreground-secondary)]">
                            {column.dtype}
                          </td>

                          <td className="px-5 py-4">
                            <span className="rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-700 dark:text-cyan-300">
                              {column.semantic_role}
                            </span>
                          </td>

                          <td className="px-5 py-4">
                            {column.null_count.toLocaleString()}
                          </td>

                          <td className="px-5 py-4">
                            {column.unique_count.toLocaleString()}
                          </td>

                          <td className="px-5 py-4 text-[var(--foreground-secondary)]">
                            {column.min_value ?? "-"} -{" "}
                            {column.max_value ?? "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </section>
        )}
      </div>

      {/* Refresh confirmation dialog */}
      {refreshDialogOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              !refreshingWorkspace
            ) {
              cancelWorkspaceRefresh();
            }
          }}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="refresh-dialog-title"
            aria-describedby="refresh-dialog-description"
            className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 text-[var(--foreground)] shadow-2xl sm:p-7"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-orange-500/30 bg-orange-500/10 text-orange-600 dark:text-orange-400">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                className="h-6 w-6"
                aria-hidden="true"
              >
                <path
                  d="M20 7v5h-5M4 17v-5h5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M5.6 9A7 7 0 0 1 17.4 6L20 12M4 12l2.6 6A7 7 0 0 0 18.4 15"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <h2
              id="refresh-dialog-title"
              className="mt-5 text-xl font-bold tracking-tight"
            >
              Refresh InsightForge AI?
            </h2>

            <p
              id="refresh-dialog-description"
              className="mt-3 text-sm leading-6 text-[var(--foreground-secondary)]"
            >
              This will clear the currently active dataset session and reset
              the workspace. Your uploaded dataset file will not be deleted
              from your computer, and the backend dataset will not be deleted.
              You will need to upload the dataset again to continue your
              analysis.
            </p>

            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                ref={refreshCancelButtonRef}
                type="button"
                onClick={cancelWorkspaceRefresh}
                disabled={refreshingWorkspace}
                className="inline-flex items-center justify-center rounded-xl border border-[var(--border)] px-4 py-3 text-sm font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={confirmWorkspaceRefresh}
                disabled={refreshingWorkspace}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-orange-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-orange-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {refreshingWorkspace && (
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <circle
                      cx="12"
                      cy="12"
                      r="9"
                      stroke="currentColor"
                      strokeWidth="3"
                      className="opacity-25"
                    />
                    <path
                      d="M21 12a9 9 0 0 0-9-9"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      className="opacity-90"
                    />
                  </svg>
                )}

                {refreshingWorkspace
                  ? "Resetting workspace..."
                  : "Refresh & Clear Data"}
              </button>
            </div>

            <p className="mt-4 text-xs text-[var(--foreground-secondary)]">
              Press Escape or select Cancel to keep your current dataset.
            </p>
          </section>
        </div>
      )}
    </main>
    </>
  );
}
