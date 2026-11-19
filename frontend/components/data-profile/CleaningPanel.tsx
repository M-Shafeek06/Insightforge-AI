"use client";

import { useEffect, useMemo, useState } from "react";

import {
  approveCleaningPlan,
  executeCleaningPlan,
  generateCleaningPreview,
  type CleaningOperation,
  type CleaningOperationType,
  type CleaningPreview,
  type CleaningExecution,
} from "@/lib/api/cleaning";

import type { ColumnProfile } from "@/lib/api/datasets";

type Props = {
  datasetId: string;
  columns: ColumnProfile[];
  onCleaningComplete?: (result: CleaningExecution) => void;
};

type MissingStrategy =
  | "mean"
  | "median"
  | "mode"
  | "constant"
  | "drop_rows";

const operationOptions: {
  value: CleaningOperationType;
  label: string;
  description: string;
  requiresColumn: boolean;
}[] = [
  {
    value: "drop_duplicates",
    label: "Remove duplicate rows",
    description: "Remove duplicate records from the dataset.",
    requiresColumn: false,
  },
  {
    value: "drop_column",
    label: "Drop columns",
    description: "Remove one or more unnecessary columns from the dataset.",
    requiresColumn: false,
  },
  {
    value: "fill_missing",
    label: "Handle missing values",
    description: "Replace or remove missing values in a column.",
    requiresColumn: true,
  },
  {
    value: "trim_whitespace",
    label: "Trim whitespace",
    description: "Remove unnecessary leading and trailing spaces.",
    requiresColumn: true,
  },
  {
    value: "standardize_text",
    label: "Standardize text",
    description: "Convert a column into a consistent case.",
    requiresColumn: true,
  },
  {
    value: "convert_numeric",
    label: "Convert to numeric",
    description: "Convert numeric-looking text into numeric values.",
    requiresColumn: true,
  },
  {
    value: "convert_datetime",
    label: "Convert to datetime",
    description: "Convert date-like text into datetime values; unparseable non-empty values become NULL after preview and approval.",
    requiresColumn: true,
  },
];

const IDENTIFIER_PATTERN =
  /(^|[\_\W])(id|identifier|code|postal|postcode|zip|phone|mobile|account|ssn|sku)([\_\W]|$)/i;

function normalizedRole(column: ColumnProfile): string {
  return (column.semantic_role ?? "").trim().toLowerCase();
}

function isNumericColumn(column: ColumnProfile): boolean {
  return /^(u?int|float|double|decimal|number)/i.test(
    column.dtype.trim()
  );
}

function isTextColumn(column: ColumnProfile): boolean {
  return /^(object|string|str|category)/i.test(
    column.dtype.trim()
  );
}

function isBooleanColumn(column: ColumnProfile): boolean {
  return /^(bool|boolean)/i.test(column.dtype.trim());
}

function isDateColumn(column: ColumnProfile): boolean {
  const dtype = column.dtype.trim().toLowerCase();
  const role = normalizedRole(column);

  return (
    /datetime|timestamp|date/.test(dtype) ||
    /date|datetime|timestamp|time/.test(role)
  );
}

function isIdentifierColumn(column: ColumnProfile): boolean {
  const role = normalizedRole(column);

  return (
    IDENTIFIER_PATTERN.test(column.name.replace(/ /g, "_")) ||
    /identifier|primary_key|foreign_key/.test(role)
  );
}

function isNumericLooking(value: string | number | null): boolean {
  if (value === null || value === undefined || value === "") {
    return false;
  }

  if (typeof value === "number") {
    return Number.isFinite(value);
  }

  const normalized = value.replace(/,/g, "").trim();

  if (!normalized) return false;

  return (
    /^[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?$/i.test(normalized) &&
    Number.isFinite(Number(normalized))
  );
}

function isDateLooking(value: string | number | null): boolean {
  if (
    value === null ||
    value === undefined ||
    typeof value !== "string"
  ) {
    return false;
  }

  const normalized = value.trim();

  if (!normalized || /^\d+(\.\d+)?$/.test(normalized)) {
    return false;
  }

  // Avoid treating ambiguous numeric dates such as 01/02/2026 as safe.
  const ambiguous = normalized.match(
    /^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/
  );

  if (ambiguous) {
    const first = Number(ambiguous[1]);
    const second = Number(ambiguous[2]);

    if (
      first >= 1 &&
      first <= 12 &&
      second >= 1 &&
      second <= 12 &&
      first !== second
    ) {
      return false;
    }
  }

  const hasDateIndicator =
    /[-/T:]/.test(normalized) ||
    /[a-zA-Z]/.test(normalized);

  return hasDateIndicator && !Number.isNaN(Date.parse(normalized));
}

function isNumericCandidate(column: ColumnProfile): boolean {
  if (!isTextColumn(column) || isIdentifierColumn(column)) {
    return false;
  }

  const role = normalizedRole(column);

  if (
    /numeric|number|measure|quantity|amount|currency|percentage|metric/.test(
      role
    )
  ) {
    return true;
  }

  return (
    isNumericLooking(column.min_value) &&
    isNumericLooking(column.max_value)
  );
}

function isDatetimeCandidate(column: ColumnProfile): boolean {
  if (!isTextColumn(column) || isIdentifierColumn(column)) {
    return false;
  }

  const role = normalizedRole(column);

  // Recognise the semantic roles produced by the backend profiler.
  if (/date|datetime|timestamp|time/.test(role)) {
    return true;
  }

  return (
    isDateLooking(column.min_value) &&
    isDateLooking(column.max_value)
  );
}

function getConstantValue(
  value: string,
  column: ColumnProfile | undefined
): string | number | boolean | null {
  if (!column) return value;

  if (isNumericColumn(column)) {
    if (value.trim() === "") return null;

    const numericValue = Number(value);

    return Number.isFinite(numericValue) ? numericValue : null;
  }

  if (isBooleanColumn(column)) {
    const normalized = value.trim().toLowerCase();

    if (normalized === "true") return true;
    if (normalized === "false") return false;

    return null;
  }

  return value;
}

export default function CleaningPanel({
  datasetId,
  columns,
  onCleaningComplete,
}: Props) {
  const [operationType, setOperationType] =
    useState<CleaningOperationType>("fill_missing");

  const [column, setColumn] = useState("");

  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);

  const [strategy, setStrategy] =
    useState<MissingStrategy>("median");

  const [constantValue, setConstantValue] = useState("0");

  const [textCase, setTextCase] = useState<
    "lower" | "upper" | "title"
  >("lower");

  const [operations, setOperations] =
    useState<CleaningOperation[]>([]);

  const [preview, setPreview] =
    useState<CleaningPreview | null>(null);

  const [previewDatasetId, setPreviewDatasetId] =
    useState<string | null>(null);

  const [execution, setExecution] =
    useState<CleaningExecution | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [previewCopied, setPreviewCopied] = useState(false);

  const selectedOperation = operationOptions.find(
    (item) => item.value === operationType
  );

  const previewJson = useMemo(
    () => (preview ? JSON.stringify(preview, null, 2) : ""),
    [preview]
  );

  async function handleCopyPreview() {
    if (!previewJson) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(previewJson);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = previewJson;
        textArea.setAttribute("readonly", "");
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.select();
        const copied = document.execCommand("copy");
        document.body.removeChild(textArea);
        if (!copied) throw new Error("Clipboard copy is unavailable.");
      }

      setPreviewCopied(true);
      window.setTimeout(() => setPreviewCopied(false), 2000);
    } catch {
      setPreviewCopied(false);
      setError("Unable to copy the cleaning preview. Please select and copy the JSON manually.");
    }
  }

  const columnsWithMissingValues = useMemo(
    () => columns.filter((item) => item.null_count > 0),
    [columns]
  );

  // Determine eligible columns for the selected operation.
  const availableColumns = useMemo(() => {
    switch (operationType) {
      case "fill_missing": {
        const missing = columnsWithMissingValues;

        if (strategy === "mean" || strategy === "median") {
          return missing.filter(isNumericColumn);
        }

        if (strategy === "constant") {
          return missing.filter(
            (item) =>
              isTextColumn(item) ||
              isNumericColumn(item) ||
              isBooleanColumn(item)
          );
        }

        return missing;
      }

      case "trim_whitespace":
        return columns.filter(isTextColumn);

      case "standardize_text":
        return columns.filter(
          (item) =>
            isTextColumn(item) && !isIdentifierColumn(item)
        );

      case "convert_numeric":
        return columns.filter(isNumericCandidate);

      case "convert_datetime":
        return columns.filter(isDatetimeCandidate);

      default:
        return columns;
    }
  }, [
    columns,
    columnsWithMissingValues,
    operationType,
    strategy,
  ]);

  const autoDateColumns = useMemo(
    () =>
      columns.filter(
        (item) =>
          isDatetimeCandidate(item) &&
          !operations.some(
            (operation) =>
              operation.type === "convert_datetime" &&
              operation.column === item.name
          )
      ),
    [columns, operations]
  );

  function addAutomaticDateCleaning() {
    if (autoDateColumns.length === 0) return;

    const dateOperations: CleaningOperation[] = autoDateColumns.map(
      (item) => ({
        type: "convert_datetime",
        column: item.name,
      })
    );

    setOperations((current) => [...current, ...dateOperations]);
    setPreview(null);
    setPreviewDatasetId(null);
    setExecution(null);
    setError("");
  }

  const selectedColumnProfile = columns.find(
    (item) => item.name === column
  );

  const constantTypedValue = getConstantValue(
    constantValue,
    selectedColumnProfile
  );

  const invalidConstant =
    operationType === "fill_missing" &&
    strategy === "constant" &&
    selectedOperation?.requiresColumn === true &&
    column !== "" &&
    constantTypedValue === null;

  // Keep the selected column valid.
  useEffect(() => {
    if (availableColumns.length === 0) {
      setColumn("");
      return;
    }

    const selectedColumnExists = availableColumns.some(
      (item) => item.name === column
    );

    if (!selectedColumnExists) {
      setColumn(availableColumns[0].name);
    }
  }, [availableColumns, column]);

  // Reset pending state when the selected dataset changes.
  const columnsKey = columns
    .map(
      (item) =>
        `${item.name}:${item.dtype}:${item.null_count}:${item.semantic_role}`
    )
    .join("|");

  useEffect(() => {
    setOperations([]);
    setSelectedColumns([]);
    setPreview(null);
    setPreviewDatasetId(null);
    setExecution(null);
    setError("");
  }, [datasetId, columnsKey]);

  // Identify columns already scheduled for removal.
  const columnsAlreadyScheduledForRemoval = useMemo(() => {
    const scheduled = operations
      .filter((operation) => operation.type === "drop_column")
      .flatMap((operation) => operation.columns ?? []);

    return new Set(scheduled);
  }, [operations]);

  // Prevent removing every column across multiple operations.
  const remainingColumnCount = useMemo(() => {
    const removedCount = columnsAlreadyScheduledForRemoval.size;

    return columns.length - removedCount;
  }, [columns.length, columnsAlreadyScheduledForRemoval]);

  const invalidDropSelection =
    operationType === "drop_column" &&
    (
      selectedColumns.length === 0 ||
      selectedColumns.some((name) =>
        columnsAlreadyScheduledForRemoval.has(name)
      ) ||
      new Set([
        ...columnsAlreadyScheduledForRemoval,
        ...selectedColumns,
      ]).size >= columns.length
    );

  function addOperation() {
    // Drop Column has its own multi-column handling.
    if (operationType === "drop_column") {
      if (selectedColumns.length === 0) {
        setError("Select at least one column to remove.");
        return;
      }

      if (
        selectedColumns.some((name) =>
          columnsAlreadyScheduledForRemoval.has(name)
        )
      ) {
        setError(
          "One or more selected columns are already scheduled for removal."
        );
        return;
      }

      const totalScheduledForRemoval = new Set([
        ...columnsAlreadyScheduledForRemoval,
        ...selectedColumns,
      ]);

      if (totalScheduledForRemoval.size >= columns.length) {
        setError(
          "You cannot remove every column from the dataset."
        );
        return;
      }

      const normalizedColumns = [...selectedColumns].sort();
      const duplicateDropOperation = operations.some(
        (existing) =>
          existing.type === "drop_column" &&
          [...(existing.columns ?? [])].sort().join("|") ===
            normalizedColumns.join("|")
      );

      if (duplicateDropOperation) {
        setError("This exact column-removal action is already in your cleaning plan.");
        return;
      }

      const operation: CleaningOperation = {
        type: "drop_column",
        columns: [...selectedColumns],
      };

      setOperations((current) => [...current, operation]);

      setSelectedColumns([]);
      setPreview(null);
      setPreviewDatasetId(null);
      setExecution(null);
      setError("");

      return;
    }

    if (selectedOperation?.requiresColumn && !column) {
      setError("No eligible column is available for this operation.");
      return;
    }

    if (
      selectedOperation?.requiresColumn &&
      !availableColumns.some((item) => item.name === column)
    ) {
      setError(
        "This column is not eligible for the selected operation."
      );
      return;
    }

    if (invalidConstant) {
      setError(
        "Enter a valid constant value compatible with the selected column."
      );
      return;
    }

    const operation: CleaningOperation = {
      type: operationType,
    };

    if (selectedOperation?.requiresColumn) {
      operation.column = column;
    }

    if (operationType === "fill_missing") {
      operation.strategy = strategy;

      if (strategy === "constant") {
        operation.value = constantTypedValue;
      }
    }

    if (operationType === "standardize_text") {
      operation.case = textCase;
    }

    const duplicateOperation = operations.some((existing) =>
      existing.type === operation.type &&
      (existing.column ?? "") === (operation.column ?? "") &&
      (existing.strategy ?? "") === (operation.strategy ?? "") &&
      JSON.stringify(existing.value ?? null) ===
        JSON.stringify(operation.value ?? null) &&
      (existing.case ?? "") === (operation.case ?? "")
    );

    if (duplicateOperation) {
      setError("This exact cleaning action is already in your plan. Add a different action or change its column or settings.");
      return;
    }

    setOperations((current) => [...current, operation]);

    setPreview(null);
    setPreviewDatasetId(null);
    setExecution(null);
    setError("");
  }

  function removeOperation(index: number) {
    setOperations((current) =>
      current.filter((_, currentIndex) => currentIndex !== index)
    );

    setPreview(null);
    setPreviewDatasetId(null);
    setExecution(null);
    setError("");
  }

  async function handlePreview() {
    if (operations.length === 0) {
      setError("Add at least one cleaning operation.");
      return;
    }

    const sourceDatasetId = datasetId;

    try {
      setLoading(true);
      setError("");
      setPreview(null);
      setPreviewDatasetId(null);
      setExecution(null);

      const result = await generateCleaningPreview(
        sourceDatasetId,
        operations
      );

      if (sourceDatasetId !== datasetId) {
        return;
      }

      setPreview(result);
      setPreviewDatasetId(sourceDatasetId);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Preview generation failed."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleApproveAndExecute() {
    if (!preview?.plan_id || !previewDatasetId) {
      setError("Generate a valid cleaning preview first.");
      return;
    }

    if (previewDatasetId !== datasetId) {
      setError(
        "The selected dataset version has changed. Generate a new preview."
      );

      setPreview(null);
      setPreviewDatasetId(null);
      return;
    }

    const confirmed = window.confirm(
      "Approve and execute these cleaning operations? " +
        "The original dataset will remain unchanged."
    );

    if (!confirmed) return;

    const sourceDatasetId = previewDatasetId;
    const planId = preview.plan_id;

    try {
      setLoading(true);
      setError("");

      await approveCleaningPlan(sourceDatasetId, planId);

      const result = await executeCleaningPlan(
        sourceDatasetId,
        planId
      );

      setExecution(result);

      setPreview(null);
      setPreviewDatasetId(null);

      onCleaningComplete?.(result);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Cleaning execution failed."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      id="data-cleaning"
      className="glass-panel-elevated space-y-6 rounded-2xl border border-[var(--border)] p-5 transition-colors duration-200 sm:p-7"
    >
      {/* Header */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-cyan-500" />
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700 dark:text-cyan-400">
              Data preparation
            </p>
          </div>

          <h2 className="mt-2 text-xl font-semibold tracking-tight text-[var(--foreground)]">
            Intelligent Data Cleaning
          </h2>

          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--foreground-secondary)]">
            Configure cleaning operations, inspect the before-and-after
            preview, and approve the changes. Your original dataset remains
            untouched.
          </p>
        </div>

        <span className="inline-flex w-fit shrink-0 items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Original protected
        </span>
      </div>

      {autoDateColumns.length > 0 && (
        <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4 sm:p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <h3 className="font-semibold text-[var(--foreground)]">
                Automatic date detection
              </h3>
              <p className="mt-1 text-sm leading-6 text-[var(--foreground-secondary)]">
                Detected {autoDateColumns.length} date-like text column
                {autoDateColumns.length === 1 ? "" : "s"}:{" "}
                {autoDateColumns.map((item) => item.name).join(", ")}.
                Invalid non-empty date values will be set to NULL in the
                proposed cleaned version; other columns will remain unchanged.
              </p>
            </div>
            <button
              type="button"
              onClick={addAutomaticDateCleaning}
              className="inline-flex shrink-0 items-center justify-center rounded-lg bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
            >
              Add automatic date cleaning
            </button>
          </div>
        </div>
      )}

      {/* Operation configuration */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-4 sm:p-5">
        <div className="mb-5">
          <h3 className="text-sm font-semibold text-[var(--foreground)]">
            Configure operation
          </h3>
          <p className="mt-1 text-xs leading-5 text-[var(--foreground-secondary)]">
            Choose a cleaning action and configure the columns or values it
            should affect.
          </p>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <div>
            <label
              htmlFor="cleaning-operation"
              className="mb-2 block text-sm font-semibold text-[var(--foreground)]"
            >
              Cleaning operation
            </label>

            <select
              id="cleaning-operation"
              value={operationType}
              onChange={(event) => {
                setOperationType(
                  event.target.value as CleaningOperationType
                );
                setError("");
              }}
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
            >
              {operationOptions.map((operation) => (
                <option key={operation.value} value={operation.value}>
                  {operation.label}
                </option>
              ))}
            </select>

            <p className="mt-2 text-xs leading-5 text-[var(--foreground-secondary)]">
              {selectedOperation?.description}
            </p>
          </div>

          {/* Single-column selector */}
          {selectedOperation?.requiresColumn && (
            <div>
              <label
                htmlFor="cleaning-column"
                className="mb-2 block text-sm font-semibold text-[var(--foreground)]"
              >
                Select column
              </label>

              <select
                id="cleaning-column"
                value={column}
                onChange={(event) => setColumn(event.target.value)}
                disabled={availableColumns.length === 0}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {availableColumns.length === 0 ? (
                  <option value="">No eligible columns available</option>
                ) : (
                  availableColumns.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                      {operationType === "fill_missing"
                        ? ` (${item.null_count} missing)`
                        : ""}
                    </option>
                  ))
                )}
              </select>

              <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                Only compatible columns are displayed.
              </p>
            </div>
          )}

          {/* Drop-column selector */}
          {operationType === "drop_column" && (
            <div className="lg:col-span-2">
              <div className="mb-2 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                <div>
                  <label className="block text-sm font-semibold text-[var(--foreground)]">
                    Select columns to remove
                  </label>
                  <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
                    Select one or more columns. At least one column must
                    remain in the dataset.
                  </p>
                </div>

                <span className="inline-flex w-fit items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-700 dark:text-cyan-300">
                  {selectedColumns.length} selected
                </span>
              </div>

              <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
                <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface-secondary)] px-4 py-3">
                  <span className="text-xs font-semibold uppercase tracking-wide text-[var(--foreground-secondary)]">
                    Available dataset columns
                  </span>
                  <span className="text-xs text-[var(--foreground-secondary)]">
                    {remainingColumnCount} remaining
                  </span>
                </div>

                <div className="grid max-h-64 gap-1 overflow-y-auto p-2 sm:grid-cols-2">
                  {columns.map((item) => {
                    const alreadyScheduled =
                      columnsAlreadyScheduledForRemoval.has(item.name);
                    const checked = selectedColumns.includes(item.name);
                    const disabled =
                      alreadyScheduled || remainingColumnCount <= 1;

                    return (
                      <label
                        key={item.name}
                        className={`flex min-w-0 items-center gap-3 rounded-lg border px-3 py-2.5 transition ${
                          checked
                            ? "border-cyan-500/50 bg-cyan-500/10"
                            : "border-transparent hover:border-[var(--border)] hover:bg-[var(--surface-secondary)]"
                        } ${
                          disabled
                            ? "cursor-not-allowed opacity-50"
                            : "cursor-pointer"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={disabled}
                          onChange={(event) => {
                            setSelectedColumns((current) =>
                              event.target.checked
                                ? [...current, item.name]
                                : current.filter(
                                    (name) => name !== item.name
                                  )
                            );
                            setError("");
                          }}
                          className="h-4 w-4 shrink-0 accent-cyan-500 focus:ring-cyan-500"
                        />

                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-[var(--foreground)]">
                            {item.name}
                          </span>
                          <span className="mt-0.5 block text-xs text-[var(--foreground-secondary)]">
                            {item.dtype}
                            {alreadyScheduled ? " · Already scheduled" : ""}
                          </span>
                        </span>

                        {checked && (
                          <span className="shrink-0 text-xs font-semibold text-cyan-700 dark:text-cyan-300">
                            Selected
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-[var(--foreground-secondary)]">
                  {selectedColumns.length > 0
                    ? `${selectedColumns.length} column(s) will be removed in this operation.`
                    : "Choose the columns you want to remove."}
                </p>

                {selectedColumns.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setSelectedColumns([])}
                    className="text-xs font-semibold text-cyan-700 transition hover:text-cyan-600 dark:text-cyan-300"
                  >
                    Clear selection
                  </button>
                )}
              </div>

              {invalidDropSelection && selectedColumns.length > 0 && (
                <p className="mt-2 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-700 dark:text-red-300">
                  Invalid selection. At least one column must remain, and
                  columns already scheduled for removal cannot be selected
                  again.
                </p>
              )}

              {remainingColumnCount <= 1 && (
                <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  No more columns can be removed. At least one column must
                  remain in the dataset.
                </p>
              )}
            </div>
          )}

          {/* Missing-value strategy */}
          {operationType === "fill_missing" && (
            <div>
              <label
                htmlFor="missing-strategy"
                className="mb-2 block text-sm font-semibold text-[var(--foreground)]"
              >
                Missing-value strategy
              </label>

              <select
                id="missing-strategy"
                value={strategy}
                onChange={(event) => {
                  setStrategy(event.target.value as MissingStrategy);
                  setError("");
                }}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
              >
                <option value="mean">Mean</option>
                <option value="median">Median</option>
                <option value="mode">Mode</option>
                <option value="constant">Constant value</option>
                <option value="drop_rows">Drop rows</option>
              </select>

              {strategy === "constant" && (
                <input
                  value={constantValue}
                  onChange={(event) =>
                    setConstantValue(event.target.value)
                  }
                  placeholder="Replacement value"
                  aria-label="Replacement value"
                  className="mt-3 w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition placeholder:text-[var(--foreground-secondary)] focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
                />
              )}

              {strategy === "constant" && selectedColumnProfile && (
                <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                  Expected value type: {selectedColumnProfile.dtype}
                </p>
              )}

              {(strategy === "mean" || strategy === "median") && (
                <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                  Only numeric columns containing missing values are
                  available.
                </p>
              )}

              {strategy === "drop_rows" && (
                <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  Warning: This operation removes entire rows containing
                  missing values in the selected column.
                </p>
              )}
            </div>
          )}

          {/* Text standardization */}
          {operationType === "standardize_text" && (
            <div>
              <label
                htmlFor="text-case"
                className="mb-2 block text-sm font-semibold text-[var(--foreground)]"
              >
                Text format
              </label>

              <select
                id="text-case"
                value={textCase}
                onChange={(event) =>
                  setTextCase(event.target.value as typeof textCase)
                }
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
              >
                <option value="lower">Lowercase</option>
                <option value="upper">Uppercase</option>
                <option value="title">Title case</option>
              </select>

              <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                Identifier-like columns are excluded to avoid changing
                identifier values.
              </p>
            </div>
          )}

          {/* Numeric conversion information */}
          {operationType === "convert_numeric" && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm leading-6 text-amber-800 dark:text-amber-300">
              Only numeric-looking text columns are listed. Identifier-like
              columns are excluded. All values are validated again by the
              backend before conversion.
            </div>
          )}

          {/* Datetime conversion information */}
          {operationType === "convert_datetime" && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm leading-6 text-amber-800 dark:text-amber-300">
              Only date-like text columns are listed. Numeric-only and
              identifier-like columns are excluded. Ambiguous dates are
              rejected by the backend.
            </div>
          )}
        </div>
      </div>

      {/* No compatible columns warning */}
      {selectedOperation?.requiresColumn &&
        availableColumns.length === 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm leading-6 text-amber-800 dark:text-amber-300">
            No compatible columns are available for this operation.
            {operationType === "fill_missing" &&
              " Check whether the dataset contains missing values and whether the selected strategy matches the column types."}
            {operationType === "convert_numeric" &&
              " No suitable numeric-looking text columns were identified."}
            {operationType === "convert_datetime" &&
              " No suitable date-like text columns were identified."}
          </div>
        )}

      {/* Add operation */}
      <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-[var(--foreground-secondary)]">
          Build a multi-step plan with different cleaning actions. Exact duplicate actions are blocked; review or remove steps before generating the preview.
        </p>

        <button
          type="button"
          onClick={addOperation}
          disabled={
            loading ||
            (selectedOperation?.requiresColumn === true &&
              availableColumns.length === 0) ||
            (operationType === "drop_column" &&
              invalidDropSelection) ||
            invalidConstant
          }
          className="inline-flex shrink-0 items-center justify-center rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-2.5 text-sm font-semibold text-cyan-800 transition hover:border-cyan-500 hover:bg-cyan-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:cursor-not-allowed disabled:opacity-40 dark:text-cyan-300"
        >
          <span className="mr-2 text-base leading-none">+</span>
          Add operation
        </button>
      </div>

      {/* Selected operations */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-[var(--foreground)]">
              Cleaning operations
            </h3>
            <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
              {operations.length === 0
                ? "No operations added yet."
                : `${operations.length} operation(s) in your pending plan.`}
            </p>
          </div>

          <span className="rounded-full border border-[var(--border)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-semibold text-[var(--foreground-secondary)]">
            {operations.length} added
          </span>
        </div>

        {operations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface-secondary)] px-4 py-7 text-center">
            <p className="text-sm font-medium text-[var(--foreground)]">
              Your cleaning plan is empty
            </p>
            <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
              Choose an operation above and select Add operation to begin.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {operations.map((operation, index) => (
              <div
                key={`${operation.type}-${index}`}
                className="flex flex-col justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-4 sm:flex-row sm:items-center"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-xs font-bold text-cyan-700 dark:text-cyan-300">
                    {String(index + 1).padStart(2, "0")}
                  </span>

                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--foreground)]">
                      {
                        operationOptions.find(
                          (item) => item.value === operation.type
                        )?.label
                      }
                    </p>

                    <p className="mt-1 break-words text-xs leading-5 text-[var(--foreground-secondary)]">
                      {operation.columns?.join(", ") ??
                        operation.column ??
                        "Entire dataset"}
                      {operation.strategy ? ` · ${operation.strategy}` : ""}
                      {operation.case ? ` · ${operation.case}` : ""}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => removeOperation(index)}
                  className="inline-flex w-fit items-center justify-center rounded-lg border border-red-500/30 px-3 py-2 text-xs font-semibold text-red-600 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-300"
                  disabled={loading}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preview action */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] p-4 sm:flex sm:items-center sm:justify-between sm:gap-5 sm:p-5">
        <div>
          <h3 className="text-sm font-semibold text-[var(--foreground)]">
            Review cleaning changes
          </h3>
          <p className="mt-1 text-xs leading-5 text-[var(--foreground-secondary)]">
            Generate a preview before approving and executing your plan.
          </p>
        </div>

        <button
          type="button"
          onClick={handlePreview}
          disabled={loading || operations.length === 0}
          className="mt-4 inline-flex w-full items-center justify-center rounded-xl bg-cyan-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-sm transition hover:bg-cyan-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:cursor-not-allowed disabled:opacity-40 sm:mt-0 sm:w-auto"
        >
          {loading ? "Processing..." : "Generate cleaning preview"}
        </button>
      </div>

      {/* Errors */}
      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm leading-6 text-red-700 dark:text-red-300"
        >
          <p className="font-semibold">Unable to continue</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {/* Cleaning preview */}
      {preview && previewDatasetId === datasetId && (
        <div className="space-y-4 rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4 sm:p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-cyan-500" />
                <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700 dark:text-cyan-300">
                  Preview ready
                </p>
              </div>

              <h3 className="mt-2 text-lg font-semibold text-[var(--foreground)]">
                Cleaning preview generated
              </h3>

              <p className="mt-1 break-all text-xs text-[var(--foreground-secondary)]">
                Plan ID: {preview.plan_id}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex w-fit rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold capitalize text-[var(--foreground-secondary)]">
                {preview.approval_status}
              </span>
              <button
                type="button"
                onClick={handleCopyPreview}
                className="inline-flex items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40"
                aria-label="Copy cleaning preview JSON"
              >
                {previewCopied ? "✓ Copied" : "Copy JSON"}
              </button>
            </div>
          </div>

          <details className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-secondary)]">
              View complete before/after preview
            </summary>

            <pre className="max-h-96 overflow-auto border-t border-[var(--border)] bg-[var(--surface-secondary)] p-4 text-xs leading-5 text-[var(--foreground)]">
              {previewJson}
            </pre>
          </details>

          {preview.approval_status === "pending" && (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-[var(--foreground-secondary)]">
                Review the preview carefully. Execution creates a cleaned
                dataset version; the original remains unchanged.
              </p>

              <button
                type="button"
                onClick={handleApproveAndExecute}
                disabled={loading}
                className="inline-flex shrink-0 items-center justify-center rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading
                  ? "Executing..."
                  : "Approve and execute cleaning"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Execution result */}
      {execution &&
        execution.cleaned_dataset_id !== datasetId && (
          <div className="space-y-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5 text-[var(--foreground)]">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                ✓
              </span>
              <div>
                <h3 className="font-semibold text-emerald-800 dark:text-emerald-300">
                  Cleaning completed successfully
                </h3>
                <p className="mt-0.5 text-xs text-[var(--foreground-secondary)]">
                  A new cleaned dataset version has been created.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
                <p className="text-xs text-[var(--foreground-secondary)]">
                  Original rows
                </p>
                <p className="mt-1 text-2xl font-bold">
                  {execution.original_rows.toLocaleString()}
                </p>
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
                <p className="text-xs text-[var(--foreground-secondary)]">
                  Cleaned rows
                </p>
                <p className="mt-1 text-2xl font-bold">
                  {execution.cleaned_rows.toLocaleString()}
                </p>
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
                <p className="text-xs text-[var(--foreground-secondary)]">
                  Rows removed
                </p>
                <p className="mt-1 text-2xl font-bold">
                  {(
                    execution.original_rows - execution.cleaned_rows
                  ).toLocaleString()}
                </p>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
              <p className="text-xs text-[var(--foreground-secondary)]">
                Output file
              </p>
              <p className="mt-1 break-all text-sm font-medium">
                {execution.output_filename}
              </p>
              <p className="mt-2 break-all font-mono text-xs text-[var(--foreground-secondary)]">
                Dataset ID: {execution.cleaned_dataset_id}
              </p>
            </div>
          </div>
        )}
    </section>
  );
}