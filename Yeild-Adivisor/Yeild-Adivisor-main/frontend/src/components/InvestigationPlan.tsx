interface Props {
  steps: string[];
  noConfidentHypothesis: boolean;
}

export function InvestigationPlan({ steps, noConfidentHypothesis }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Recommended next investigation">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Recommended next investigation</h2>
      {noConfidentHypothesis || steps.length === 0 ? (
        <p className="mt-3 text-slate-700">
          No strong systematic signal was detected. Additional data or investigation is required.
        </p>
      ) : (
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-slate-800">
          {steps.map((step, index) => (
            <li key={`${index}-${step}`}>{step}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
