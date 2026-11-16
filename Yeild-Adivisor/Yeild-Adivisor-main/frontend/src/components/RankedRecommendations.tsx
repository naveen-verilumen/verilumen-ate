import React, { useEffect, useState } from "react";
import type {
  EngineeringRecommendation,
  RecommendationBundle,
} from "../types/api";
import {
  fetchRecommendations,
} from "../services/yieldImprovementApi";
import { FailingDiesModal } from "./FailingDiesModal";

export type ScopeFilter = "ALL" | "GLOBAL" | "LOT_SPECIFIC";

interface Props {
  bundle?: RecommendationBundle | null;
  datasetId: string;
  selectedLotId?: string | null;
  initialScope?: ScopeFilter;
  onScopeChange?: (scope: ScopeFilter) => void;
}

function isGlobalRecommendation(rec: EngineeringRecommendation): boolean {
  if (rec.scope === "GLOBAL") return true;
  if (rec.scope === "LOT_SPECIFIC") return false;
  if (rec.lot_id && rec.lot_id.trim()) return false;
  const target = (rec.target_population || "").toUpperCase();
  const title = (rec.title || "").toUpperCase();
  if (/\b(?:LOT|PROCESS)\s+[A-Z0-9_-]+/.test(target) || /\b(?:LOT)\s+[A-Z0-9_-]+/.test(title)) {
    return false;
  }
  return true;
}

function isLotLevelRecommendation(rec: EngineeringRecommendation): boolean {
  return !isGlobalRecommendation(rec);
}

function isRecommendationForLot(rec: EngineeringRecommendation, lotId: string): boolean {
  const targetLot = lotId.trim().toUpperCase();

  // 1. If recommendation explicitly specifies a lot_id:
  if (rec.lot_id && rec.lot_id.trim()) {
    return rec.lot_id.trim().toUpperCase() === targetLot;
  }

  // 2. If recommendation scope is LOT_SPECIFIC without an explicit lot_id:
  if (rec.scope === "LOT_SPECIFIC") {
    const target = (rec.target_population || "").toUpperCase();
    const title = (rec.title || "").toUpperCase();
    return target.includes(targetLot) || title.includes(targetLot);
  }

  // 3. For recommendations without explicit lot_id:
  // Check if target_population or title explicitly targets another lot
  const target = (rec.target_population || "").toUpperCase();
  const title = (rec.title || "").toUpperCase();

  const targetLotMatch = target.match(/\b(?:LOT|PROCESS)\s+([A-Z0-9_-]+)/);
  if (targetLotMatch && targetLotMatch[1] && targetLotMatch[1] !== targetLot) {
    return false;
  }

  const titleLotMatch = title.match(/\b(?:LOT)\s+([A-Z0-9_-]+)/);
  if (titleLotMatch && titleLotMatch[1] && titleLotMatch[1] !== targetLot) {
    return false;
  }

  return true;
}

export function RankedRecommendations({
  bundle,
  datasetId,
  selectedLotId,
  initialScope,
  onScopeChange,
}: Props) {
  const currentLotId = selectedLotId?.trim() || null;

  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>(
    initialScope || (currentLotId ? "ALL" : "GLOBAL")
  );

  const [activeBundle, setActiveBundle] = useState<RecommendationBundle | null>(bundle ?? null);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drillDownRec, setDrillDownRec] = useState<EngineeringRecommendation | null>(null);

  // Sync scope if initialScope or lot changes
  useEffect(() => {
    if (initialScope) {
      setScopeFilter(initialScope);
    } else if (!currentLotId) {
      setScopeFilter("GLOBAL");
    } else {
      setScopeFilter("ALL");
    }
  }, [currentLotId, initialScope]);

  // Synchronize when prop changes or fetch fallback when bundle is missing
  useEffect(() => {
    if (bundle !== undefined) {
      setActiveBundle(bundle);
      setLoadError(null);
    } else {
      let isMounted = true;
      setLoading(true);
      setLoadError(null);
      fetchRecommendations(datasetId, currentLotId || undefined)
        .then((res) => {
          if (isMounted) {
            setActiveBundle(res);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (isMounted) {
            setLoadError(err.message || "Failed to load recommendations.");
            setLoading(false);
          }
        });
      return () => {
        isMounted = false;
      };
    }
  }, [bundle, datasetId, currentLotId]);

  const reloadRecommendations = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetchRecommendations(datasetId, currentLotId || undefined);
      setActiveBundle(res);
    } catch (err: any) {
      setLoadError(err.message || "Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" aria-label="Engineering Recommendations">
        <h2 className="text-base font-semibold text-slate-800">Engineering Recommendations</h2>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
          <svg className="h-4 w-4 animate-spin text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          Loading engineering recommendations...
        </div>
      </section>
    );
  }

  if (loadError) {
    return (
      <section className="rounded-lg border border-rose-200 bg-rose-50/60 p-5 shadow-sm" aria-label="Engineering Recommendations">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-rose-900">Engineering Recommendations Error</h2>
          <button
            type="button"
            onClick={reloadRecommendations}
            className="rounded bg-rose-700 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-800"
          >
            Retry
          </button>
        </div>
        <p className="mt-2 text-sm text-rose-700">{loadError}</p>
      </section>
    );
  }

  if (!activeBundle || activeBundle.recommendation_count === 0) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" aria-label="Engineering Recommendations">
        <h2 className="text-base font-semibold text-slate-800">Engineering Recommendations</h2>
        <p className="mt-2 text-sm text-slate-600">
          No actionable recommendations generated for the current view.
        </p>
      </section>
    );
  }

  const currentBundle = activeBundle;
  const allRaw = currentBundle.recommendations;

  // Filter recommendations applicable to current lot context:
  // If a specific lot is selected, lot-specific findings must match that lot.
  const applicableRecs = currentLotId
    ? allRaw.filter((rec) => isGlobalRecommendation(rec) || isRecommendationForLot(rec, currentLotId))
    : allRaw;

  const globalRecs = applicableRecs.filter(isGlobalRecommendation);
  const lotRecs = applicableRecs.filter(isLotLevelRecommendation);

  const allCount = applicableRecs.length;
  const globalCount = globalRecs.length;
  const lotCount = lotRecs.length;

  const displayRecommendations =
    scopeFilter === "GLOBAL"
      ? globalRecs
      : scopeFilter === "LOT_SPECIFIC"
      ? lotRecs
      : applicableRecs;

  return (
    <section className="space-y-4" aria-label="Engineering Recommendations">
      {/* Section Header & Scope Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-base font-bold text-slate-900">Engineering Recommendations</h2>

        {/* Scope Selector: Global vs Lot-Level */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 p-0.5" role="tablist" aria-label="Recommendation scope selector">
            <button
              type="button"
              role="tab"
              aria-selected={scopeFilter === "ALL"}
              onClick={() => {
                setScopeFilter("ALL");
                onScopeChange?.("ALL");
              }}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                scopeFilter === "ALL"
                  ? "bg-slate-900 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All ({allCount})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={scopeFilter === "GLOBAL"}
              onClick={() => {
                setScopeFilter("GLOBAL");
                onScopeChange?.("GLOBAL");
              }}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                scopeFilter === "GLOBAL"
                  ? "bg-sky-700 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Global ({globalCount})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={scopeFilter === "LOT_SPECIFIC"}
              onClick={() => {
                setScopeFilter("LOT_SPECIFIC");
                onScopeChange?.("LOT_SPECIFIC");
              }}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                scopeFilter === "LOT_SPECIFIC"
                  ? "bg-purple-700 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Lot-Level ({lotCount})
            </button>
          </div>
        </div>
      </div>

      {/* Recommendations Cards List */}
      {displayRecommendations.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">
          {scopeFilter === "GLOBAL"
            ? "No product-wide global recommendations identified. Check lot-specific excursion signals."
            : scopeFilter === "LOT_SPECIFIC"
            ? currentLotId
              ? `No lot-specific recommendations identified for lot ${currentLotId}.`
              : "No lot-level recommendations found. Select a specific lot from the Lot dropdown above to analyze lot-specific loss patterns."
            : "No actionable recommendations found."}
        </div>
      ) : (
        <div className="space-y-3">
          {displayRecommendations.map((rec) => {
            const subgroupTotal =
              rec.subgroup_die_count ??
              (rec.observed_failure_rate > 0
                ? Math.round(rec.affected_die_count / rec.observed_failure_rate)
                : rec.eligible_die_count);
            const subgroupFailed = rec.subgroup_failed_die_count ?? rec.affected_die_count;

            return (
              <div
                key={rec.recommendation_id}
                className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
              >
                {/* Section A: Finding */}
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2.5">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                    #{rec.priority_rank}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-bold ${
                      rec.priority_tier === "HIGH"
                        ? "bg-rose-100 text-rose-800"
                        : rec.priority_tier === "MEDIUM"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    Priority: {rec.priority_tier}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-semibold ${
                      rec.confidence_tier === "HIGH"
                        ? "bg-emerald-100 text-emerald-800"
                        : rec.confidence_tier === "MODERATE"
                        ? "bg-blue-100 text-blue-800"
                        : "bg-orange-100 text-orange-800"
                    }`}
                  >
                    Confidence: {rec.confidence_tier}
                  </span>
                  {rec.evidence_strength && (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold border ${
                        rec.evidence_strength === "STRONG"
                          ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                          : rec.evidence_strength === "MODERATE"
                          ? "bg-blue-50 text-blue-800 border-blue-300"
                          : rec.evidence_strength === "WEAK"
                          ? "bg-orange-50 text-orange-800 border-orange-300"
                          : "bg-slate-100 text-slate-700 border-slate-300"
                      }`}
                    >
                      Strength: {rec.evidence_strength}
                    </span>
                  )}
                  {isGlobalRecommendation(rec) ? (
                    <span className="rounded bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-900 border border-sky-200">
                      Global
                    </span>
                  ) : (
                    <span className="rounded bg-purple-100 px-2 py-0.5 text-xs font-semibold text-purple-900 border border-purple-200">
                      Lot-Level {rec.lot_id ? `(${rec.lot_id})` : ""}
                    </span>
                  )}
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                    {rec.target_population}
                  </span>
                </div>

                {/* Recommendation Title & Plain-Language Summary */}
                <div className="mt-2.5">
                  <h3 className="text-base font-bold text-slate-900">{rec.title}</h3>
                  {rec.summary && (
                    <p className="mt-1 text-xs text-slate-600 leading-relaxed">{rec.summary}</p>
                  )}
                </div>

                {/* Section B: Why this recommendation exists */}
                <div className="mt-2.5 grid grid-cols-1 sm:grid-cols-2 gap-2 rounded-md bg-slate-50 p-2.5 text-xs">
                  <div>
                    <span className="text-slate-500">Affected Dies (Overall):</span>
                    <p className="font-semibold text-slate-800">
                      {rec.affected_die_count.toLocaleString()} / {rec.eligible_die_count.toLocaleString()} dies
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">
                      {subgroupTotal < rec.eligible_die_count ? "Subgroup Failure Rate:" : "Failure Rate:"}
                    </span>
                    <p className="font-semibold text-slate-800">
                      {(rec.observed_failure_rate * 100).toFixed(1)}%{" "}
                      <span className="font-normal text-slate-600">
                        ({subgroupFailed.toLocaleString()} / {subgroupTotal.toLocaleString()} dies)
                      </span>
                    </p>
                  </div>
                </div>

                {/* Key Observed Facts */}
                {rec.observed_facts && rec.observed_facts.length > 0 && (
                  <div className="mt-2 text-xs text-slate-700 space-y-1 bg-slate-50/60 p-2.5 rounded border border-slate-200/60">
                    <span className="font-semibold text-slate-800 block text-[11px] uppercase tracking-wide">Key Observed Facts:</span>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-600 text-[11px]">
                      {rec.observed_facts.map((fact, idx) => (
                        <li key={idx}>{fact}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Section C: Evidence Quality & Traceability (Expandable Details) */}
                <details className="mt-2.5 rounded-md border border-slate-200 bg-slate-50/40 text-xs">
                  <summary className="cursor-pointer font-semibold text-slate-700 p-2 hover:bg-slate-100/80 flex items-center justify-between transition-colors">
                    <span className="flex items-center gap-1.5">
                      <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      Evidence Quality & Traceability
                    </span>
                    <span className="text-[11px] font-normal text-slate-500">
                      Validation: <strong className="font-medium text-slate-700">{rec.validation_status || "NOT_EVALUATED"}</strong>
                    </span>
                  </summary>
                  <div className="p-2.5 pt-1.5 space-y-2 border-t border-slate-200/60">
                    {/* Supporting Evidence Items */}
                    {rec.supporting_evidence && rec.supporting_evidence.length > 0 && (
                      <div>
                        <span className="font-semibold text-slate-700 block text-[11px]">Supporting Evidence Traceability:</span>
                        <div className="mt-1 space-y-1">
                          {rec.supporting_evidence.map((item, idx) => (
                            <div key={idx} className="rounded bg-white p-2 border border-slate-200/70 text-[11px]">
                              <div className="flex flex-wrap items-center justify-between gap-1">
                                <span className="font-medium text-slate-800">{item.entity_scope}</span>
                                <span className={`rounded px-1.5 py-0.2 text-[10px] font-semibold ${
                                  item.evidence_classification === "OBSERVED_FACT"
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                    : item.evidence_classification === "STATISTICAL_ASSOCIATION"
                                    ? "bg-blue-50 text-blue-700 border border-blue-200"
                                    : item.evidence_classification === "UNCONFIRMED_HYPOTHESIS"
                                    ? "bg-amber-50 text-amber-700 border border-amber-200"
                                    : "bg-slate-100 text-slate-600"
                                }`}>
                                  {item.evidence_classification}
                                </span>
                              </div>
                              <div className="text-slate-600 mt-0.5">
                                Source: <span className="font-mono text-[10px]">{item.source_artifact}</span>
                                {item.numerator !== null && item.numerator !== undefined && item.denominator && (
                                  <span> | Rate: {item.numerator} / {item.denominator}</span>
                                )}
                                {item.comparison_baseline && (
                                  <span> | Baseline: {item.comparison_baseline}</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Uncertainties & Data Gaps */}
                    {((rec.uncertainties && rec.uncertainties.length > 0) || (rec.data_gaps && rec.data_gaps.length > 0)) && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                        {rec.uncertainties && rec.uncertainties.length > 0 && (
                          <div className="rounded bg-amber-50/50 p-2 border border-amber-200/60">
                            <span className="font-semibold text-amber-900 block text-[11px]">Uncertainties:</span>
                            <ul className="mt-0.5 list-disc list-inside space-y-0.5 text-[11px] text-amber-800">
                              {rec.uncertainties.map((u, idx) => (
                                <li key={idx}>{u}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {rec.data_gaps && rec.data_gaps.length > 0 && (
                          <div className="rounded bg-slate-100/70 p-2 border border-slate-200/70">
                            <span className="font-semibold text-slate-800 block text-[11px]">Data Gaps:</span>
                            <ul className="mt-0.5 list-disc list-inside space-y-0.5 text-[11px] text-slate-700">
                              {rec.data_gaps.map((g, idx) => (
                                <li key={idx}>{g}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </details>

                {/* Section D: What to investigate next */}
                <div className="mt-2.5 rounded-md border border-blue-100 bg-blue-50/60 p-2.5 text-xs text-blue-950">
                  <div className="flex flex-wrap items-center justify-between gap-1 font-bold text-blue-900">
                    <span className="flex items-center gap-1.5">
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Recommended Next Action
                    </span>
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 border border-amber-200">
                      Advisory suggestion — production action forbidden
                    </span>
                  </div>
                  <p className="mt-1 font-medium text-slate-800">{rec.recommended_action}</p>
                </div>

                {/* View Failing Dies Drill-Down Link / Button */}
                {subgroupFailed > 0 && (
                  <div className="mt-2.5 flex items-center justify-between border-t border-slate-100 pt-2.5">
                    <span className="text-[11px] text-slate-500">
                      Supporting subgroup: <strong className="text-slate-700">{subgroupFailed.toLocaleString()}</strong> first-pass failing dies
                    </span>
                    <button
                      type="button"
                      onClick={() => setDrillDownRec(rec)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 hover:border-indigo-300 transition-colors shadow-xs"
                      aria-label={`View failing dies for ${rec.title}`}
                    >
                      <svg className="h-3.5 w-3.5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      View failing dies ({subgroupFailed})
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Failing Dies Drill-Down Modal */}
      <FailingDiesModal
        isOpen={drillDownRec !== null}
        onClose={() => setDrillDownRec(null)}
        datasetId={datasetId}
        recommendation={drillDownRec}
        lotId={currentLotId}
      />
    </section>
  );
}
