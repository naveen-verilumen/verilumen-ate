interface Props {
  fpy: string;
  fpyLoss: string;
  eligibleDies: string;
}

export function KpiSummary({ fpy, fpyLoss, eligibleDies }: Props) {
  const items = [
    { label: "FPY", value: fpy },
    { label: "FPY LOSS", value: fpyLoss },
    { label: "ELIGIBLE DIES", value: eligibleDies },
  ];
  return (
    <section aria-label="KPI summary" className="grid grid-cols-3 gap-4">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-slate-200 bg-white px-4 py-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{item.label}</div>
          <div className="mt-2 font-mono text-3xl font-semibold text-slate-900">{item.value}</div>
        </div>
      ))}
    </section>
  );
}
