# Phase 4 — Hypothesis composition, evidence ranking, and explanation

**Status:** Implemented. Unconfirmed associations only. No opportunity engine, safety recommendations, ATE writes, ML, LLM, dashboard, or API.

Companion: `docs/PHASE_3_STATISTICAL_DETECTORS.md`. Calibration: `configs/calibration.yaml` (`status: TO_BE_CALIBRATED`).

```text
RAW DATA
   ↓
FPY ENGINE
   ↓
STATISTICAL DETECTORS
   ↓
DetectorBundle
   ↓
HYPOTHESIS COMPOSER
   ↓
UNCONFIRMED HypothesisBundle
   ↓
(not implemented) opportunity / safety layers
```

Every hypothesis sets `not_a_root_cause: true`. There is no `confirmed_root_cause` field. Status is always `UNCONFIRMED`.

The composer never reads hidden ground truth (`scenario_id`, `true_cause`, `RUN_SUMMARY`). Evaluation joins labels **after** composition.

CLI (agent-visible directory only):

```text
python -m yield_improvement hypothesize data/synthetic/agent_visible/<dataset_id>
```

---

## Architecture

```text
src/yield_improvement/hypotheses/
├── contract.py     Hypothesis / HypothesisBundle
├── identity.py     family.detail identity + associative statements
├── ranking.py      PRELIMINARY evidence_score (not P(cause))
├── explain.py      Deterministic templates (no LLM)
└── composer.py     DetectorBundle → HypothesisBundle

src/yield_improvement/evaluation/hypotheses.py   # GT join AFTER compose
```

---

## Schema

`Hypothesis` (extra fields forbidden):

| Field | Meaning |
|-------|---------|
| `hypothesis_id` | `H-{family}.{detail}` |
| `family` / `detail` | Taxonomy identity (associative, not causal) |
| `statement` | “Yield loss is associated with …” |
| `status` | `UNCONFIRMED` |
| `not_a_root_cause` | `true` (immutable) |
| `association_class` | `PRIMARY_EVIDENCE` \| `SECONDARY_ASSOCIATION` \| `WEAK_ASSOCIATION` \| `INSUFFICIENT_EVIDENCE` |
| `evidence_tier` | `STRONG_EVIDENCE` \| `MODERATE_EVIDENCE` \| `WEAK_EVIDENCE` \| `INSUFFICIENT_EVIDENCE` |
| `evidence_score` | Transparent rank score in `[0, 1]` |
| `score_status` | `PRELIMINARY` |
| `confidence_level` | `INSUFFICIENT` \| `LOW` \| `MEDIUM` \| `HIGH` — `HIGH` is still UNCONFIRMED |
| `evidence` / `counter_evidence` | Preserved detector packets |
| `supporting_detectors` / `conflicting_detectors` | Detector names |
| `statistical_evidence` | method, n, effect, p, adjusted p, populations, role |
| `affected_population` / `data_coverage` / `data_gaps` | Propagated, never inferred |
| `validation_required` | Engineering checks, not production actions |
| `explanation` | Deterministic template text |

`HypothesisBundle`: `analysis_id`, `current_fpy`, `hypotheses[]`, `no_confident_hypothesis`, `data_gaps`, `detector_summary`, `limitations`. No production-action fields.

---

## Hypothesis identity

Identity is `family + detail` (scope labels such as tester id stay in `affected_population`). Two SIGNAL packets with the same identity contribute evidence to **one** hypothesis. Different identities stay separate.

| Detector | Identity |
|----------|----------|
| spatial | `SPATIAL.{EDGE\|CENTER\|RING}` |
| equipment | `EQUIPMENT.DEGRADATION` |
| temporal | `PROCESS.DRIFT` |
| temperature | `ENVIRONMENT.TEMPERATURE` |
| parametric | `PARAMETRIC.SHIFT` |
| near_limit | `TEST.LIMIT_SENSITIVITY` |
| sequence | `TEST.SEQUENCE` |
| contact | `CONTACT.PROBE` |
| lot | `PROCESS.LOT_VARIATION` |
| wafer | `PROCESS.WAFER_VARIATION` |
| correlation | `CORRELATED.FAILURES` |
| no_signal | does not create a cause hypothesis |

`SPATIAL.EDGE` and `PROCESS.DRIFT` are two hypotheses. They are never collapsed into “EDGE + DRIFT root cause”.

---

## Evidence composition

Roles on `statistical_evidence`:

| Role | Meaning |
|------|---------|
| `PRIMARY_EVIDENCE` | Detector whose identity is this hypothesis, and the identity is not a nested grain of another SIGNAL |
| `SECONDARY_SUPPORT` | Same identity, but the association is classified secondary/weak |
| `CORRELATED_SUPPORT` | A different detector analyzing a nested grain of this identity |
| `CONFLICTING_EVIDENCE` | Reserved; not invented |

Documented nested grains (not independent confirmation):

- `lot` ⊂ `temporal` (lot is the time grain of drift)
- `wafer` ⊂ `temporal` / `lot` / `spatial`
- `contact` ⊂ `equipment`
- `near_limit` ⊂ `parametric`

The composer does **not** score `number of SIGNAL detectors`. Two packets on nearly identical data are correlated support plus an explicit limitation.

Counter-evidence is copied from detectors or recorded when a nested-grain SIGNAL exists beside a parent SIGNAL. Methodological disclaimers (`association_is_not_causation`) go to `limitations`. Empty `counter_evidence` is allowed. Missing X/Y, equipment, temperature, sequence, or limits are propagated as `data_gaps`; they are never filled in.

Association class:

- `PRIMARY_EVIDENCE` — identity is not nested under another SIGNAL and `|effect|` meets the weak floor
- `SECONDARY_ASSOCIATION` — nested grain of another SIGNAL (S15 lot/wafer beside EDGE+DRIFT)
- `WEAK_ASSOCIATION` — nested with small effect, or primary with `|Δ rate| < 1.5 × min_effect_size_fpy_delta`
- `INSUFFICIENT_EVIDENCE` — not used to invent a hypothesis from `INSUFFICIENT_DATA` detectors

`no_confident_hypothesis` is true when no `PRIMARY_EVIDENCE` hypothesis reaches `MODERATE_EVIDENCE` or `STRONG_EVIDENCE`.

---

## Ranking and evidence_score

`evidence_score` is **not** a probability of root cause and is **not** `1 − p`.

```text
sig  = 1.0 if adjusted_p ≤ fdr_q
     | 0.55 if raw p ≤ alpha
     | 0.40 if a non-p SIGNAL path exists (e.g. near-limit mass)
     | 0.0 otherwise

eff  = min(1, |effect| / metric_reference)
       fail_rate_difference reference = hypothesis_effect_ref_rate_diff (0.10)
       ks_d / 0.40; jaccard / 0.30; mann_kendall_tau / 0.80; near_limit_mass / 0.40

sample    = min(1, n / hypothesis_n_ref)
coverage  = max(0, 1 − 0.15 × min(4, n_gaps))
independence = 1 if ≥2 supporting detectors are not a documented parent/child pair, else 0
counter   = min(1, 0.25 × n_counter_items)

raw = 0.30·sig + 0.30·eff + 0.15·sample + 0.15·coverage + 0.10·independence − 0.15·counter
raw ∈ [0, 1]
raw × 0.65 if SECONDARY_ASSOCIATION
raw × 0.45 if WEAK_ASSOCIATION
```

Tiers from `calibration.yaml` candidates (`hypothesis_score_strong` 0.75, `moderate` 0.50, `weak` 0.30). **A single detector is one view:** without independent support, tier is capped at `MODERATE_EVIDENCE`. `HIGH` confidence is not assigned in V1 (`confidence_high_min_independent_views` = 2); even then the hypothesis remains UNCONFIRMED.

The full set is ranked by `(-evidence_score, family, detail)` and preserved. `hypothesis_top_k` is not used to drop competitors.

---

## Competing hypotheses

Multiple hypotheses may be valid at once. S15 must keep both:

- H1 `SPATIAL.EDGE`
- H2 `PROCESS.DRIFT`

Lot/wafer/contact packets on S15 remain in the bundle as secondary or observed associations. The system must not claim “lot variation is the root cause” because the lot detector fired.

---

## Negative controls

**S01 (random) and S16 (no signal):** if no systematic SIGNAL exists, `hypotheses = []` and `no_confident_hypothesis = true`. The composer must not invent a cause. `no_signal` never becomes a yield-loss hypothesis.

---

## S11 sequence censoring

Stop-on-fail writes later tests as `NOT_EXECUTED`. The sequence detector often returns `INSUFFICIENT_DATA`. Phase 4 does **not** invent later-test outcomes or infer order from CSV row order.

When sequence is `INSUFFICIENT_DATA`, no `TEST.SEQUENCE` hypothesis is composed. Bundle limitations include:

> Later-test observations are censored by stop-on-fail behavior.

If the generator/observable contract should emit continue-on-fail pairs for sequence evaluation, that is a **separate** data-contract change. Hidden ground truth is not edited to make evaluation pass.

---

## Validation recommendations

Templates only. Examples:

- Spatial: additional lots; wafer-map repeatability
- Equipment: matched lots across equipment; maintenance/probe history
- Temporal: process changes; equipment state over time
- Temperature: matched temperature conditions
- Parametric: independent-sample distribution shift
- Sequence: controlled execution (stop-on-fail censors later tests)
- Contact: probe-card comparison on matched lots

None of these are production actions. The composer does not SET_LIMIT, change recipes, or compute opportunity.

---

## Evaluation

`yield_improvement.evaluation.hypotheses` runs `compose_from_dir` on `data/synthetic/agent_visible/` then joins `evaluation/ground_truth/synthetic/RUN_SUMMARY.json`.

Measures: expected identity present, extra identities, missing identities, S15 dual-cause recovery, S01/S16 `no_confident_hypothesis`, S11 non-invention, ranking order, `not_a_root_cause` on every hypothesis.

Machine-readable table: `evaluation/results/hypotheses_phase4.json`.

---

## Known limitations

- `evidence_score` is PRELIMINARY. Thresholds are `TO_BE_CALIBRATED` and must not be treated as factory SLAs.
- Correlated detectors can still emit extra observed associations (equipment/contact/lot/wafer FPs from Phase 3). They are classified, not silently deleted to beautify scores.
- Sequence and many co-fail pairs are censored by stop-on-fail.
- One statistical view cannot justify HIGH confidence or a confirmed cause.
- No stratified “effect after controlling for lot” test yet; that counter-evidence is only recorded when the nested-grain structure applies.

---

## Recommended next phase

Phase 5: opportunity bounds that copy `safety_eligible_production = 0`, still advisory, still no ATE writes. Do not implement safety decisioning as production recommendations in that phase until the opportunity contract is honest about upper bounds.
