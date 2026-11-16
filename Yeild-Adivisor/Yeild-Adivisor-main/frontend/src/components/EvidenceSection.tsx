import type { EvidenceDisplayRow } from "../services/yieldImprovementViewModel";
import { Expandable } from "./Expandable";
import { StatusBadge } from "./StatusBadge";

interface Props {
  rows: EvidenceDisplayRow[];
}

export function EvidenceSection({ rows }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Statistical evidence">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Statistical signals</h2>
      {rows.length === 0 ? (
        <p className="mt-3 text-slate-600">No detector findings were returned.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3 font-medium">Signal</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Effect</th>
                <th className="py-2 font-medium">Sample</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.detector}-${row.signal}`} className="border-b border-slate-100 align-top">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-slate-900">{row.signal}</div>
                    <div className="text-xs text-slate-500">{row.detector}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <StatusBadge value={row.status} />
                  </td>
                  <td className="py-2 pr-3 font-mono text-slate-800">{row.effect}</td>
                  <td className="py-2 text-slate-700">{row.sampleSize}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Expandable title="Statistical details">
            <ul className="space-y-2">
              {rows.map((row) => (
                <li key={`${row.detector}-details`}>
                  <span className="font-medium">{row.signal}</span>
                  {`: method ${row.method}; p=${row.pValue}; adjusted p=${row.adjustedPValue}`}
                  {row.dataGaps.length > 0 ? `; gaps: ${row.dataGaps.join(", ")}` : ""}
                </li>
              ))}
            </ul>
          </Expandable>
        </div>
      )}
    </section>
  );
}
