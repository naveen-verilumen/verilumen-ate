# Synthetic data design — Yield Improvement

**Status:** Implemented in Phase 2. This package is self-contained. It does not import DTL, Dynamic Test Limits, False Failure Reduction, Retest Reduction, or Escape Prevention. It does not call another agent or reuse another agent's datasets or models.

Purpose: controlled experiments with a **known hidden cause**, observable data that the future agent may see, and later evaluation against that hidden truth.

```text
KNOWN HIDDEN CAUSE
        ↓
OBSERVABLE DATA  (data/synthetic/agent_visible/<dataset_id>/)
        ↓
FUTURE YIELD AGENT
        ↓
HYPOTHESIS
        ↓
EVALUATION vs evaluation/ground_truth/synthetic/<dataset_id>/
```

This phase generates, validates, and stores data. It does **not** implement detectors, ranking, opportunity, recommendations, a dashboard, FastAPI, or an STDF parser.

---

## Architecture

```text
configs/synthetic.yaml
        ↓
src/yield_improvement/synthetic/
├── config.py         load + type-check generator YAML
├── baseline.py       healthy population with realistic noise
├── scenarios.py      S01–S16 injectors (modular registry)
├── generator.py      realize outcomes, write canonical tables
├── ground_truth.py   hidden GroundTruth schema
└── validation.py     canonical + integrity + sanity + leakage
```

Flow:

1. `build_baseline` — lots → wafers → dies on a wafer grid, with lot/wafer/die/tester noise.
2. `apply_scenario` — mutate failure probabilities, measurements, or sequence (no labels on dies).
3. `realize_outcomes` — Bernoulli / parametric / sequence draws → pass/fail, bins, test results.
4. `run_generator_validation` — Phase 1 loader + hierarchy + coordinates + parametric limits + leakage + scenario sanity. Invalid data is **not** silently repaired.
5. Persist agent-visible CSVs separately from ground truth JSON.

Grain remains **unique die × attempt**, using the Phase 1 canonical models (`Lot`, `Wafer`, `Part`, `DieAttempt`, `TestResult`, `ParametricMeasurement`, `Equipment`).

---

## Baseline model

Configured in `configs/synthetic.yaml` under `baseline`. Dataset size lives in YAML profiles (`small` / `medium` / `large`), not in Python.

Assumptions:

- Additive Gaussian offsets on a Bernoulli fail probability: lot, wafer, die, small tester offsets.
- Tester offsets are **not** planted equipment causes; they are normal shop-floor variation.
- Measurement noise around passing parametric means (`IDDQ`, `VMIN`). Rare natural limit crossings are kept.
- Temperatures overlap lots and testers so temperature is not 1:1 confounded with equipment.
- Expected first-pass FPY band: `expected_fpy_min`–`expected_fpy_max` (default 0.85–0.97). The no-signal scenario (S16) is the empirical baseline FPY check.
- Population is not perfect: background fails exist by design.

Hierarchy: Product → lots → wafers → dies → attempts → tests.

---

## Scenarios S01–S16

| Id | Hidden cause | Observable intent |
|----|----------------|-------------------|
| S01 | `RANDOM.FAILURE` | Extra i.i.d. fails; no systematic association |
| S02 | `SPATIAL.EDGE` | Failures concentrate near wafer edge |
| S03 | `SPATIAL.CENTER` | Failures concentrate at center |
| S04 | `SPATIAL.RING` | Radial ring |
| S05 | `EQUIPMENT.DEGRADATION` | One tester elevated; others remain populated |
| S06 | `PROCESS.DRIFT` | Fail probability rises with lot/time index |
| S07 | `ENVIRONMENT.TEMPERATURE` | Hot setpoint elevated; temps overlap lots/testers |
| S08 | `PARAMETRIC.SHIFT` | IDDQ mean shift on selected lots; production limits unchanged |
| S09 | `TEST.LIMIT_SENSITIVITY` | Measurements near the **unchanged** production limit; no `tight_limit` column |
| S10 | `CONTACT.PROBE` | Probe-card associated continuity fails; some retest recovery |
| S11 | `TEST.SEQUENCE` | P(FUNC fail \| IDDQ fail and IDDQ precedes FUNC) elevated |
| S12 | `PROCESS.LOT_VARIATION` | Selected lots elevated |
| S13 | `PROCESS.WAFER_VARIATION` | Selected wafers elevated |
| S14 | `CORRELATED.FAILURES` | IDDQ and FUNCTIONAL associated, not deterministic |
| S15 | `SPATIAL.EDGE` + `PROCESS.DRIFT` | Dual cause; competing explanations |
| S16 | `NONE.NO_CONFIDENT_ROOT_CAUSE` | Baseline only; agent must not invent a cause |

`hard_options` in YAML (weak signal, strong noise, unequal lot sizes, missing optional fields, confounding, …) is configuration support for later runs. The first development run leaves `enabled: false`.

---

## Configuration

`configs/synthetic.yaml` controls seed, profiles, testers and weights, probe cards, temperatures, test program, parametric limits, baseline rates, per-scenario parameters, and sanity delta.

Same seed + same configuration ⇒ same observable dataset (reproducibility test: S02).

---

## Ground-truth separation

Agent-visible tree (`data/synthetic/agent_visible/<dataset_id>/`):

- `lots.csv`, `wafers.csv`, `parts.csv`, `die_attempts.csv`, `test_results.csv`, `parametric_measurements.csv`, `equipment.csv`
- `manifest.json` — opaque `dataset_id`, row counts, `seed_hash`, optional fields present. **No** `scenario_id`, true cause, injected parameters, difficulty, or generator seed.

Hidden tree (`evaluation/ground_truth/synthetic/<dataset_id>/`):

- `ground_truth.json` — typed `GroundTruth` (scenario, true_causes, injected_parameters, affected_population, expected_signal, confounders, difficulty, seed)
- `scenario_manifest.json`
- `validation_report.json`

Operator index: `evaluation/ground_truth/synthetic/RUN_SUMMARY.json` maps `dataset_id` → `scenario_id`. The Phase 1 FPY pipeline must not read this path (`configs/allowlist.yaml`).

`dataset_id` is `ds_` + SHA-256 of version, profile, seed, and scenario. It does not spell `S02`.

---

## Reproducibility

`random.Random(seed)` is the only RNG. CSV writers use `\n` line endings. Identical seed + config produces byte-identical `die_attempts.csv`. A different seed must differ and still pass validation.

---

## Validation

Every generated dataset must pass:

- Phase 1 canonical parse (`parse_die_attempts` / `parse_test_results`) and quality issues at ERROR severity
- Lot / wafer / part / equipment / parametric pydantic rows
- Hierarchy and unique IDs
- Attempt order (`attempt_number`, `is_first_attempt`, `is_retest`)
- Disposition `PASS`/`FAIL`
- Coordinates inside wafer radius
- Parametric pass/fail vs limits (`measurement > upper_limit` ⇒ FAIL; equality is PASS)
- No forbidden columns on agent-visible tables
- Scenario-specific sanity (edge rate, equipment split, drift, temperature, parametric shift, S16 no injection, …)
- Written files re-run through `run_pipeline` (`status == OK`)

---

## Scaling

Change `active_profile` or pass `--profile medium|large`. Do not hardcode N in Python. `large` is still a development scale (not millions of rows). Increase `n_lots` / `grid_side` in YAML when a stress dataset is needed.

---

## Known limitations (realism)

- Failure injection is additive probability, not a physics/process recipe.
- Wafer maps are a rectangular grid clipped to a radius, not a real stepper shot map or notch.
- Only two temperatures and one product/step.
- Equipment “degradation” is a fail-rate bump, not a parametric signature per pin.
- S09 produces a low FPY by design (mass of measurements around the limit).
- S11 keeps a high FPY because the extra fail is conditional on a prior fail.
- Retest recovery is generated only in S10.
- Hard-option generators (unequal lot sizes, missing fields, extra confounding) are configured but not applied in the first run.
- Not STDF; CSV compatible with Phase 1 loaders only.

---

## Phase 1 policy notes (not changed)

Missing `part_class` still means: treat as `PRODUCTION` and set `part_class_assumed_production`. Spec marks this **OPEN to reverse** if real data is mostly unlabeled engineering. Prompt 5 keeps current behavior. Generated data writes `part_class=PRODUCTION` explicitly so the assumption flag is not triggered on synthetic files.

Safety decision-table `when` must be a quoted string (`"ALWAYS"`), not a YAML boolean.
