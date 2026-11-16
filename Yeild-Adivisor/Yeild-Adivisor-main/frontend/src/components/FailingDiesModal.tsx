import React, { useEffect, useMemo, useState } from "react";
import type {
  EngineeringRecommendation,
  FailingDieRecord,
  RecommendationFailingDiesResponse,
} from "../types/api";
import { fetchRecommendationFailingDies } from "../services/yieldImprovementApi";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  datasetId: string;
  recommendation: EngineeringRecommendation | null;
  lotId?: string | null;
}

const PAGE_SIZE = 25;

export function FailingDiesModal({
  isOpen,
  onClose,
  datasetId,
  recommendation,
  lotId,
}: Props) {
  const [data, setData] = useState<RecommendationFailingDiesResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>("");
  const [failureCodeFilter, setFailureCodeFilter] = useState<string>("ALL");
  const [page, setPage] = useState<number>(1);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Fetch failing dies whenever recommendation or lot changes
  useEffect(() => {
    if (!isOpen || !recommendation) {
      setData(null);
      setError(null);
      setSearch("");
      setFailureCodeFilter("ALL");
      setPage(1);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);
    setSearch("");
    setFailureCodeFilter("ALL");
    setPage(1);

    fetchRecommendationFailingDies(
      datasetId,
      recommendation.recommendation_id,
      lotId || recommendation.lot_id || undefined,
    )
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || "Failed to load failing dies for this recommendation.");
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, datasetId, recommendation, lotId]);

  // Unique failure codes for filtering
  const failureCodes = useMemo(() => {
    if (!data?.failing_dies) return [];
    const set = new Set<string>();
    for (const d of data.failing_dies) {
      if (d.primary_failure_code) {
        set.add(d.primary_failure_code);
      }
    }
    return Array.from(set).sort();
  }, [data]);

  // Filtered dies based on search and failure code
  const filteredDies = useMemo(() => {
    if (!data?.failing_dies) return [];
    let list = data.failing_dies;

    if (failureCodeFilter !== "ALL") {
      list = list.filter((d) => d.primary_failure_code === failureCodeFilter);
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((d) => {
        const dieIdMatch = d.die_id.toLowerCase().includes(q);
        const waferIdMatch = d.wafer_id.toLowerCase().includes(q);
        const lotIdMatch = d.lot_id.toLowerCase().includes(q);
        const codeMatch = d.primary_failure_code.toLowerCase().includes(q);
        const testMatch = d.failed_test_ids.some((t) => t.toLowerCase().includes(q));
        return dieIdMatch || waferIdMatch || lotIdMatch || codeMatch || testMatch;
      });
    }

    return list;
  }, [data, search, failureCodeFilter]);

  const totalPages = Math.ceil(filteredDies.length / PAGE_SIZE) || 1;
  const paginatedDies = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredDies.slice(start, start + PAGE_SIZE);
  }, [filteredDies, page]);

  if (!isOpen || !recommendation) {
    return null;
  }

  const counts = data?.counts;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-3 sm:p-5 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="failing-dies-title"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-5xl flex-col rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between border-b border-slate-200 bg-slate-50/80 px-5 py-3.5 gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                #{recommendation.priority_rank}
              </span>
              <h2 id="failing-dies-title" className="text-base font-bold text-slate-900">
                Failing Dies Drill-Down
              </h2>
              <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">
                {recommendation.recommendation_category}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-600 font-medium">{recommendation.title}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
            aria-label="Close failing dies dialog"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>


        {/* Explicit Denominators Breakdown */}
        {counts && (
          <div className="border-b border-slate-200 bg-slate-100/70 p-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Explicit Denominator Breakdown
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* 1. Subgroup Failures / Subgroup Eligible Dies */}
              <div className="rounded-lg border border-purple-200 bg-purple-50/80 p-3 shadow-xs">
                <span className="text-[11px] font-bold uppercase tracking-wider text-purple-700">
                  1. Recommendation Subgroup
                </span>
                <p className="mt-1 text-lg font-extrabold text-purple-950">
                  {counts.subgroup_failing_dies.toLocaleString()}{" "}
                  <span className="text-xs font-normal text-purple-800">
                    / {counts.subgroup_eligible_dies.toLocaleString()} dies
                  </span>
                </p>
                <div className="mt-1 flex items-center justify-between text-xs">
                  <span className="font-semibold text-purple-900">
                    {(counts.subgroup_failure_rate * 100).toFixed(1)}% Failure Rate
                  </span>
                  {counts.subgroup_failing_measurements && counts.subgroup_eligible_measurements ? (
                    <span className="text-[11px] text-purple-700 font-normal">
                      ({counts.subgroup_failing_measurements} / {counts.subgroup_eligible_measurements} meas.)
                    </span>
                  ) : null}
                </div>
                <p className="mt-1.5 text-[11px] text-purple-800/90 line-clamp-1" title={data?.subgroup_definition}>
                  {data?.subgroup_definition}
                </p>
              </div>

              {/* 2. Lot-wide Failures / Lot Eligible Dies */}
              <div className="rounded-lg border border-sky-200 bg-sky-50/80 p-3 shadow-xs">
                <span className="text-[11px] font-bold uppercase tracking-wider text-sky-700">
                  2. Selected Lot ({counts.lot_display || counts.lot_id || "All Lots"})
                </span>
                <p className="mt-1 text-lg font-extrabold text-sky-950">
                  {counts.lot_failing_dies !== null ? counts.lot_failing_dies.toLocaleString() : "—"}{" "}
                  <span className="text-xs font-normal text-sky-800">
                    {counts.lot_eligible_dies !== null ? `/ ${counts.lot_eligible_dies.toLocaleString()} dies` : ""}
                  </span>
                </p>
                <div className="mt-1 text-xs font-semibold text-sky-900">
                  {counts.lot_failure_rate !== null ? `${(counts.lot_failure_rate * 100).toFixed(1)}% Lot Failure Rate` : "Global Scope"}
                </div>
                <p className="mt-1.5 text-[11px] text-sky-700">
                  {counts.lot_id ? `First-pass fallout restricted to ${counts.lot_id}` : "Product-wide global recommendation"}
                </p>
              </div>

              {/* 3. Dataset-wide Failures / Dataset Eligible Dies */}
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-xs">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  3. Overall Dataset Baseline
                </span>
                <p className="mt-1 text-lg font-extrabold text-slate-900">
                  {counts.dataset_failing_dies.toLocaleString()}{" "}
                  <span className="text-xs font-normal text-slate-600">
                    / {counts.dataset_eligible_dies.toLocaleString()} dies
                  </span>
                </p>
                <div className="mt-1 text-xs font-semibold text-slate-700">
                  {(counts.dataset_failure_rate * 100).toFixed(1)}% Dataset Failure Rate
                </div>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  All first-pass dies across entire product run
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Filter and Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <input
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Search die, wafer, or failure..."
                className="w-56 rounded-md border border-slate-300 py-1.5 pl-8 pr-3 text-xs focus:border-indigo-500 focus:outline-none"
              />
              <svg className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            {failureCodes.length > 1 && (
              <select
                value={failureCodeFilter}
                onChange={(e) => {
                  setFailureCodeFilter(e.target.value);
                  setPage(1);
                }}
                className="rounded-md border border-slate-300 py-1.5 px-2.5 text-xs text-slate-700 bg-white focus:border-indigo-500 focus:outline-none"
                aria-label="Filter by primary failure code"
              >
                <option value="ALL">All Failure Modes ({data?.failing_dies.length || 0})</option>
                {failureCodes.map((code) => {
                  const count = data?.failing_dies.filter((d) => d.primary_failure_code === code).length || 0;
                  return (
                    <option key={code} value={code}>
                      {code} ({count})
                    </option>
                  );
                })}
              </select>
            )}
          </div>

          <div className="text-xs text-slate-600 font-medium">
            Showing <span className="font-bold text-slate-900">{filteredDies.length}</span> first-pass failing dies
          </div>
        </div>

        {/* Body / Table Area */}
        <div className="flex-1 overflow-auto p-5">
          {loading ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-sm text-slate-500">
              <svg className="h-6 w-6 animate-spin text-indigo-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
              </svg>
              <span>Loading canonical failing dies...</span>
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
              <span className="font-bold">Error:</span> {error}
            </div>
          ) : paginatedDies.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center text-xs text-slate-500">
              <p>No first-pass failing dies match the current search or filter criteria.</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-xs text-slate-800">
                <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-2.5 px-3">Physical Die Identity (Lot / Wafer / Die)</th>
                    <th className="py-2.5 px-3">Coordinates (X, Y)</th>
                    <th className="py-2.5 px-3">Outcome</th>
                    <th className="py-2.5 px-3">Primary Failure Code</th>
                    <th className="py-2.5 px-3">Failed Tests</th>
                    <th className="py-2.5 px-3">Relevant Parametric Measurements</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {paginatedDies.map((die: FailingDieRecord) => {
                    const key = `${die.lot_id}-${die.wafer_id}-${die.die_id}`;
                    return (
                      <tr key={key} className="hover:bg-slate-50/70 transition-colors">
                        {/* Physical Identity */}
                        <td className="py-2 px-3 font-mono font-semibold text-slate-900">
                          {die.lot_id} / {die.wafer_id} / {die.die_id}
                        </td>

                        {/* Coordinates */}
                        <td className="py-2 px-3 text-slate-600 font-mono">
                          {die.x !== null && die.y !== null ? `(${die.x}, ${die.y})` : "—"}
                        </td>

                        {/* Outcome */}
                        <td className="py-2 px-3">
                          <span className="inline-flex items-center rounded bg-rose-100 px-1.5 py-0.5 text-[11px] font-bold text-rose-800">
                            FAIL
                          </span>
                        </td>

                        {/* Primary Failure Code */}
                        <td className="py-2 px-3 font-semibold text-rose-900">
                          {die.primary_failure_code}
                        </td>

                        {/* Failed Tests */}
                        <td className="py-2 px-3 text-slate-600">
                          {die.failed_test_ids && die.failed_test_ids.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {die.failed_test_ids.map((tid) => (
                                <span
                                  key={tid}
                                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-mono font-medium text-slate-700 border border-slate-200"
                                >
                                  {tid}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        {/* Relevant Parametric Measurements */}
                        <td className="py-2 px-3 text-slate-700">
                          {die.relevant_measurements && die.relevant_measurements.length > 0 ? (
                            <div className="space-y-1">
                              {die.relevant_measurements
                                .filter((m) => m.near_limit || die.relevant_measurements.length <= 3)
                                .slice(0, 3)
                                .map((m) => (
                                  <div key={m.parameter_name} className="flex items-center gap-1.5 text-[11px]">
                                    <span className="font-semibold text-slate-800">{m.parameter_name}:</span>
                                    <span className="font-mono">{m.value} {m.unit}</span>
                                    {m.near_limit ? (
                                      <span className="rounded bg-amber-100 px-1 py-0.2 text-[9px] font-bold text-amber-800 border border-amber-300">
                                        Near Limit
                                      </span>
                                    ) : null}
                                  </div>
                                ))}
                              {die.relevant_measurements.length > 3 && (
                                <span className="text-[10px] text-slate-400 italic">
                                  +{die.relevant_measurements.length - 3} more measurements
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer with Pagination */}
        <div className="flex flex-wrap items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-3 text-xs text-slate-600">
          <div>
            Showing Page <span className="font-bold text-slate-900">{page}</span> of{" "}
            <span className="font-bold text-slate-900">{totalPages}</span> ({filteredDies.length} dies)
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
            <button
              type="button"
              onClick={onClose}
              className="ml-2 rounded-md bg-slate-900 px-3.5 py-1 text-xs font-semibold text-white hover:bg-slate-800"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
