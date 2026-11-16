import type { HypothesisCardModel } from "../services/yieldImprovementViewModel";

interface Props {
  cards: HypothesisCardModel[];
  title?: string;
}

export function HypothesisCards({ cards, title = "Investigation Findings" }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white px-5 py-4" aria-label="Investigation findings">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {cards.length === 0 ? (
        <p className="mt-3 text-slate-600">No strong systematic signal was detected.</p>
      ) : (
        <div className="mt-3 space-y-4">
          {cards.map((card) => (
            <article key={card.hypothesisId} className="rounded-md border border-slate-200 px-4 py-3">
              <h3 className="font-medium text-slate-900">{card.title}</h3>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Finding</dt>
                  <dd className="mt-0.5">{card.finding}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Confidence</dt>
                  <dd className="mt-0.5">{card.confidence}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Next</dt>
                  <dd className="mt-0.5">{card.nextStep}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
