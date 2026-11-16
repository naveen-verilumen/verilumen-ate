import type { DashboardViewModel } from "../services/yieldImprovementViewModel";

interface Props {
  opportunity: DashboardViewModel["opportunity"];
  title?: string;
}

export function OpportunitySection({ opportunity, title = "Yield Opportunity" }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Yield opportunity">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Current FPY</dt>
          <dd className="font-mono text-lg">{opportunity.fpy}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">FPY Loss</dt>
          <dd className="font-mono text-lg">{opportunity.fpyLoss}</dd>
        </div>
      </dl>
      {opportunity.rows.length > 0 ? (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-3 font-medium">Finding</th>
              <th className="py-2 font-medium">Potential opportunity</th>
            </tr>
          </thead>
          <tbody>
            {opportunity.rows.map((row) => (
              <tr key={row.id} className="border-b border-slate-100">
                <td className="py-2 pr-3">{row.title}</td>
                <td className="py-2 font-mono">{row.potential}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-3 text-sm text-slate-600">No investigation opportunity estimates are available.</p>
      )}
      <p className="mt-3 text-sm text-slate-600">{opportunity.overlapNote}</p>
    </section>
  );
}
