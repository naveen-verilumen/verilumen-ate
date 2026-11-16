import type { DashboardViewModel } from "../services/yieldImprovementViewModel";
import { Expandable } from "./Expandable";

interface Props {
  dataQuality: DashboardViewModel["dataQuality"];
  notices: DashboardViewModel["notices"];
}

function gapList(items: string[], empty: string) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-600">{empty}</p>;
  }
  return (
    <ul className="list-disc pl-5 text-sm text-slate-700">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function DataQuality({ dataQuality, notices }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Data quality">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Data quality</h2>
      </div>
      {notices.nearLimit ? (
        <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {notices.nearLimit}
        </p>
      ) : null}
      {notices.sequenceCensoring ? (
        <p className="mt-3 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {notices.sequenceCensoring}
        </p>
      ) : null}
      <div className="mt-3">
        <h3 className="text-xs uppercase tracking-wide text-slate-500">Required gaps</h3>
        {gapList(dataQuality.required, "none recorded")}
      </div>
      <Expandable title="Recommended and detector-specific gaps">
        <h3 className="text-xs uppercase tracking-wide text-slate-500">Recommended</h3>
        {gapList(dataQuality.recommended, "none recorded")}
        <h3 className="mt-2 text-xs uppercase tracking-wide text-slate-500">Detector-specific</h3>
        {gapList(dataQuality.detectorSpecific, "none recorded")}
      </Expandable>
    </section>
  );
}
