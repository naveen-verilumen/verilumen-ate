import type { AnalysisStatus, DataQualityState } from "../services/yieldImprovementViewModel";

const STATUS_CLASS: Record<string, string> = {
  COMPLETE: "bg-emerald-50 text-emerald-800 border-emerald-200",
  HEALTHY: "bg-emerald-50 text-emerald-800 border-emerald-200",
  SIGNAL: "bg-emerald-50 text-emerald-800 border-emerald-200",
  AVAILABLE: "bg-emerald-50 text-emerald-800 border-emerald-200",
  MONITOR: "bg-amber-50 text-amber-900 border-amber-200",
  REVIEW: "bg-amber-50 text-amber-900 border-amber-200",
  WARNING: "bg-amber-50 text-amber-900 border-amber-200",
  PARTIAL: "bg-amber-50 text-amber-900 border-amber-200",
  NEEDS_MORE_DATA: "bg-amber-50 text-amber-900 border-amber-200",
  NO_CONFIDENT_HYPOTHESIS: "bg-amber-50 text-amber-900 border-amber-200",
  ML_DEGRADED: "bg-amber-50 text-amber-900 border-amber-200",
  DEGRADED: "bg-red-50 text-red-800 border-red-200",
  NEEDS_RETRAINING: "bg-red-50 text-red-800 border-red-200",
  INSUFFICIENT_DATA: "bg-red-50 text-red-800 border-red-200",
  REJECTED: "bg-red-50 text-red-800 border-red-200",
  FORBIDDEN: "bg-slate-100 text-slate-700 border-slate-300",
  UNAVAILABLE: "bg-slate-100 text-slate-600 border-slate-200",
  UNCONFIRMED: "bg-slate-100 text-slate-700 border-slate-300",
  NO_SIGNAL: "bg-slate-100 text-slate-700 border-slate-200",
  STRONG_EVIDENCE: "bg-emerald-50 text-emerald-800 border-emerald-200",
  MODERATE_EVIDENCE: "bg-amber-50 text-amber-900 border-amber-200",
  WEAK_EVIDENCE: "bg-slate-100 text-slate-700 border-slate-200",
  INSUFFICIENT_EVIDENCE: "bg-slate-100 text-slate-600 border-slate-200",
  INVESTIGATION_CANDIDATE_ONLY: "bg-indigo-50 text-indigo-800 border-indigo-200",
  NO_THRESHOLD_ESTABLISHED: "bg-slate-100 text-slate-600 border-slate-200",
  EVALUATED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  INSUFFICIENT_TRAIN_DATA: "bg-amber-50 text-amber-900 border-amber-200",
  NO_HELD_OUT_TARGET_FAILURES: "bg-slate-100 text-slate-600 border-slate-200",
  NOT_EVALUATED: "bg-slate-100 text-slate-500 border-slate-200",
};

interface Props {
  value: string | AnalysisStatus | DataQualityState;
}

export function StatusBadge({ value }: Props) {
  const cls = STATUS_CLASS[value] ?? "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium tracking-wide ${cls}`}>
      {value}
    </span>
  );
}
