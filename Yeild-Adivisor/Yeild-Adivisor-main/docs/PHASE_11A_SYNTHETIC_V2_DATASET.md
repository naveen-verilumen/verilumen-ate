# Phase 11A — Yield Improvement Synthetic Dataset V2

## 1. Dataset purpose

Replace the small Phase 2 hashed-scenario collection (`ds_<hash>`, 8 lots × 2 wafers × 49 dies) as the **active** Yield Improvement production dataset.

V2 is a single controlled semiconductor-native hierarchy:

`DATASET → LOT → WAFER → DIE → TEST / PARAMETRIC / EQUIPMENT / ENVIRONMENT`

It is large enough and structured enough for FPY, lot/wafer/die analysis, wafer maps, test Pareto, equipment, temporal drift, parametric analysis, LOLO, hypothesis generation, opportunity estimation, and later ML retraining.

This phase **generates and activates V2 data only**. It does not retrain, approve, or activate a model. `artifacts/ml/yi_ml_v1/` is unchanged.

## 2. Dataset version

- Internal id: `yi_synthetic_v2`
- Dataset version: `yi_synth_v2`
- Display name: Yield Improvement V2
- Type: `SYNTHETIC`
- Config: `configs/synthetic_v2.yaml`

## 3. Seed

`20261101`

Stored only in hidden ground truth / evaluation validation JSON. Not written to agent-visible CSVs or `manifest.json`.

## 4–9. Counts

| Item | Value |
| --- | --- |
| Lots | 5 (`L001`–`L005`) |
| Wafers per lot | 5 (`W01`–`W05`) |
| Total wafers | 25 |
| Dies per wafer | 100 (10 × 10 grid) |
| Dies per lot | 500 |
| Total unique dies | 2500 |
| First-pass attempts | 2500 |
| Retest attempts | 60 |
| Test-result rows | 25600 (10 tests × 2560 attempts) |
| Parametric rows | 20480 (8 parameters × 2560 attempts) |

## 10–11. Tests and retests

Each attempt has tests `T001`–`T010`. First-pass PASS dies have all required tests PASS. First-pass FAIL dies have at least one FAIL. Retests exist only on a controlled subset of first-pass failures and never rewrite `first_pass_fail`.

## 12. FPY by lot (emergent, not forced)

Overall first-pass yield: **89.96%** (inside 80%–95%).

| Lot | FPY |
| --- | --- |
| L001 | 93.4% |
| L002 | 90.2% |
| L003 | 92.4% |
| L004 | 80.6% |
| L005 | 93.2% |

## 13. FPY by wafer

See `evaluation/results/synthetic_v2_validation.json` (`wafer_fpy`). Notable temporal pattern on L004: W01 94% → W05 55%.

## 14. Failure distribution (first-pass primary `failure_code`)

CONTACT 92, VMIN 39, IDDQ 38, CONTINUITY 17, OPENS 13, VMAX 12, FUNCTIONAL 12, SHORTS 10, LEAKAGE 9, SCAN 9.

## 15. Equipment distribution

Testers shared across lots (not unique to a scenario): T01 1052 dies, T02 847, T03 601.

First-pass fail rates: T01 11.5%, T02 8.9%, T03 9.2%. Detectable, not 100% correlated.

## 16. Temperature distribution

Varies around 25 °C with a hot-condition subset near 85 °C. Observed min / mean / max: 17.9 / 32.0 / 89.4 °C.

## 17. Spatial distribution

Each wafer is a deterministic 10 × 10 grid, `x,y ∈ {1…10}`. Die `D001` is (1,1); `D100` is (10,10).

Observed overall edge fail rate 13.1% vs center 8.8%. On L002, edge fail rate exceeds interior (quality check `l002_edge_higher_fail`: PASS).

## 18. Hidden scenario mapping

Stored only under `evaluation/ground_truth/synthetic_v2/`. Not present on agent-visible tables.

| Lot | Hidden role | Expected signal family |
| --- | --- | --- |
| L001 | BASELINE | NONE |
| L002 | SPATIAL_EDGE | SPATIAL.EDGE |
| L003 | EQUIPMENT (T01 elevated, not deterministic) | EQUIPMENT.DEGRADATION |
| L004 | PROCESS_DRIFT (later wafers worse) | PROCESS.DRIFT |
| L005 | WEAK_MIXED | WEAK |

## 19. Agent-visible vs hidden data

Agent-visible (`data/synthetic/agent_visible/yi_synthetic_v2/`):

- `manifest.json` (no seed, no cause labels)
- `die_attempts.csv`
- `test_results.csv`
- `parametric_measurements.csv`
- `lot_metadata.csv` / `lots.csv`
- `wafer_metadata.csv` / `wafers.csv`
- `parts.csv`
- `equipment.csv`

Hidden: `evaluation/ground_truth/synthetic_v2/yi_synthetic_v2.json` and `RUN_SUMMARY.json`.

## 20. Data-quality checks

All generator checks in `evaluation/results/synthetic_v2_validation.json` are PASS: hierarchy, unique dies, 10×10 grid, first-pass coverage, retest isolation, no orphan tests/parametrics, chronological timestamps, FPY range, L002 edge elevation, non-trivial equipment effect, no hidden labels on agent-visible tables.

## 21. Known limitations

- Parametric names include IDDQ/VMIN/etc. The current champion `yi_ml_v1` still expects the V1 feature contract (`IR_DROP_MV`, `THERMAL_C`, …). V2 is **not** used to retrain in this phase.
- L004 W05 FPY is low (55%) because drift accumulates by wafer index. That is intentional process-drift evidence, not a post-hoc clamp.
- `creation_seed` is omitted from the agent-visible manifest because `generator_seed` is a forbidden hidden-label column. Seed remains in hidden GT.
- Historical S01–S16 / monitoring datasets were **removed from the production selector** and archived under `tests/fixtures/synthetic_v1/` so holdout tests still run.

## Replacement inventory (2A.1)

| Old dataset | Path (now archived) | Type | Referenced by | Safe to remove from active data |
| --- | --- | --- | --- | --- |
| `ds_0b5542c71e1a13e0` (S02 / champion training set) | `tests/fixtures/synthetic_v1/agent_visible/ds_0b5542c71e1a13e0` | synthetic V1 | ML explainer, holdouts, monitoring reference | YES (active) / NO (delete entirely) |
| `ds_223a4dcbba4d4202` and other S01–S16 hashes | `tests/fixtures/synthetic_v1/agent_visible/ds_*` | synthetic V1 | evaluation holdouts, historical `evaluation/results/*` | YES (active) / NO (delete entirely) |
| `ds_mon_01`–`ds_mon_10` | `tests/fixtures/synthetic_v1/monitoring/agent_visible/` | monitoring fixture | monitoring tests / health JSON | YES (production selector) / NO (delete entirely) |
| `case_01` FPY fixtures | `tests/fixtures/fpy/` | golden FPY | API/unit tests | NO (not a production dataset; never deleted) |
| `yi_ml_v1` | `artifacts/ml/yi_ml_v1/` | champion model | registry, dashboard ML snapshot | NO |

Reference classes:

- **A. Active runtime** — `GET /api/datasets` and frontend selector now use only `yi_synthetic_v2`.
- **B. Test fixture** — archived V1 + FPY fixtures.
- **C/D. Historical docs/evaluation** — Phase 2–10B docs and `evaluation/results/*` keep old ids as history.
- **E. Obsolete UI** — hashed ids no longer listed.
- **F. Obsolete generated data** — moved out of `data/synthetic/agent_visible/`.

## Runtime after replacement

- Production selector: one dataset, **Yield Improvement V2**, then lots LOT 001–005.
- `GET /api/datasets` does not return `ds_*`, `ds_mon_*`, or `case_01`.
- Optional `?lot_id=L001` filters analysis through the existing engines (no client-side FPY recompute).
- V1 `--all-core` / `--monitoring` generate into the fixture archive, not the production selector.
