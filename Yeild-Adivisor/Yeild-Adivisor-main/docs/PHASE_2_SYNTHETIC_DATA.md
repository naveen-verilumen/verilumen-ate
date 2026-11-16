# Phase 2 — Synthetic datasets with hidden ground truth

**Status:** Implemented. No ML, detectors, hypothesis ranking, opportunity engine, recommendations, dashboard, FastAPI, or STDF parser.

This phase exists so a later Yield Improvement agent can be scored against **answers it is not allowed to see**.

Companion design: `docs/SYNTHETIC_DATA_DESIGN.md`.

---

## Phase 1 follow-ups completed first

1. **`safety_policy.yaml` `when`.** YAML `when: true` was a boolean. S12 is now `when: "ALWAYS"` (quoted string). `DecisionRule` rejects booleans. Safety outcomes are unchanged (fail-closed default still `NEEDS_MORE_DATA`).
2. **Missing `part_class`.** Kept: assume `PRODUCTION` + `part_class_assumed_production`. Spec status remains `FROZEN_OPEN_TO_REVERSE`. Not silently changed. Documented here because reversing it would change FPY eligibility on unlabeled lots.

Existing CASE_01–14 `expected.json` files were not edited.

---

## What was built

Configurable generator under `src/yield_improvement/synthetic/`. Configuration: `configs/synthetic.yaml`. Development profile: **small** (8 lots × 2 wafers × 49 dies = **784 unique dies** per scenario).

Agent-visible output:

```text
data/synthetic/agent_visible/<dataset_id>/
  lots.csv  wafers.csv  parts.csv  die_attempts.csv
  test_results.csv  parametric_measurements.csv  equipment.csv
  manifest.json          # anonymous; no scenario_id / true cause
```

Hidden output:

```text
evaluation/ground_truth/synthetic/<dataset_id>/
  ground_truth.json
  scenario_manifest.json
  validation_report.json
evaluation/ground_truth/synthetic/RUN_SUMMARY.json
```

---

## How to generate

```text
python -m yield_improvement generate --all-core --profile small
python -m yield_improvement generate --scenario S02 --seed 42 --profile small
```

`--profile` may be `small`, `medium`, or `large`. Size is YAML-only.

---

## First development run (seed 20260322, small)

All 16 core scenarios generated. Canonical validation, scenario sanity, leakage scan, and Phase 1 pipeline load: **PASSED**.

| Scenario | Hidden cause | Dies | Attempts | First-pass FPY |
|----------|--------------|------|----------|----------------|
| S01 | RANDOM.FAILURE | 784 | 784 | 0.864 |
| S02 | SPATIAL.EDGE | 784 | 784 | 0.736 |
| S03 | SPATIAL.CENTER | 784 | 784 | 0.733 |
| S04 | SPATIAL.RING | 784 | 784 | 0.781 |
| S05 | EQUIPMENT.DEGRADATION | 784 | 784 | 0.834 |
| S06 | PROCESS.DRIFT | 784 | 784 | 0.755 |
| S07 | ENVIRONMENT.TEMPERATURE | 784 | 784 | 0.770 |
| S08 | PARAMETRIC.SHIFT | 784 | 784 | 0.749 |
| S09 | TEST.LIMIT_SENSITIVITY | 784 | 784 | 0.471 |
| S10 | CONTACT.PROBE | 784 | 911 | 0.759 |
| S11 | TEST.SEQUENCE | 784 | 784 | 0.915 |
| S12 | PROCESS.LOT_VARIATION | 784 | 784 | 0.844 |
| S13 | PROCESS.WAFER_VARIATION | 784 | 784 | 0.870 |
| S14 | CORRELATED.FAILURES | 784 | 784 | 0.677 |
| S15 | EDGE + DRIFT | 784 | 784 | 0.675 |
| S16 | NO_CONFIDENT_ROOT_CAUSE | 784 | 784 | 0.909 |

S16 is the empirical **baseline FPY** (~0.91), inside the configured 0.85–0.97 band. S10 attempt count is higher because some first-pass fails receive a passing retest. S09 FPY is low because measurements are concentrated around the production limit without changing that limit.

---

## Tests

```text
python -m pytest
```

Includes: existing Phase 1 golden FPY tests (CASE_01–14 unchanged), new config tests for `"ALWAYS"` / boolean rejection / part_class policy, generator schema tests for S01–S16, reproducibility (S02 same seed identical, different seed differs), leakage (forbidden columns on agent-visible files), and scenario sanity.

---

## Isolation rules

The future agent (and Phase 1 `analyze` path) may read `data/synthetic/agent_visible/**` and `configs/*.yaml`.

It must not read `evaluation/ground_truth/**` or columns such as `scenario_id`, `true_cause`, `ground_truth`, `injected_effect`, `expected_hypothesis`, `generator_seed`, `difficulty`.

---

## Recommended next phase (not this document)

Hypothesis ranking over Phase 3 detector evidence, still advisory-only, still `safety_eligible_production = 0`.
