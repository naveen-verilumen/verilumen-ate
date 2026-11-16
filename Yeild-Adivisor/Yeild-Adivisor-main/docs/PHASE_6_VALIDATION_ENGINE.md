# Phase 6 — Safety and validation layer

**Status:** Implemented. Advisory engineering investigation only. No production authorization, ATE writes, limit changes, specialist-agent invocation, ML, or LLM.

Companion: `docs/PHASE_5_OPPORTUNITY_ENGINE.md`. Safety policy: `configs/safety_policy.yaml` (S0–S12 unchanged; production eligibility immutable 0).

```text
OpportunityBundle
        ↓
SAFETY
        ↓
DATA QUALITY
        ↓
POPULATION VALIDITY
        ↓
EVIDENCE SUFFICIENCY
        ↓
CONFLICTING EVIDENCE
        ↓
CONFIDENCE / ENGINEERING POLICY
        ↓
(opportunity is last and cannot override earlier gates)
        ↓
ValidationBundle
```

CLI (agent-visible directory only; one load, then hypotheses → opportunity → validation):

```text
python -m yield_improvement validate data/synthetic/agent_visible/<dataset_id>
```

Existing commands `analyze`, `detect`, `hypothesize`, and `opportunity` are unchanged.

Phase 1 `validation/quality.py` (`collect_quality_issues`) is preserved. Phase 6 adds gates beside it. The validator never reads hidden ground truth.

---

## 1. Architecture

```text
src/yield_improvement/validation/
├── quality.py          Phase 1 data-quality issues (unchanged)
├── contract.py         ValidationResult / ValidationBundle
├── safety.py           forbidden verbs, production=0, no promised FPY
├── data_quality.py     PASS / WARNING / FAIL / UNAVAILABLE
├── population.py       arithmetic and attribution
├── evidence.py         descriptive score, independence, conflicts
├── recommendation.py   INVESTIGATE / REVIEW / MONITOR / NEEDS_MORE_DATA / REJECTED
└── validator.py        orchestrator
```

---

## 2. Validation contract

`ValidationResult` (`extra=forbid`) includes analysis/hypothesis/opportunity IDs, recommendation + reason, evidence and opportunity rates, four gate statuses, validation steps, supporting/conflicting detectors, gaps, overlap/union/exclusive counts, `gate_trace`, and `traceability`.

Immutable fields:

| Field | Value |
|-------|--------|
| `production_action` | `FORBIDDEN` |
| `production_authorized` | `false` |
| `safety_eligible_production_count` | `0` |
| `safety_eligible_production_rate` | `0.0` |
| `invoked_agents` | `[]` |
| `not_a_root_cause` | `true` |

Creating `APPROVED_FOR_PRODUCTION`, `SET_LIMIT`, `CHANGE_LIMIT`, `MODIFY_RECIPE`, `MODIFY_ATE`, `MODIFY_EQUIPMENT`, or non-zero production eligibility raises a validation error.

---

## 3. Safety gate ordering

From `configs/safety_policy.yaml` `principle_order`:

1. SAFETY
2. DATA_QUALITY
3. POPULATION_VALIDITY
4. EVIDENCE_SUFFICIENCY
5. CONFLICTING_EVIDENCE
6. CONFIDENCE
7. ENGINEERING_POLICY
8. OPPORTUNITY

`independent_of_opportunity: true` is unchanged. A large upper bound cannot pass a failed earlier gate. S0–S4 remain fail-closed for production verbs, numeric limits, invented escape, and promised FPY wording.

---

## 4. Data-quality policy

States: `PASS`, `WARNING`, `FAIL`, `UNAVAILABLE`. Missing fields are never invented.

- FAIL: no eligible denominator, referential integrity errors, corrupted grain.
- UNAVAILABLE: family-required fields missing (X/Y for spatial, tester for equipment, temperature, parametric/limits, sequence under stop-on-fail).
- WARNING: optional context missing while unrelated evidence remains usable.

---

## 5. Population validation

Require a reproducible `population_definition`, eligible denominator, attribution mode (`PRIMARY_FAILURE` vs `ANY_FAIL`, never mixed), and hypothesis identity.

Unchecked arithmetic is **not clamped**:

- `affected_count <= eligible_denominator`
- `observed_loss_count <= affected_count`
- `upper_bound_count <= affected_count`
- `plausible_count <= upper_bound_count`

Invalid arithmetic → `REJECTED`. Unresolved population → `NEEDS_MORE_DATA`.

---

## 6. Evidence validation

`evidence_score` is descriptive only. It is not P(cause), P(recovery), or P(FPY gain).

A single statistical view cannot be HIGH confidence. Lot/wafer/contact nested grains are not independent confirmation. Secondary associations are not upgraded to primary. Unavailable evidence stays `NEEDS_MORE_DATA`.

---

## 7. Conflict handling

Conflicts are recorded (`conflict_type`, supporting vs counter-evidence) and the hypothesis is **not deleted**.

Typical outcomes: `REVIEW` (overlapping primary slices, conflicting detectors) or `NEEDS_MORE_DATA` (unreplicated counter-evidence). Secondary nested grains stay visible as `MONITOR`.

---

## 8. Recommendation states

Exactly: `INVESTIGATE`, `REVIEW`, `MONITOR`, `NEEDS_MORE_DATA`, `REJECTED`.

Policy (first deciding gate wins):

| Condition | State |
|-----------|--------|
| Safety wording / forbidden verb / production request | REJECTED |
| Invalid population arithmetic | REJECTED |
| Missing denominator / unresolved population / required evidence unavailable | NEEDS_MORE_DATA |
| Major overlapping or conflicting primary evidence | REVIEW |
| Secondary or weak association | MONITOR |
| Primary evidence, population established, preliminary but meaningful | INVESTIGATE |
| Default | NEEDS_MORE_DATA |

Opportunity size, p-value, detector count, and evidence_score alone do not set the state.

---

## 9. Validation-step generation

Deterministic templates by family (spatial wafers/lots/stratification; equipment matched lots; drift chronology; temperature coverage; parametric coverage; near-limit metadata and repeatability **without changing the limit**; contact probe identity; lot/wafer stability; correlated co-occurrence as statistics). Sequence steps record stop-on-fail censoring and forbid inventing later tests.

---

## 10. S01 / S16

`no_actionable_recommendation = true`, empty `results`. Overall observed FPY loss remains on the bundle. No invented investigation target.

---

## 11. S15 overlap

`SPATIAL.EDGE` and `PROCESS.DRIFT` are validated separately. `OPP-UNION-PRIMARY` is `REVIEW` with explicit “not a combined root cause.” Overlap/union/sum-of-individuals from Phase 5 are copied into `overlap_summary`. Lot/wafer remain secondary `MONITOR`.

---

## 12. S09 near-limit

Allowed: `INVESTIGATE` / `REVIEW` / `NEEDS_MORE_DATA`. Forbidden in output: increase/decrease/change/optimize/set limit, candidate limit, `SET_LIMIT`. Production remains 0.

---

## 13. S11 censoring

No invented sequence opportunity. If a sequence item exists it is `NEEDS_MORE_DATA`. Bundle limitations record stop-on-fail censoring.

---

## 14. Immutable production = 0

Copied from `safety_policy.yaml`. Config load, opportunity models, and validation models all refuse non-zero values. `production_authorized=true` cannot be constructed.

---

## 15. Traceability

Each result traces `analysis_id`, `hypothesis_id`, `opportunity_id`, detector IDs, population definition, eligible denominator, attribution mode, calculation method, and calibration / safety / FPY policy versions.

---

## 16. Holdout evaluation

`yield_improvement.evaluation.validation` joins `RUN_SUMMARY.json` after `validate_from_dir`. Table: `evaluation/results/validation_phase6.json`. Success is correctness (no invented causes, no limit writes, production=0, S15 uncollapsed), not “more INVESTIGATE is better.”

---

## 17. Tests

Unit: contracts (13), safety (7), evidence (6), population (7). Evaluation holdout (9). Isolation: no `scenario_id` / `true_cause` / `RUN_SUMMARY` in the validation package. Standalone: existing forbidden-import test still applies.

Full suite: **198 collected, 198 passed, 0 failed** (`python -m pytest -q --tb=line`).

Holdout table: `evaluation/results/validation_phase6.json` (16/16 scenarios; `safety_violations = 0`).

---

## 18. Limitations

- No historical replication store; CONFIDENCE/HISTORY uses current-run independence only.
- PROCESS.DRIFT with a single statistical view plus unreplicated counter-evidence is fail-closed to `NEEDS_MORE_DATA` (S06/S12/S13/S15). Overlapping primary slices without that conflict stay `REVIEW`.
- S15 contact may still validate as a primary observed association if equipment did not fire.
- Sequence remains censored by the observable contract.
- Recommendation policy thresholds are documented, not factory SLAs.

---

## 19. Calibration items

Reuse Phase 3–5 `TO_BE_CALIBRATED` n-min and evidence-tier candidates. No new production SLA. `opportunity_cannot_override_earlier_gates` is a frozen policy flag, not a numeric threshold.

---

## 20. Next recommended phase

Phase 7 (if any): operator-facing **review packet** (static report of ValidationBundle + OpportunityBundle + HypothesisBundle) still without ATE writes, still `invoked=false`, still production eligibility 0. Do not add a decision-maker that converts INVESTIGATE into APPLY_TO_PRODUCTION.
