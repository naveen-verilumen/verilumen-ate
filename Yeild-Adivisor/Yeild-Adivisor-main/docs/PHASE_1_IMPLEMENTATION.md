# Phase 1 Implementation — Data loading, validation, FPY engine

**Status:** Implemented. Deterministic foundation only. No ML, detectors, opportunity engine, STDF, API, or dashboard.

This agent is a **standalone** product. It does not import or call any other semiconductor agent.

---

## Package structure

```text
src/yield_improvement/
├── __init__.py              run_pipeline export
├── __main__.py              small CLI
├── pipeline.py              load → validate → FPY
├── config/                  YAML load + pydantic validation
├── models/                  canonical rows + FpyResult
├── ingestion/               CSV/Parquet loaders
├── validation/              data-quality issues
├── yield_analysis/          FPY + primary/any-fail attribution
└── utils/                   paths, parse, errors

tests/unit/                  golden FPY, config, schema, independence
tests/integration/           fixture-directory pipeline
tests/fixtures/fpy/          CASE_01–14 (unchanged expected.json)
configs/                     policy YAML (source of truth)
```

Install (from repo root):

```text
python -m pip install -e ".[dev]"
```

---

## Data flow

```text
CSV/Parquet die_attempts (+ optional test_results)
        → schema / type normalize (no silent invention)
        → data-quality issues (ERROR | WARNING | ASSUMPTION | UNAVAILABLE)
        → unique-die first-pass eligibility (fpy_policy.yaml)
        → FPY counts + invariant
        → primary-fail (exactly one per fail die) + any-fail (overlap OK)
        → FpyResult JSON
```

The agent never reads `evaluation/ground_truth/` or forbidden label columns (`true_*`, `planted_*`, `scenario_id`, …).

---

## Canonical model

Primary fact: **`die_attempts`** — grain unique `(lot_id, wafer_id, die_id)` × `attempt_id`.

Also typed: Lot, Wafer, Part, TestResult, Failure, ParametricMeasurement, Equipment (Phase 1 loads die_attempts + test_results; other entities exist for later phases).

---

## FPY algorithm

Implemented in `yield_analysis/fpy.py`. Behavior is taken from `configs/fpy_policy.yaml`:

\[
\mathrm{FPY} = N_{\text{first-pass PASS}} / N_{\text{eligible unique dies}}
\]

- First valid **production** attempt only (`attempt_number == 1` / `is_first_attempt`).
- Abort on first attempt → **FAIL** (`abort_is_first_pass_fail`).
- Retest PASS does not change a first-pass FAIL.
- Retest-only, engineering, calibration, rework, missing disposition, missing identity, ambiguous duplicates → **excluded**.
- Missing `part_class` → treat as `PRODUCTION` and emit assumption flag `part_class_assumed_production`.
- Same `attempt_id` twice on a die → exclude `AMBIGUOUS_DUPLICATE`.
- Distinct attempts: earliest valid first-pass by `(timestamp, attempt_number, attempt_id)`.
- Mixed `product_id`/`step_id` → `INVALID` / `POPULATION_MIX`.
- Invariant: `n_eligible == n_pass + n_fail`.

`escape_rate` is always `unavailable`.

---

## Primary-failure algorithm

`yield_analysis/attribution.py`:

1. `is_first_fail == true` (exactly one) → that `test_id`.
2. Else min `sequence_index` if all failed tests have it (ties → `UNKNOWN_PRIMARY_FAILURE`).
3. Else single failed test.
4. Else abort / attempt `failure_code` / `BIN:{sbin}`.
5. Else `UNKNOWN_PRIMARY_FAILURE` / `UNKNOWN.PRIMARY_UNORDERED`.

No severity ranking. Each fail die has **exactly one** PRIMARY. Any-fail is a separate overlapping table.

Unmapped codes → `UNKNOWN.UNMAPPED_CODE` (no string-similarity guessing).

---

## Data-quality behavior

| Severity | Meaning |
|----------|---------|
| ERROR | Invalid value, missing identity, duplicates, mix, forbidden columns |
| WARNING | Unmapped bin/code, missing sequence for multi-fail |
| ASSUMPTION | Missing part_class → PRODUCTION |
| UNAVAILABLE | No tester_id / no x,y (analysis not invented) |

Normal DQ problems return structured `FpyResult`; they do not raise pandas exceptions. Exceptions are for missing files / malformed YAML only.

---

## How to run tests

```text
python -m pytest
```

All CASE_01–14 expected counts are read from `tests/fixtures/fpy/case_XX/expected.json`. Those files were not edited to force a pass.

---

## How to run the CLI

```text
python -m yield_improvement tests/fixtures/fpy/case_01
python -m yield_improvement --die-attempts path/to/die_attempts.csv --test-results path/to/test_results.csv
python -m yield_improvement generate --all-core --profile small
```

FPY CLI prints JSON: eligible dies, first-pass pass/fail, FPY, exclusions, primary/any-fail tables.

`generate` writes agent-visible CSVs under `data/synthetic/agent_visible/` and hidden ground truth under `evaluation/ground_truth/synthetic/`. See `docs/PHASE_2_SYNTHETIC_DATA.md`.

---

## Test strategy

- Golden counts for every fixture case.
- Policy YAML is loaded in tests (abort, excluded classes, assumption flag) so behavior is not re-hardcoded in test code.
- Primary-failure unit tests for first-fail, sequence, ties, abort, unmapped codes.
- Schema: forbidden columns, population mix, parquet round-trip.
- Independence: no `dtl_agent` / sibling-agent imports in `src/`.
- Synthetic generator: S01–S16 validation, reproducibility, ground-truth leakage.

---

## Out of scope (later phases)

Spatial / equipment / drift detectors, opportunity, safety recommendation gate, STDF parser, ML, dashboard.

Statistical detectors (evidence only) are Phase 3 (`docs/PHASE_3_STATISTICAL_DETECTORS.md`). Hypothesis ranking is not implemented.
