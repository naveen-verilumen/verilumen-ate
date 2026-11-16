# Phase 5 — Yield opportunity analysis

**Status:** Implemented. Analytical estimates only. No production recommendations, ATE writes, limit changes, ML, LLM, dashboard, or API.

Companion: `docs/PHASE_4_HYPOTHESIS_ENGINE.md`. Safety: `configs/safety_policy.yaml` (`safety_eligible_production.value: 0`, immutable). Calibration: `configs/calibration.yaml` (`TO_BE_CALIBRATED`).

```text
HypothesisBundle
        ↓
OPPORTUNITY ENGINE
        ↓
OpportunityBundle
        ↓
(not implemented) safety recommendation layer
```

CLI (agent-visible directory only):

```text
python -m yield_improvement opportunity data/synthetic/agent_visible/<dataset_id>
```

Default attribution: `PRIMARY_FAILURE`. Pass `--attribution ANY_FAIL` for the overlapping any-fail labeling. The two modes are never mixed silently.

The engine never reads hidden ground truth.

---

## Four quantities (never merged)

| Quantity | Meaning | V1 rule |
|----------|---------|---------|
| Observed loss | Measured first-pass fails / eligible dies | A measurement, not an opportunity |
| Upper-bound opportunity | Associated fails in the hypothesis slice / eligible | If every fail in the slice were recoverable — **not a forecast** |
| Plausible opportunity | Excess fail rate vs complement, PRELIMINARY | Not `evidence_score`, not P(recoverable) |
| Safety-eligible production | Production-deployable opportunity | **Always 0** |

Required disclaimer on every item and bundle:

> Observed loss is not a predicted FPY gain. Upper bound assumes every fail in this slice is recoverable, which is usually false. Safety-eligible production opportunity is 0%.

Do not write “FPY will increase by X%.” Write: observed associated loss is X percentage points; that is an upper bound, not a predicted improvement.

---

## Schema

`Opportunity` (extra fields forbidden):

- identity: `opportunity_id`, `hypothesis_id`, `family`, `detail`
- `attribution_mode`: `PRIMARY_FAILURE` \| `ANY_FAIL`
- `status`: `OBSERVED` \| `ESTIMATED` \| `PRELIMINARY` \| `INSUFFICIENT_DATA` \| `OVERLAPPING` \| `NOT_ESTIMABLE` \| `NOT_ELIGIBLE_FOR_PRODUCTION`
- `status_flags` always includes `NOT_ELIGIBLE_FOR_PRODUCTION`. `APPROVED_FOR_PRODUCTION` is rejected.
- counts/rates: observed, upper bound, plausible (`plausible_unavailable` when not computed)
- `safety_eligible_production_count = 0`, `safety_eligible_production_rate = 0.0`
- overlap: `overlap_count`, `union_count`, `exclusive_count`, `intersection_count`, `included_in_union`
- traceability: `population_definition`, `affected_die_ids`, `eligible_population`, `calculation_method`, `config_versions`
- `assumptions`, `data_gaps`, `limitations`, `disclaimer`

`OpportunityBundle.summary` reports overall observed FPY loss, `sum_of_individual_upper_bounds` (explicitly allowed to exceed observed loss), `union_upper_bound` (the non-double-counted quantity), `plausible_total`, and `safety_eligible_total = 0`.

---

## Observed loss

Overall:

\[
L = N_{\mathrm{fail}} / N_{\mathrm{eligible}}
\]

on first-pass eligible dies from the Phase 1 FPY engine.

Hypothesis-associated observed loss (default `PRIMARY_FAILURE`): failed eligible dies in the affected slice, divided by \(N_{\mathrm{eligible}}\). One die is one first-pass fail. `ANY_FAIL` additionally counts a die if any executed test is FAIL; that mode is labeled separately.

Avoid double counting by never adding slice rates into overall \(L\).

---

## Upper bound

For a resolvable slice:

\[
U = L^{\mathrm{obs}}_{\mathrm{slice}}
\]

Interpretation: maximum observed associated loss if every fail in that slice were unnecessary and fully recoverable. It is **not** a predicted FPY gain.

`PRIMARY_EVIDENCE` slices are eligible for the non-double-counted union. `SECONDARY_ASSOCIATION` is reported as an observed association with status `NOT_ESTIMABLE` and is excluded from the union (`opportunity_include_secondary_in_union` candidate 0).

---

## Plausible opportunity (PRELIMINARY, TO_BE_CALIBRATED)

Do **not** set plausible = evidence_score or \(1-p\). Do **not** copy \(U\) when a recipe cannot be computed.

Excess-rate recipe (V1 spec class recipes, unified):

\[
P = \max(0, n_{\mathrm{fail,slice}} - r_{\mathrm{complement}} \cdot n_{\mathrm{slice}}) / N
\]

which is \(\max(0, \mathrm{FPY}_{comp}-\mathrm{FPY}_{slice})\times n_{slice}/N\).

- `WEAK_ASSOCIATION`: multiply by `opportunity_plausible_weak_scale` (candidate 0.50), still PRELIMINARY.
- `SECONDARY_ASSOCIATION`, `INSUFFICIENT_EVIDENCE`, unresolved population: `plausible_unavailable = true`.
- `TEST.LIMIT_SENSITIVITY` and `CORRELATED.FAILURES`: plausible unavailable (not claimed recoverable; no limit change).
- `TEST.SEQUENCE`: not invented under stop-on-fail censoring.
- Conflicting detectors: block plausible.

If the slice is below `n_min_group_compare`, plausible is unavailable.

When primary slices overlap, `plausible_total = min(sum(P_i), L)` and is flagged.

---

## Overlap

For each pair/set of **primary** slices:

- exclusive = fails in this slice only
- intersection = fails in all compared primary slices
- union = unique failed dies across primary slices

`sum_of_individual_upper_bounds` may exceed observed FPY loss; the bundle labels that. Combined opportunity is the **union**, not the sum. S15 EDGE + DRIFT each have an item plus `OPP-UNION-PRIMARY`.

Correlated support (lot nested in drift, wafer nested in spatial) is not a second independent opportunity in the union.

---

## Status

| Status | When |
|--------|------|
| `INSUFFICIENT_DATA` | Population cannot be established (missing X/Y, sequence censoring, etc.) |
| `NOT_ESTIMABLE` | Secondary association / not eligible for union upper-bound treatment |
| `OVERLAPPING` | Primary slice shares failed dies with another primary |
| `PRELIMINARY` | Excess-rate plausible computed, uncalibrated |
| `ESTIMATED` | Upper bound only |
| `OBSERVED` | Associated loss reported without an estimable bound |
| `NOT_ELIGIBLE_FOR_PRODUCTION` | Always present as a flag; never `APPROVED_FOR_PRODUCTION` |

S01 / S16: `no_actionable_opportunity = true`, empty `opportunities[]`, overall observed loss still in the summary. No invented cause.

---

## Safety-eligible production

Copied from `configs/safety_policy.yaml`. Immutable 0. Configuration load refuses any other value. Opportunity models refuse non-zero fields. STRONG evidence, large upper bounds, and synthetic FPY improvements do not change this.

Investigation-eligible opportunity is not computed in this phase (safety recommendation layer is out of scope).

---

## Examples

**S02 spatial edge.** Affected = dies with radius ≥ edge quantile. Observed associated loss = edge first-pass fails / \(N\). Upper bound = that rate. Plausible = excess vs interior, PRELIMINARY. Production = 0%.

**S09 near-limit.** Observed associated loss in the δ-band. Upper bound reported. Plausible unavailable (not claimed recoverable). No candidate limit. No “increase test limit.” Production = 0%.

**S15 dual cause.** EDGE and DRIFT each have an opportunity. Combined = union of failed dies. Lot/wafer secondary associations are observed, not added into the union.

**S11 sequence.** No `TEST.SEQUENCE` opportunity is invented from stop-on-fail-censored later tests.

---

## Evaluation

`yield_improvement.evaluation.opportunity` joins `RUN_SUMMARY.json` after `estimate_from_dir`. Metrics are correctness and traceability, not “higher opportunity is better.”

Machine-readable table: `evaluation/results/opportunity_phase5.json`.

---

## Known limitations

- Plausible excess-rate scale is `TO_BE_CALIBRATED` and is not a recoverable fraction.
- Extra Phase 3/4 associations (e.g. S15 contact) can still produce a primary observed opportunity if equipment did not fire; they enter the union only if classified `PRIMARY_EVIDENCE`.
- Sequence and many co-fail pairs remain censored.
- No Wilson interval on plausible rates yet; small-n slices force `plausible_unavailable`.
- `ANY_FAIL` is labeled but default analysis is `PRIMARY_FAILURE`.

---

## Recommended next phase

Phase 6: safety **recommendation** layer (`INVESTIGATE` / `REVIEW` / `MONITOR` / `NEEDS_MORE_DATA` / `REJECTED`), still `production_action: forbidden`, still `invoked: false` for specialist labels, still no ATE or limit writes. Opportunity scores must not override a failed safety gate.
