import { DashboardView } from "../components/DashboardView";
import { Header } from "../components/Header";
import { useDashboard } from "../hooks/useDashboard";
import { toDashboardViewModel } from "../services/yieldImprovementViewModel";

export function DashboardPage() {
  const {
    datasets,
    selectedLotId,
    lots,
    payload,
    waferMap,
    parametricAnalysis,
    parametricLoading,
    parametricError,
    loading,
    error,
    selectLot,
    refreshAnalysis,
    retry,
  } = useDashboard();

  let body;
  if (loading) {
    body = <p className="text-slate-600">Loading analysis…</p>;
  } else if (error) {
    body = (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        <p>API unavailable. {error}</p>
        <button type="button" className="mt-2 rounded border border-red-300 px-2 py-1" onClick={retry}>
          Retry
        </button>
      </div>
    );
  } else if (datasets.length === 0) {
    body = <p className="text-slate-600">No datasets are available.</p>;
  } else if (!payload) {
    body = <p className="text-slate-600">Analysis results are not available yet.</p>;
  } else if (payload.report.fpy_summary.fpy === null) {
    body = (
      <div className="space-y-4">
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Insufficient data for a reliable first-pass yield analysis.
        </p>
        <DashboardView
          model={toDashboardViewModel(payload)}
          waferMap={waferMap}
          selectedLotId={selectedLotId}
          parametricAnalysis={parametricAnalysis}
          parametricLoading={parametricLoading}
          parametricError={parametricError}
        />
      </div>
    );
  } else {
    body = (
      <DashboardView
        model={toDashboardViewModel(payload)}
        waferMap={waferMap}
        selectedLotId={selectedLotId}
        parametricAnalysis={parametricAnalysis}
        parametricLoading={parametricLoading}
        parametricError={parametricError}
      />
    );
  }

  const model = payload ? toDashboardViewModel(payload) : null;

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        selectedLotId={selectedLotId}
        lots={lots}
        generatedAt={model?.generatedAt ?? null}
        onSelectLot={selectLot}
        onRefresh={refreshAnalysis}
        refreshing={loading}
      />
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">{body}</main>
    </div>
  );
}
