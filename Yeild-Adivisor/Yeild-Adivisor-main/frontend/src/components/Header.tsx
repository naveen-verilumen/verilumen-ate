import type { DatasetLot } from "../types/api";
import { formatAnalysisTimestampIst } from "../services/format";

interface Props {
  selectedLotId: string;
  lots: DatasetLot[];
  generatedAt: string | null;
  onSelectLot: (lotId: string) => void;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function Header({ selectedLotId, lots, generatedAt, onSelectLot, onRefresh, refreshing }: Props) {
  const lastAnalysis = formatAnalysisTimestampIst(generatedAt);
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-4 px-6 py-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Advisory analysis</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Yield Advisor — Pre-Production</h1>
          <div className="mt-2 flex items-center gap-3">
            {lastAnalysis ? (
              <p className="text-xs text-slate-500">Last analysis: {lastAnalysis}</p>
            ) : null}
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={refreshing}
                className="text-xs text-indigo-600 hover:text-indigo-800 underline font-medium disabled:opacity-50"
              >
                {refreshing ? "Re-running…" : "Re-run analysis"}
              </button>
            )}
          </div>
        </div>
        <label className="text-sm text-slate-600">
          Lot
          <select
            aria-label="Lot"
            className="ml-2 rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900"
            value={selectedLotId}
            onChange={(event) => onSelectLot(event.target.value)}
            disabled={lots.length === 0}
          >
            <option value="">All lots</option>
            {lots.map((lot) => (
              <option key={lot.lot_id} value={lot.lot_id}>
                {lot.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  );
}
