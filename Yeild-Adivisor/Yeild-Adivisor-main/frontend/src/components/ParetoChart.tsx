import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ParetoDisplayRow } from "../services/yieldImprovementViewModel";

interface Props {
  rows: ParetoDisplayRow[];
  unavailableNote: string | null;
}

export function ParetoChart({ rows, unavailableNote }: Props) {
  if (rows.length === 0) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Failure Pareto">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Where is yield lost?</h2>
        <p className="mt-3 text-slate-600">{unavailableNote ?? "PRIMARY_FAILURE Pareto is not available."}</p>
      </section>
    );
  }
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Failure Pareto">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Where is yield lost?</h2>
      <p className="mt-1 text-xs text-slate-500">PRIMARY_FAILURE only. Values copied from the analysis output.</p>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 16, right: 16, top: 8, bottom: 8 }}>
            <XAxis type="number" domain={[0, 100]} tickFormatter={(value: number) => `${value}%`} />
            <YAxis
              type="category"
              dataKey="displayLabel"
              width={220}
              tick={{ fontSize: 11 }}
              interval={0}
            />
            <Tooltip
              formatter={(value) => [`${Number(value).toFixed(1)}% of fails`, "Share of fails"]}
              labelFormatter={(label) => String(label)}
            />
            <Bar dataKey="shareOfFailsPct" fill="#334155" radius={[0, 2, 2, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 space-y-1 text-sm text-slate-700">
        {rows.map((row) => (
          <li key={row.failureKey}>
            <span className="font-medium">{row.displayLabel}</span>
            {" · "}
            {row.affectedDiesLabel} dies
            {" · "}
            {row.shareOfFailsLabel} of fails
            {" · "}
            {row.percentageOfEligibleLabel} of eligible
          </li>
        ))}
      </ul>
    </section>
  );
}
