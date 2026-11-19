"use client";

import { useEffect, useState } from "react";

import {
  getDatasetPreview,
  getColumnUniqueValues,
  type DatasetPreviewResponse,
  type ColumnUniqueValuesResponse,
} from "@/lib/api/dataset-preview";

type DatasetViewerProps = {
  datasetId: string;
};

const PAGE_SIZE = 10;

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "NULL";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  const text = String(value);

  // Keep date-only values date-only. Do not pass them through Date(),
  // which can introduce timezone shifts in some browsers.
  const dateOnlyMatch = text.match(/^(\d{4}-\d{2}-\d{2})$/);
  if (dateOnlyMatch) {
    return dateOnlyMatch[1];
  }

  // Normalize ISO date-time strings without changing their represented
  // clock time or timezone. This avoids browser-local timezone conversion.
  const dateTimeMatch = text.match(
    /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/
  );

  if (dateTimeMatch) {
    const [, date, time, seconds, timezone] = dateTimeMatch;
    const normalizedTimezone = timezone
      ? timezone === "Z"
        ? " UTC"
        : ` ${timezone}`
      : "";

    return `${date} ${time}${seconds ? `:${seconds}` : ""}${normalizedTimezone}`;
  }

  return text;
}

export default function DatasetViewer({
  datasetId,
}: DatasetViewerProps) {
  const [data, setData] = useState<DatasetPreviewResponse | null>(null);

  const [page, setPage] = useState(1);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const [sortBy, setSortBy] = useState<string | undefined>();
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  const [uniqueColumn, setUniqueColumn] = useState<string | null>(null);
  const [uniqueValues, setUniqueValues] = useState<ColumnUniqueValuesResponse | null>(null);
  const [uniqueValuesLoading, setUniqueValuesLoading] = useState(false);
  const [uniqueValuesError, setUniqueValuesError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounced search.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);

    return () => clearTimeout(timer);
  }, [searchInput]);

  // Reset viewer when the selected dataset version changes.
  useEffect(() => {
    setData(null);
    setPage(1);
    setSearchInput("");
    setSearch("");
    setSortBy(undefined);
    setSortOrder("asc");
    setUniqueColumn(null);
    setUniqueValues(null);
    setUniqueValuesError(null);
    setError(null);
  }, [datasetId]);

  // Fetch the selected dataset preview.
  useEffect(() => {
    let cancelled = false;

    async function loadPreview() {
      if (!datasetId) return;

      setLoading(true);
      setError(null);

      try {
        const result = await getDatasetPreview(datasetId, {
          page,
          page_size: PAGE_SIZE,
          search: search || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        });

        if (!cancelled) {
          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load dataset preview."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadPreview();

    return () => {
      cancelled = true;
    };
  }, [datasetId, page, search, sortBy, sortOrder]);

  async function toggleUniqueValues(column: string) {
    if (uniqueColumn === column) {
      setUniqueColumn(null);
      setUniqueValues(null);
      setUniqueValuesError(null);
      return;
    }

    setUniqueColumn(column);
    setUniqueValues(null);
    setUniqueValuesError(null);
    setUniqueValuesLoading(true);
    try {
      const result = await getColumnUniqueValues(datasetId, column, 100);
      setUniqueValues(result);
    } catch (err) {
      setUniqueValuesError(
        err instanceof Error ? err.message : "Unable to load unique values.",
      );
    } finally {
      setUniqueValuesLoading(false);
    }
  }

  function handleSort(column: string) {
    if (sortBy === column) {
      setSortOrder((previous) =>
        previous === "asc" ? "desc" : "asc"
      );
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }

    setPage(1);
  }

  const pagination = data?.pagination;
  const totalPages = pagination?.total_pages ?? 0;

  return (
    <div
      id="dataset-preview"
      className="dataset-preview-panel space-y-5"
      aria-labelledby="dataset-preview-heading"
    >
      <div>
        <h3
          id="dataset-preview-heading"
          className="text-xl font-semibold"
        >
          Dataset Preview
        </h3>

        <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
          Explore, search and sort records from the currently selected
          dataset version.
        </p>
      </div>

      {/* Dataset metadata */}
      {data && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            {
              label: "Preview Records",
              value: data.preview_rows.toLocaleString(),
            },
            {
              label: "Preview Limit",
              value: data.preview_limit.toLocaleString(),
            },
          ].map((item) => (
            <div
              key={item.label}
              className="glass-panel-interactive rounded-xl border border-[var(--border)] p-4"
            >
              <p className="text-sm text-[var(--foreground-secondary)]">
                {item.label}
              </p>

              <p className="mt-2 text-2xl font-bold">
                {item.value}
              </p>
            </div>
          ))}
        </div>
      )}

        {/* Search and Sorting Controls */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex w-full flex-col gap-2 sm:max-w-md sm:flex-row">
              <input
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search across all dataset records..."
                aria-label="Search dataset records"
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--foreground)] outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
              />

              {sortBy && (
                <button
                  type="button"
                  onClick={() => {
                    setSortBy(undefined);
                    setSortOrder("asc");
                    setPage(1);
                  }}
                  className="whitespace-nowrap rounded-lg border border-red-500/40 px-4 py-3 text-sm font-medium text-red-600 transition hover:bg-red-500/10 dark:text-red-400"
                >
                  Clear Sort ×
                </button>
              )}
            </div>

            <span className="text-sm font-medium text-[var(--foreground-secondary)]">
              10 records per page
            </span>
          </div>

      {uniqueColumn && (
        <section
          className="rounded-xl border border-cyan-500/30 bg-[var(--surface)] p-4"
          aria-label={`Unique values for ${uniqueColumn}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="font-semibold">Unique values · {uniqueColumn}</h4>
              {uniqueValues && (
                <p className="mt-1 text-xs text-[var(--foreground-secondary)]">
                  {uniqueValues.total_unique_values.toLocaleString()} distinct non-empty values
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                setUniqueColumn(null);
                setUniqueValues(null);
                setUniqueValuesError(null);
              }}
              className="rounded-md border border-[var(--border)] px-2.5 py-1.5 text-xs"
            >
              Close
            </button>
          </div>

          {uniqueValuesLoading && (
            <p className="mt-3 text-sm text-[var(--foreground-secondary)]">Loading unique values…</p>
          )}
          {uniqueValuesError && (
            <p role="alert" className="mt-3 text-sm text-red-600">{uniqueValuesError}</p>
          )}
          {uniqueValues && (
            <>
              <div className="mt-3 flex max-h-48 flex-wrap gap-2 overflow-y-auto">
                {uniqueValues.values.map((value, index) => (
                  <span
                    key={`${String(value)}-${index}`}
                    className="max-w-full break-all rounded-md border border-[var(--border)] bg-[var(--surface-secondary)] px-2.5 py-1.5 text-xs"
                  >
                    {formatValue(value)}
                  </span>
                ))}
                {uniqueValues.has_null && (
                  <span className="rounded-md border border-dashed border-[var(--border)] px-2.5 py-1.5 text-xs italic text-[var(--foreground-secondary)]">
                    NULL
                  </span>
                )}
                {uniqueValues.total_unique_values === 0 && !uniqueValues.has_null && (
                  <span className="text-sm text-[var(--foreground-secondary)]">No values available.</span>
                )}
              </div>
              {uniqueValues.truncated && (
                <p className="mt-2 text-xs text-[var(--foreground-secondary)]">
                  Showing the first {uniqueValues.limit} values. This column has more distinct values; the list is capped to keep the workspace responsive.
                </p>
              )}
            </>
          )}
        </section>
      )}

      {/* Error */}
      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-500/40 bg-red-500/5 p-4"
        >
          <p className="font-medium text-red-700 dark:text-red-300">
            Dataset preview unavailable
          </p>

          <p className="mt-1 text-sm text-[var(--foreground-secondary)]">
            {error}
          </p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div
          role="status"
          className="rounded-xl border border-[var(--border)] p-10 text-center"
        >
          <p className="text-sm text-[var(--foreground-secondary)]">
            Loading dataset records...
          </p>
        </div>
      )}

      {/* Dataset table */}
      {!loading && !error && data && (
        <>
          <div className="overflow-hidden rounded-xl border border-[var(--border)]">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead className="bg-[var(--surface-secondary)]">
                  <tr>
                    <th className="whitespace-nowrap border-b border-[var(--border)] px-4 py-3 font-semibold">
                      #
                    </th>

                    {data.columns.map((column) => (
                      <th
                        key={column.name}
                        className="min-w-40 whitespace-nowrap border-b border-[var(--border)] px-4 py-3"
                      >
                        <button
                          type="button"
                          onClick={() => handleSort(column.name)}
                          title={`Sort by ${column.name} (${column.dtype})`}
                          aria-label={`Sort by ${column.name}, currently ${
                            sortBy === column.name
                              ? sortOrder === "asc"
                                ? "ascending"
                                : "descending"
                              : "unsorted"
                          }`}
                          className="flex items-center gap-2 font-semibold hover:text-cyan-600"
                        >
                          <span>{column.name}</span>

                          <span className="text-xs text-[var(--foreground-secondary)]">
                            {sortBy === column.name
                              ? sortOrder === "asc"
                                ? "↑"
                                : "↓"
                              : "↕"}
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={() => void toggleUniqueValues(column.name)}
                          aria-expanded={uniqueColumn === column.name}
                          aria-label={`Show unique values for ${column.name}`}
                          className={`mt-2 flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition ${
                            uniqueColumn === column.name
                              ? "border-cyan-500 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300"
                              : "border-[var(--border)] text-[var(--foreground-secondary)] hover:border-cyan-500 hover:text-cyan-700"
                          }`}
                        >
                          Unique values <span aria-hidden="true">▾</span>
                        </button>

                        <p className="mt-1 text-xs font-normal text-[var(--foreground-secondary)]">
                          {column.dtype}
                        </p>

                        <div
                          className="mt-3 min-w-36 space-y-1.5 text-[11px] font-normal"
                          aria-label={`Data quality for ${column.name}`}
                        >
                          {[
                            { key: "valid", label: "Valid", dot: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400" },
                            { key: "error", label: "Error", dot: "bg-red-500", text: "text-red-600 dark:text-red-400" },
                            { key: "empty", label: "Empty", dot: "bg-neutral-400", text: "text-[var(--foreground-secondary)]" },
                          ].map((item) => {
                            const metric = column.quality[item.key as keyof typeof column.quality];
                            return (
                              <div key={item.key} className={`flex items-center justify-between gap-2 ${item.text}`}>
                                <span className="flex items-center gap-1.5">
                                  <span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} />
                                  {item.label}
                                </span>
                                <span className="tabular-nums">{metric.percentage}%</span>
                              </div>
                            );
                          })}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {data.records.length > 0 ? (
                    data.records.map((record, index) => (
                      <tr
                        key={index}
                        className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--surface-secondary)]"
                      >
                        <td className="whitespace-nowrap px-4 py-3 text-[var(--foreground-secondary)]">
                          {(page - 1) * PAGE_SIZE + index + 1}
                        </td>

                        {data.columns.map((column) => {
                          const value = record[column.name];

                          return (
                            <td
                              key={column.name}
                              title={formatValue(value)}
                              className="max-w-xs truncate whitespace-nowrap px-4 py-3"
                            >
                              {value === null || value === undefined ? (
                                <span className="italic text-[var(--foreground-secondary)]">
                                  NULL
                                </span>
                              ) : (
                                formatValue(value)
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={data.columns.length + 1}
                        className="px-4 py-12 text-center text-[var(--foreground-secondary)]"
                      >
                        No matching records found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <p className="text-sm text-[var(--foreground-secondary)]">
              Showing{" "}
              {data.records.length > 0
                ? (page - 1) * PAGE_SIZE + 1
                : 0}
              {" – "}
              {(page - 1) * PAGE_SIZE + data.records.length}
              {" of "}
              {pagination?.total_filtered_rows.toLocaleString() ?? 0}
              {" matching records"}
            </p>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() =>
                  setPage((previous) => Math.max(1, previous - 1))
                }
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>

              <span className="px-2 text-sm text-[var(--foreground-secondary)]">
                Page {page} of {totalPages}
              </span>

              <button
                type="button"
                disabled={loading || page >= totalPages}
                onClick={() => setPage((previous) => previous + 1)}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>

          <p className="text-xs text-[var(--foreground-secondary)]">
            Initial preview is limited to 1,000 records. Search and sorting
            operate across the full selected dataset.
          </p>
        </>
      )}
    </div>
  );
}