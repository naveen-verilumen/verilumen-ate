# Yield Improvement V2 — Dataset Structure and Data Split

This document describes the dataset the Yield Improvement Agent actually receives today. Every count, column, and formula below was checked against the current V2 files and the code that reads them.

Inspection date of the repository clock: 2026-09-29. The timestamps inside the data use a synthetic clock that starts at 2026-11-01. Those are data timestamps, not the inspection date.

## How to read this document

| Reader | Start here |
| --- | --- |
| Semiconductor / test engineer | Hierarchy, lot/wafer/die, tests, parameters, FPY, Pareto |
| ML engineer | ML dataset, target, LOLO split, leakage |
| Developer | File inventory, which module loads which file, derived vs persisted |
| Manager | “What the agent sees”, verified summary at the end |

Three boundaries matter throughout:

1. **Persisted agent-visible files** live in `data/synthetic/agent_visible/yi_synthetic_v2/`.
2. **Derived results** (FPY, Pareto, detector inputs, ML rows) are calculated in memory. They are not saved as extra V2 tables.
3. **Hidden evaluation data** lives outside that folder. Values that identify planted scenarios are omitted from this document on purpose.

---

## 1. Active dataset

| Item | Verified value |
| --- | --- |
| Display name | Yield Improvement V2 |
| Dataset id | `yi_synthetic_v2` |
| Dataset version | `yi_synth_v2` |
| Dataset type | `SYNTHETIC` |
| Product | `DEV_A` |
| Step | `WS_SORT` (wafer sort) |
| Path | `data/synthetic/agent_visible/yi_synthetic_v2/` |
| Generator config | `configs/synthetic_v2.yaml` |
| Test catalog overlay | `configs/v2_test_catalog.yaml` (display names only; see [YIELD_IMPROVEMENT_V2_TEST_CATALOG.md](YIELD_IMPROVEMENT_V2_TEST_CATALOG.md)) |
| Generator | `src/yield_improvement/synthetic/v2_generator.py` |
| Production selector | `ACTIVE_DATASET_ID = "yi_synthetic_v2"` in `src/yield_improvement/api/service.py` |
| Directory root used by the API | `data/synthetic/agent_visible/` from `active_synthetic_dir()` |

The manifest at `data/synthetic/agent_visible/yi_synthetic_v2/manifest.json` records:

| Field | Value |
| --- | --- |
| `n_lots` | 5 |
| `n_wafers` | 25 |
| `n_dies` | 2500 |
| `wafers_per_lot` | 5 |
| `dies_per_wafer` | 100 |
| `product_id` | `DEV_A` |
| `created_at` | `2026-11-01T08:00:00Z` |

Those manifest counts match the tables. There is one first-pass row for every die.

Parquet files: **NOT PRESENT**. JSON data tables: **NOT PRESENT** except `manifest.json`.

---

## 2. Data hierarchy

Physical objects and logical keys are not the same thing. `wafer_id` and `die_id` repeat. A wafer is identified by `(lot_id, wafer_id)`. A die is identified by `(lot_id, wafer_id, die_id)`.

```text
GENERATOR CONFIG
configs/synthetic_v2.yaml
        |
        |  v2_generator.py writes agent-visible CSVs
        v
PERSISTED AGENT-VISIBLE FILES
data/synthetic/agent_visible/yi_synthetic_v2/
        |
        |  ingestion/loader.py  ->  canonical models
        v
CANONICAL FACTS USED BY THE AGENT
Lot identity (from die_attempts, and lot id list from lot_metadata)
        |
        v
WAFER   key = (lot_id, wafer_id)     ids W01..W05 repeat on every lot
        |
        v
DIE     key = (lot_id, wafer_id, die_id)    ids D001..D100 repeat on every wafer
        |
        v
ATTEMPT key = attempt_id             one first pass, optional retests
        |
        +----> TEST rows              10 tests per attempt  (test_results.csv)
        |
        +----> PARAMETRIC rows        8 measurements per attempt
        |
        v
DERIVED IN MEMORY, NOT STORED AS V2 TABLES
FPY and FPY loss          yield_analysis/fpy.py
Primary-failure Pareto    yield_analysis/attribution.py
Detector context          detectors/population.py
ML frame + target         ml/dataset.py
ML features               ml/features.py
LOLO folds                ml/split.py
        |
        v
HYPOTHESES and INVESTIGATION
hypotheses/composer.py -> opportunity -> validation -> reporting
        |
        v
DASHBOARD
"Where is yield lost?" reads the primary-failure Pareto from the report

HIDDEN EVALUATION FILES  (not on the path above)
evaluation/ground_truth/synthetic_v2/
```

| Layer | What it is | Persisted? |
| --- | --- | --- |
| Physical lot / wafer / die | Manufacturing hierarchy the tables describe | Yes, as columns and small dimension files |
| Attempt / test / measurement | What was recorded at wafer sort | Yes |
| FPY, Pareto, spatial region, equipment fail rates | Calculated | No separate V2 file |
| ML matrix and LOLO folds | Calculated when ML code runs | No separate V2 file |
| Hidden generator scenario | Evaluation only | Separate JSON, not in the agent folder |

---

## 3. Dataset inventory

Every file in `data/synthetic/agent_visible/yi_synthetic_v2/`:

| File | Format | Purpose | Grain | Rows | Columns | Key columns | Used by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `manifest.json` | JSON | Dataset label and declared counts | dataset | 1 object | 11 keys | `dataset_id` | API dataset list |
| `die_attempts.csv` | CSV | One test attempt on one die | die-attempt | 2,560 | 27 | `attempt_id` | FPY, detectors, ML, dashboard |
| `test_results.csv` | CSV | Each catalog test on an attempt | attempt-test | 25,600 | 11 | `attempt_id` + `test_id` | FPY attribution, sequence and correlation detectors. Loaded by ML and then ignored for features and for the target |
| `parametric_measurements.csv` | CSV | Limit measurements on an attempt | attempt-parameter | 20,480 | 16 | `attempt_id` + `parameter_name` | Parametric and near-limit detectors. ML reads the file, then drops these parameter names (see ML section) |
| `lot_metadata.csv` | CSV | Lot header | lot | 5 | 8 | `lot_id` | API lot list (`lot_id` and display name only) |
| `lots.csv` | CSV | Same bytes as `lot_metadata.csv` | lot | 5 | 8 | `lot_id` | API fallback if `lot_metadata.csv` is missing. Identical copy |
| `wafer_metadata.csv` | CSV | Wafer header | lot-wafer | 25 | 9 | `lot_id` + `wafer_id` | **Not loaded** by FPY, detectors, ML, or the report builder |
| `wafers.csv` | CSV | Same bytes as `wafer_metadata.csv` | lot-wafer | 25 | 9 | `lot_id` + `wafer_id` | **Not loaded** by the analysis path. Identical copy |
| `parts.csv` | CSV | Die master | die | 2,500 | 11 | `lot_id` + `wafer_id` + `die_id` | **Not loaded** by the analysis path |
| `equipment.csv` | CSV | Equipment catalog | equipment asset | 8 | 5 | `equipment_id` | **Not loaded** by the analysis path. The agent sees equipment ids on `die_attempts.csv` |

`lots.csv` and `lot_metadata.csv` are identical (5 rows, same columns, same values). `wafers.csv` and `wafer_metadata.csv` are identical (25 rows).

No other CSV, Parquet, or JSON table belongs to this dataset folder.

---

## 4. Lot data

There are **5 lots**. Stored ids are `L001` … `L005`. The API displays them as LOT 001 … LOT 005 (`display_lot_name` in `api/service.py`). The string `LOT 001` is **not** stored in the CSV.

Each lot file row has:

| Column | Example (L001) | Meaning |
| --- | --- | --- |
| `lot_id` | `L001` | Lot id |
| `product_id` | `DEV_A` | Product |
| `step_id` | `WS_SORT` | Wafer sort |
| `start_timestamp` | `2026-11-01T08:00:00Z` | Earliest die timestamp on the lot |
| `end_timestamp` | `2026-11-01T21:14:15Z` | Latest first-pass die timestamp on the lot |
| `start_ts` | same as `start_timestamp` | Duplicate of the start time |
| `quantity_declared` | `500` | Die count on the lot (5 wafers × 100) |
| `hold_flag` | `false` | All five lots |

Not stored on the lot row: yield, equipment assignment, temperature, humidity, process recipe, chamber, or a lot-level fail rate. Those are either on the die attempt or only exist after FPY is calculated.

Lot yield below is **derived** from first-pass rows in `die_attempts.csv` (`attempt_number = 1`). It is not a column in `lots.csv`.

| Lot id | Display | Dies | Wafers | First-pass pass | First-pass fail | FPY | FPY loss | Retest attempt rows | First timestamp | Last first-pass timestamp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L001 | LOT 001 | 500 | W01–W05 | 467 | 33 | 0.9340 | 0.0660 | 10 | 2026-11-01T08:00:00Z | 2026-11-01T21:14:15Z |
| L002 | LOT 002 | 500 | W01–W05 | 451 | 49 | 0.9020 | 0.0980 | 9 | 2026-11-03T08:00:00Z | 2026-11-03T21:14:15Z |
| L003 | LOT 003 | 500 | W01–W05 | 462 | 38 | 0.9240 | 0.0760 | 6 | 2026-11-05T08:00:00Z | 2026-11-05T21:14:15Z |
| L004 | LOT 004 | 500 | W01–W05 | 403 | 97 | 0.8060 | 0.1940 | 25 | 2026-11-07T08:00:00Z | 2026-11-07T21:14:15Z |
| L005 | LOT 005 | 500 | W01–W05 | 466 | 34 | 0.9320 | 0.0680 | 10 | 2026-11-09T08:00:00Z | 2026-11-09T21:14:15Z |

FPY = first-pass passes / 500. Overall first-pass FPY is 2,249 / 2,500 = **0.8996**. Overall FPY loss is 251 / 2,500 = **0.1004**.

Equipment is **not** constant for a lot. Every lot contains testers T01, T02, and T03. First-pass tester counts:

| Lot | T01 | T02 | T03 |
| --- | --- | --- | --- |
| L001 | 193 | 176 | 131 |
| L002 | 209 | 161 | 130 |
| L003 | 219 | 167 | 114 |
| L004 | 235 | 156 | 109 |
| L005 | 196 | 187 | 117 |

Planted lot roles are evaluation-only and are not listed here.

---

## 5. Wafer data

| Check | Result |
| --- | --- |
| Wafers per lot | 5 |
| Total lot-wafer pairs | 25 |
| Wafer ids | `W01`, `W02`, `W03`, `W04`, `W05` |
| Does `wafer_id` alone identify a wafer? | No. `W01` exists on all five lots |
| Relationship | `lot_id` + `wafer_id` |
| Dies per wafer | 100 on every wafer |
| `wafer_sequence` / `slot` | 1 through 5, matching W01 through W05 |
| `process_tool_id` | `TOOL-A` on all 25 wafers |
| `process_chamber_id` | Present, empty on all 25 wafers |

Wafer header columns: `lot_id`, `wafer_id`, `wafer_sequence`, `slot`, `process_tool_id`, `process_chamber_id`, `start_timestamp`, `end_timestamp`, `start_ts`.

The analysis path does not load `wafers.csv`. Wafer comparisons in the detectors use `wafer_id` on the first-pass die attempt. `process_tool_id` is therefore **not** an input to FPY, detectors, or ML.

Wafer FPY below is derived from first-pass attempts. Each wafer has 100 eligible dies.

```text
L001
├── W01  94 pass / 100   FPY 0.94
├── W02  94 pass / 100   FPY 0.94
├── W03  94 pass / 100   FPY 0.94
├── W04  89 pass / 100   FPY 0.89
└── W05  96 pass / 100   FPY 0.96

L002
├── W01  0.90
├── W02  0.88
├── W03  0.88
├── W04  0.93
└── W05  0.92

L003
├── W01  0.94
├── W02  0.91
├── W03  0.91
├── W04  0.93
└── W05  0.93

L004
├── W01  0.94
├── W02  0.91
├── W03  0.89
├── W04  0.74
└── W05  0.55

L005
├── W01  0.94
├── W02  0.92
├── W03  0.93
├── W04  0.92
└── W05  0.95
```

L004 is the only lot whose wafer FPY falls steadily from W01 to W05. That pattern is visible in the attempt timestamps and pass/fail flags. This document does not state a planted cause for it.

---

## 6. Die data

One die is one coordinate on one wafer of one lot.

| Check | Result |
| --- | --- |
| Total dies | 2,500 |
| Dies per wafer | 100 |
| Dies per lot | 500 |
| Die ids | `D001` through `D100` |
| Die id globally unique? | **No.** Each id appears 25 times (once per wafer) |
| Die key | `(lot_id, wafer_id, die_id)` |
| `parts.csv` rows | 2,500, one per die key |
| Coordinates | `x` and `y` integers **1 through 10** |
| Origin | 1, not 0 |
| Grid | Every wafer contains each `(x, y)` from (1, 1) through (10, 10) exactly once |
| Id order | `y` is the outer loop, `x` is the inner loop. `D001` is (1, 1). `D002` is (2, 1). `D011` is (1, 2). `D100` is (10, 10) |

`site` on the die is `(x - 1) % 2`, so odd `x` has site `0` and even `x` has site `1`. Site is constant for a die, including retests.

Actual first row of the grid, from `die_attempts.csv`:

| Field | Value |
| --- | --- |
| `lot_id` | `L001` |
| `wafer_id` | `W01` |
| `die_id` | `D001` |
| `x` | `1` |
| `y` | `1` |
| `site` | `0` |
| `product_id` | `DEV_A` |
| `step_id` | `WS_SORT` |
| `part_class` | `PRODUCTION` |
| `attempt_id` | `E-L001-W01-D001-1` |
| `attempt_number` | `1` |
| `tester_id` | `T01` |
| `probe_card_id` | `PC02` |
| `prober_id` | `PR01` |
| `temperature_c` | `28.32` |
| `voltage_v` | `0.7958` |
| `timestamp` | `2026-11-01T08:00:00Z` |
| `pass_fail` | `FAIL` |
| `disposition` | `FAIL` |
| `failure_code` | `SHORTS` |
| `sbin` | `10` |
| `hbin` | `5` |
| `abort_flag` | `false` |
| `is_retest` | `false` |
| `is_rework` | `false` |
| `record_status` | `VALID` |

A full multi-attempt die is in section 29.

---

## 7. Parameter dictionary

Columns that exist in the V2 files, plus fields the code derives and does not store. If a name is absent from both the files and the derivation path, it is marked **NOT PRESENT**.

### A. Identity

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `dataset_id` | string | `yi_synthetic_v2` | Dataset id | dataset | Raw (manifest) | API selection |
| `dataset_version` | string | `yi_synth_v2` | Generator version label | dataset | Raw (manifest) | Manifest only |
| `display_name` | string | Yield Improvement V2 | UI name | dataset | Raw (manifest) | API |
| `dataset_type` | string | `SYNTHETIC` | Synthetic flag | dataset | Raw (manifest) | API |
| `product_id` | string | `DEV_A` | Product | attempt, lot, part | Raw | Population check (one product) |
| `step_id` | string | `WS_SORT` | Process step | attempt, lot | Raw | Population check |
| `lot_id` | string | `L001` | Lot | lot and below | Raw | Grouping, LOLO split key. Not an ML feature |
| `wafer_id` | string | `W01` | Wafer id within a lot | wafer and below | Raw | Grouping. Not an ML feature |
| `die_id` | string | `D049` | Die id within a wafer | die and below | Raw | Grouping. Not globally unique. Not an ML feature |
| `attempt_id` | string | `E-L001-W01-D049-1` | One attempt | attempt | Raw. Format `E-{lot}-{wafer}-{die}-{n}` | Join key. Not an ML feature |
| `test_id` | string | `T004` | Catalog test | attempt-test | Raw | Pareto key and test analysis. Not an ML feature |
| `parameter_name` | string | `IDDQ` | Measurement name | attempt-parameter | Raw | Parametric detectors |
| `parameter` | string | `IDDQ` | Duplicate of `parameter_name` | attempt-parameter | Raw copy | Not read by the loader. Loader uses `parameter_name` |
| `equipment_id` | string | `T01` | Catalog id | equipment file | Raw | Not loaded by analysis |
| `part_class` | string | `PRODUCTION` | Eligibility class | attempt, part | Raw | FPY eligibility. Allowed ML input, but `build_dataset` does not copy it |

`attempt_id` as a separate business object beyond this string: the string is the id. There is no second attempt-id column.

### B. Location / spatial

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `x` | int | `9` | Column, 1–10 | die | Raw | Maps, ML `die_x` |
| `y` | int | `5` | Row, 1–10 | die | Raw | Maps, ML `die_y` |
| `site` | int | `0` or `1` | `(x - 1) % 2` | die | Raw (generated from `x`) | ML numeric feature |
| `die_x`, `die_y` | float | | Copies of `x`, `y` | ML row | Derived in `ml/features.py` | ML |
| `normalized_x`, `normalized_y` | float | | Min-max using the **training** fold | ML row | Derived | ML |
| `radial_distance` | float | | `hypot(x, y)` | ML row / detector | Derived | ML and spatial detector |
| `edge_distance` | float | | training max radius minus `hypot(x, y)` | ML row | Derived | ML |
| `spatial_region` | string | `EDGE`, `CENTER`, `OTHER` | Training radius quantiles | ML row | Derived | ML |
| `wafer_sequence`, `slot` | int | `1`–`5` | Wafer order in the lot | wafer file | Raw | Not loaded by analysis |

`normalized_x`, `normalized_y`, `radial_distance`, `edge_distance`, and `spatial_region` are **NOT PRESENT** in the CSV files.

### C. Attempt / retest

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `attempt_number` | int | `1`, `2`, `3` | Attempt order | attempt | Raw | First-pass selection |
| `is_first_attempt` | bool | `true` / `false` | True only on attempt 1 | attempt | Raw | FPY also treats `attempt_number == 1` as first pass |
| `is_retest` | bool | `false` on attempt 1 | True on attempts 2 and 3 | attempt | Raw | Excluded from ML features |
| `is_rework` | bool | `false` on every row | Rework flag | attempt, part | Raw | FPY exclusion if true. None are true |
| `record_status` | string | `VALID` | Row status | attempt | Raw | `REJECT` rows are skipped. None are REJECT |
| `is_engineering` | bool | `false` | On `parts.csv` only | die | Raw | Not loaded by analysis |
| `is_calibration` | bool | `false` | On `parts.csv` only | die | Raw | Not loaded by analysis |

### D. First-pass / yield

These are **not columns**. `calculate_fpy` in `yield_analysis/fpy.py` produces them.

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `first_pass_disposition` | PASS/FAIL | `FAIL` | Disposition of the first-pass attempt | eligible die | Derived | FPY numerator and ML target |
| `final_disposition` | PASS/FAIL | `PASS` | Latest attempt that has a disposition | eligible die | Derived | Final yield and retest recovery. Not the FPY numerator |
| `fpy_counts_as` | PASS/FAIL | `FAIL` | Same as first-pass disposition | eligible die | Derived | FPY |
| `fpy` | float | `0.8996` | Passes / eligible | population | Derived | Dashboard KPI |
| `fpy_loss` | float | `0.1004` | Fails / eligible | population | Derived | Dashboard KPI |
| `final_yield` | float | `0.9192` | Final passes / eligible | population | Derived | Reported beside FPY |
| `retest_recovery` | float | `0.1952` | First-fail dies that later pass / first-fail dies | population | Derived | Report |
| `first_pass_fail` | 0/1 | `1` | ML target | eligible die | Derived | ML label. Not a file column |

### E. Test

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `test_id` | string | `T001` | Catalog id | attempt-test | Raw | Pareto |
| `sequence_index` | int | `1`–`10` | Program order | attempt-test | Raw | Primary-fail fallback and sequence detector. Denied as an ML feature |
| `test_pass_fail` | string | `PASS`, `FAIL`, `NOT_EXECUTED` | Test result | attempt-test | Raw | Attribution. `INVALID` is allowed by the loader and does not occur |
| `pass_fail` | string | same as `test_pass_fail` | Duplicate column on the test file | attempt-test | Raw copy | Loader uses `test_pass_fail` |
| `failure_code` | string | `CONTINUITY` or blank | Code when the test failed | attempt-test | Raw | Taxonomy |
| `is_first_fail` | string | `true`, `false`, or blank | Marks the earliest failed test | attempt-test | Raw | Primary-failure selection |
| `timestamp` | string | attempt time | Copied from the die attempt | attempt-test | Raw | Not loaded into the `TestResult` model |

### F. Failure

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `pass_fail` | string | `FAIL` | Attempt result | attempt | Raw | FPY disposition. Denied as an ML feature |
| `disposition` | string | `FAIL` | Same value as `pass_fail` on every V2 row | attempt | Raw | Denied as an ML feature. FPY prefers `pass_fail` when it is PASS or FAIL |
| `sbin` | int | `9` | Software bin | attempt | Raw | Bin map if `pass_fail` is missing. Denied as an ML feature |
| `hbin` | int | `1` or `5` | Hardware bin. 1 pass, 5 fail | attempt | Raw | Bin map fallback. Denied as an ML feature |
| `failure_code` | string | `CONTACT` or blank | Attempt fail code. Blank on every pass | attempt | Raw | Taxonomy if test rows are missing. Denied as an ML feature |
| `primary_failure_key` | string | `T001` | Selected test id | failing die | Derived | Pareto. See the die-id collision warning |
| `primary_failure_code` | string | `CONTINUITY` | Code of that test | failing die | Derived | Pareto |
| `taxonomy_code` | string | `CONTACT.CONTINUITY` | Family.detail from `configs/bin_map.yaml` | failing die | Derived | Evidence labels |
| `selection_method` | string | `is_first_fail` | How the primary was chosen | failing die | Derived | All 251 current primaries use this method |

### G. Parametric measurements

| Parameter | Type | Unit in file | Limits in file | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `IDDQ` | float | `uA` | upper 50 | attempt | Raw | Detectors. Not an ML feature under the current allowlist |
| `VMIN` | float | `V` | upper 0.85 | attempt | Raw | Detectors. Not an ML feature |
| `VMAX` | float | `V` | lower 1.05 | attempt | Raw | Detectors. Not an ML feature |
| `VDD` | float | `V` | 0.72 to 0.88 | attempt | Raw | Detectors. Not an ML feature |
| `SUPPLY_CURRENT` | float | `mA` | upper 120 | attempt | Raw | Detectors. Not an ML feature |
| `CONTACT_RESISTANCE` | float | `ohm` | upper 2.5 | attempt | Raw | Detectors. Not an ML feature |
| `INTERCONNECT_RESISTANCE` | float | `ohm` | upper 8 | attempt | Raw | Detectors. Not an ML feature |
| `ON_RESISTANCE` | float | `ohm` | upper 15 | attempt | Raw | Detectors. Not an ML feature |
| `measurement` | float | | The numeric result | attempt-parameter | Raw | Loader |
| `value` | float | | Identical to `measurement` on all 20,480 rows | attempt-parameter | Raw copy | Not read by the loader |
| `unit` | string | | Unit above | attempt-parameter | Raw | Limits context |
| `lower_limit` | float or blank | | Blank means no lower spec | attempt-parameter | Raw | Near-limit and limit fail |
| `upper_limit` | float or blank | | Blank means no upper spec | attempt-parameter | Raw | Near-limit and limit fail |
| `condition_id` | string | `NONE` on every row | Test condition id | attempt-parameter | Raw | No extra conditions exist |
| `pass_fail` | string | `PASS` or `FAIL` | Limit check for that parameter | attempt-parameter | Raw | Not copied into ML |

Names that the ML allowlist expects and that this dataset does **not** contain: `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, `TEST_TIME_MS`. **NOT PRESENT** in V2.

### H. Environment

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `temperature_c` | float | `24.696` | Chuck / test temperature, degrees C | attempt. Copied onto that attempt’s parametric rows | Raw | Temperature detector and ML |
| `voltage_v` | float | `0.8009` | Supply set-point, volts | attempt. Also copied onto parametric rows | Raw | ML numeric feature |
| humidity | | | | | | **NOT PRESENT** |
| other environment fields | | | | | | **NOT PRESENT** |

### I. Equipment

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `tester_id` | string | `T01` | Tester used for the die | die (same on retests) | Raw | Equipment detector, ML |
| `probe_card_id` | string | `PC03` | Probe card | die | Raw | Contact detector, ML |
| `prober_id` | string | `PR01` | Prober | die | Raw | ML categorical feature. No prober detector |
| `equipment_type` | string | `TESTER` | Catalog type | equipment file | Raw | Not loaded by analysis |
| `vendor`, `model` | string | `ADV`, `T-A` | Catalog text | equipment file | Raw | Not loaded by analysis |
| `parent_equipment_id` | string | empty | Parent asset | equipment file | Raw, always blank | Not loaded |
| `tester_fail_rate` | float | | Mean training-label fail rate of that tester | ML row | Derived in `FeatureBuilder` | ML |
| `probe_fail_rate` | float | | Mean training-label fail rate of that probe card | ML row | Derived | ML |
| equipment status | | | | | | **NOT PRESENT** |

### J. Time

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `timestamp` | ISO-8601 Z | `2026-11-01T08:36:00Z` | Attempt time, second resolution | attempt | Raw | Order, temporal detector, ML |
| `start_timestamp`, `end_timestamp`, `start_ts` | ISO-8601 Z | | Lot or wafer window | lot or wafer file | Raw | Not used by FPY |
| `timestamp_epoch` | float | | Seconds after the training-fold minimum timestamp | ML row | Derived | ML numeric feature |
| `created_at` | ISO-8601 Z | `2026-11-01T08:00:00Z` | Manifest clock | dataset | Raw | Manifest |

### K. Derived parameters

See section 19. They are calculated by code and are not CSV columns.

### L. Metadata

| Parameter | Type | Example | Meaning | Grain | Raw / derived | Used for |
| --- | --- | --- | --- | --- | --- | --- |
| `quantity_declared` | int | `500` | Dies declared on the lot | lot | Raw | Lot file only |
| `hold_flag` | bool | `false` | Lot hold | lot | Raw | Lot file only. Not read by FPY |
| `n_lots`, `n_wafers`, `n_dies`, `wafers_per_lot`, `dies_per_wafer` | int | | Declared size | manifest | Raw | API display |

---

## 8. Identity and relationships

```text
dataset yi_synthetic_v2
    lot_id                         L001 is unique
        (lot_id, wafer_id)         W01 is NOT unique across lots
            (lot_id, wafer_id, die_id)   D001 is NOT unique across wafers
                attempt_id         globally unique
                    (attempt_id, test_id)
                    (attempt_id, parameter_name)
```

| Id | Role | ML |
| --- | --- | --- |
| `lot_id` | Business lot. LOLO group key | On the ML frame. Not a model feature |
| `wafer_id` | Business wafer id, only unique with `lot_id` | On the ML frame. Not a feature and not the split key |
| `die_id` | Business die id, only unique with lot and wafer | On the ML frame. Not a feature |
| `attempt_id` | Relational key to tests and parameters | On the ML frame so attributes can be joined. Not a feature |
| `test_id` | Catalog id, shared by every die | Not on the ML frame |
| `parameter_name` | Catalog id, shared by every attempt | Not on the ML frame as a column. Values would be pivoted by name. V2 names are not in the pivot list |

There is no separate `test_execution_id`. The test row key is `(attempt_id, test_id)`.

Physical die identity is `(lot_id, wafer_id, die_id)`. `die_id` is reused on every wafer, so a primary-failure lookup that uses `die_id` alone attributes the wrong test and failure code. The FPY copy of the primary failure uses the physical-die triple. FPY totals, eligibility, first-pass labels, retest handling, and Pareto counts are unchanged by that key.

---

## 9. First-pass yield

Implementation: `src/yield_improvement/yield_analysis/fpy.py`. Policy: `configs/fpy_policy.yaml` (`yi_fpy_v1`, abort policy `FIRST_PASS_ABORT_IS_FAIL`).

```text
FPY      = n_first_pass_pass / n_fpy_eligible
FPY loss = n_first_pass_fail / n_fpy_eligible
invariant: n_fpy_eligible = n_first_pass_pass + n_first_pass_fail
```

On this dataset the engine returns status `OK`:

| Quantity | Value |
| --- | --- |
| Eligible dies | 2,500 |
| First-pass pass | 2,249 |
| First-pass fail | 251 |
| Excluded | 0 |
| FPY | 2,249 / 2,500 = **0.8996** |
| FPY loss | 251 / 2,500 = **0.1004** |
| Final yield | 2,298 / 2,500 = **0.9192** |
| Dies with at least one retest | 57 |
| Retest rate of eligible | 57 / 2,500 = 0.0228 |
| Retest recovery | 49 / 251 = 0.1952 |
| Invariant | holds |
| Errors / warnings | 0 / 0 |

Final yield counts a die that failed first and passed on a later attempt as a final pass. FPY still counts that die as a fail.

### Eligibility rules as they apply to V2

| Rule | V2 fact |
| --- | --- |
| Eligible die | `part_class = PRODUCTION`, not rework, has a first attempt, has a timestamp, disposition resolves to PASS or FAIL |
| First attempt | `attempt_number == 1` or `is_first_attempt` is true. Both agree on every row |
| Pass / fail | `pass_fail` is `PASS` or `FAIL` on every row, so the bin map is not needed to decide disposition |
| Retest | Attempts 2 and 3 do not replace attempt 1. The die stays in the denominator |
| Abort | `abort_flag` is `false` on all 2,560 rows. Policy would count a first-pass abort as FAIL. Zero aborts occur |
| Rework | `is_rework` is `false` on all rows. `part_class` is never `REWORK` |
| Engineering | `part_class` is never `ENGINEERING`. `parts.csv` `is_engineering` is `false` and that file is not loaded |
| Calibration | No `CALIBRATION` rows. `is_calibration` is `false` on `parts.csv` |
| Missing disposition | 0 rows |
| Missing outcome | 0 rows |
| `record_status = REJECT` | 0 rows |
| Duplicate `attempt_id` | 0 |
| Ambiguous duplicate | 0 exclusions |

Example from the file `L001 / W01 / D049`:

| Attempt | `pass_fail` | What FPY does |
| --- | --- | --- |
| 1 | FAIL | This is the first pass. The die **counts as FAIL** |
| 2 | PASS | Changes final disposition to PASS. Does not change FPY |

So FPY for this die is FAIL. Final yield for this die is PASS.

---

## 10. Attempt data

`die_attempts.csv` has 2,560 rows.

| `attempt_number` | Rows | `is_first_attempt` | `is_retest` |
| --- | --- | --- | --- |
| 1 | 2,500 | true | false |
| 2 | 57 | false | true |
| 3 | 3 | false | true |

| Field | Observed |
| --- | --- |
| `pass_fail` | PASS 2,298 / FAIL 262 across all attempts. First pass only: PASS 2,249 / FAIL 251 |
| `disposition` | Identical to `pass_fail` on every row |
| `abort_flag` | `false` on every row |
| `is_rework` | `false` on every row |
| `part_class` | `PRODUCTION` on every row |
| `record_status` | `VALID` on every row |
| `failure_code` | Blank on all 2,298 passes. On fails, one of the 10 codes in section 16 |
| `timestamp` | Attempt 1 uses the die time. Each later attempt is 30 seconds later (`v2_generator.py`) |
| Equipment, `x`, `y`, `site`, temperature, voltage | Copied from attempt 1 onto retests. A die has exactly one tester, one probe card, and one prober |

A die can have 1, 2, or 3 attempts. Attempt 3 exists only when attempt 2 is still a fail. 57 dies were retested. 3 of those have a third attempt. 49 dies that failed first pass end as PASS. 202 eligible dies are still FAIL after the last attempt (2,500 − 2,298).

There is no separate attempt file. Multiple attempts are additional rows that share `(lot_id, wafer_id, die_id)` and differ by `attempt_id`.

---

## 11. Test data

Catalog size: **10 tests**. Every attempt has all 10 rows (2,560 × 10 = 25,600). Tests are not omitted from the file. A test can be `NOT_EXECUTED`.

Machine-readable IDs remain `T001`–`T010`. The generator does not define a separate `test_name`. Dashboard names copy the generator program-slot `failure_code` from `configs/synthetic_v2.yaml`. See [YIELD_IMPROVEMENT_V2_TEST_CATALOG.md](YIELD_IMPROVEMENT_V2_TEST_CATALOG.md).

There is no test-name column in the CSVs. Display names are mapped at API/dashboard overlay time. The failure code below is still the generator taxonomy stored on FAIL rows.

| Test id | Display name (overlay) | Type (overlay) | Failure code on FAIL | `sequence_index` | Rows | PASS | FAIL | NOT_EXECUTED | Software bin when this code is the attempt bin |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T001 | CONTINUITY | CONTINUITY | CONTINUITY | 1 | 2,560 | 2,543 | 17 | 0 | 9 |
| T002 | OPENS | OPENS | OPENS | 2 | 2,560 | 2,530 | 14 | 16 | 9 |
| T003 | SHORTS | SHORTS | SHORTS | 3 | 2,560 | 2,520 | 10 | 30 | 10 |
| T004 | CONTACT | CONTACT | CONTACT | 4 | 2,560 | 2,427 | 96 | 37 | 12 |
| T005 | IDDQ | IDDQ | IDDQ | 5 | 2,560 | 2,387 | 45 | 128 | 8 |
| T006 | VMIN | VMIN | VMIN | 6 | 2,560 | 2,345 | 53 | 162 | 13 |
| T007 | VMAX | VMAX | VMAX | 7 | 2,560 | 2,332 | 22 | 206 | 13 |
| T008 | LEAKAGE | LEAKAGE | LEAKAGE | 8 | 2,560 | 2,323 | 17 | 220 | 8 |
| T009 | FUNCTIONAL | FUNCTIONAL | FUNCTIONAL | 9 | 2,560 | 2,310 | 23 | 227 | 11 |
| T010 | SCAN | SCAN | SCAN | 10 | 2,560 | 2,298 | 24 | 238 | 11 |

Display names copy the generator program slot. This overlay does **not** invent additional physical test types.

A passing attempt has all 10 tests `PASS`. A failing attempt marks the earliest failed sequence with `is_first_fail = true`. Tests after that sequence are `NOT_EXECUTED` unless the generator also listed that later test as a fail. 59 attempts contain more than one `FAIL` test (one `is_first_fail = true` and one `is_first_fail = false`). `is_first_fail` counts: blank 25,279, `true` 262, `false` 59. Those 262 `true` flags are one per failing attempt, including retest fails.

`INVALID` test results: **NOT PRESENT**.

Stop-on-fail is partial. Later tests are censored with `NOT_EXECUTED`, and a second failed test can still be stored after the first fail. The correlation detector’s own comment states that stop-on-fail censors later tests.

The canonical `TestResult` model keeps `attempt_id`, `test_id`, `test_pass_fail`, `sequence_index`, `is_first_fail`, and `failure_code`. CSV columns `lot_id`, `wafer_id`, `die_id`, `pass_fail`, and `timestamp` are in the file and are not copied onto that model.

PRIMARY_FAILURE Pareto still keys on `test_id` (for example `T004`). The dashboard displays `T004 — CONTACT` without changing die counts or FPY.

---

## 12. Parametric data

Eight parameters. Every attempt has all eight (2,560 × 8 = 20,480). Retest rows repeat the first-attempt numbers: 480 retest measurement comparisons match the first attempt exactly, including temperature and voltage. Statistics below use the **first-pass attempt** (2,500 rows per parameter), which is the grain detectors keep.

Limit rule in the generator and in FPY policy: fail if `measurement > upper_limit` or `measurement < lower_limit`. A value equal to the limit is a pass.

| Parameter | Unit | Lower | Upper | n | Missing | Min | Max | Mean | Median | Std (sample) | Limit fails |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IDDQ` | uA | none | 50 | 2,500 | 0 | 10.7726 | 63.4185 | 33.6653 | 33.1880 | 6.9642 | 29 |
| `VMIN` | V | none | 0.85 | 2,500 | 0 | 0.3438 | 1.0060 | 0.6362 | 0.6331 | 0.0896 | 28 |
| `VMAX` | V | 1.05 | none | 2,500 | 0 | 1.0420 | 1.3113 | 1.1809 | 1.1818 | 0.0401 | 1 |
| `VDD` | V | 0.72 | 0.88 | 2,500 | 0 | 0.7367 | 0.8587 | 0.8002 | 0.8003 | 0.0195 | 0 |
| `SUPPLY_CURRENT` | mA | none | 120 | 2,500 | 0 | 42.9200 | 105.6990 | 77.7577 | 77.8743 | 9.7011 | 0 |
| `CONTACT_RESISTANCE` | ohm | none | 2.5 | 2,500 | 0 | 0.2885 | 2.2600 | 1.1613 | 1.1430 | 0.2891 | 0 |
| `INTERCONNECT_RESISTANCE` | ohm | none | 8 | 2,500 | 0 | 1.9468 | 6.4241 | 4.2116 | 4.2139 | 0.6851 | 0 |
| `ON_RESISTANCE` | ohm | none | 15 | 2,500 | 0 | 3.5869 | 13.5131 | 8.4700 | 8.4866 | 1.4060 | 0 |

File: `parametric_measurements.csv`. All-attempt rows (including copied retests) have the same min/max for these parameters. All-attempt limit-fail counts are IDDQ 37, VMIN 37, VMAX 1, and 0 for the others, because retests copy the out-of-limit values.

`CONTACT_RESISTANCE` never crosses 2.5 ohm in this file. Its maximum observed value is 2.260 ohm.

---

## 13. Environment data

| Parameter | Unit | Grain | n | Missing | Min | Max | Mean | Median | Std |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `temperature_c` | °C | first-pass attempt | 2,500 | 0 | 17.942 | 89.443 | 32.021 | 25.330 | 19.349 |
| `voltage_v` | V | first-pass attempt | 2,500 | 0 | 0.7669 | 0.8310 | 0.8004 | 0.8003 | 0.0100 |

Source column: `die_attempts.csv`. The same numbers are repeated on `parametric_measurements.csv`. Humidity: **NOT PRESENT**.

The temperature distribution is bimodal in the generator (a nominal cloud around 25 °C and a hot fraction around 85 °C). The agent sees only the resulting `temperature_c` values. 2,142 distinct first-pass temperatures exist at 0.001 °C resolution. The temperature detector groups by the exact formatted value, so nearly every temperature is its own group.

---

## 14. Equipment data

Catalog in `equipment.csv` (not loaded by analysis):

| equipment_id | equipment_type | vendor | model | parent |
| --- | --- | --- | --- | --- |
| T01 | TESTER | ADV | T-A | blank |
| T02 | TESTER | ADV | T-B | blank |
| T03 | TESTER | ADV | T-C | blank |
| PC01 | PROBE_CARD | PCV | PC-A | blank |
| PC02 | PROBE_CARD | PCV | PC-B | blank |
| PC03 | PROBE_CARD | PCV | PC-C | blank |
| PR01 | PROBER | PRB | P-A | blank |
| PR02 | PROBER | PRB | P-B | blank |

Ids actually present on attempts:

| Field | Unique values | All-attempt rows | First-pass rows |
| --- | --- | --- | --- |
| `tester_id` | T01, T02, T03 | 1,081 / 863 / 616 | 1,052 / 847 / 601 |
| `probe_card_id` | PC01, PC02, PC03 | 835 / 873 / 852 | 814 / 856 / 830 |
| `prober_id` | PR01, PR02 | 1,277 / 1,283 | 1,244 / 1,256 |
| `site` | 0, 1 | 1,272 / 1,288 | |

```text
Die (and every attempt of that die)
    ├── tester_id       one of T01, T02, T03
    ├── probe_card_id   one of PC01, PC02, PC03
    ├── prober_id       one of PR01, PR02
    └── site            0 or 1 from x
```

Assignment is chosen per die, then copied to retests. It is not constant for a lot or a wafer. Every wafer contains more than one tester (maximum distinct testers per wafer is 3). No handler, load board, site controller, or equipment-status column exists.

`tester_fail_rate` and `probe_fail_rate` are **not** in the CSV. They are training-fold means of `first_pass_fail`, computed in `ml/features.py`.

---

## 15. Failure data

Attempt-level failure codes on FAIL rows (262 attempts, including retests):

| Code | Attempt rows | In `configs/bin_map.yaml` `failure_code_map`? | Taxonomy if mapped |
| --- | --- | --- | --- |
| CONTACT | 93 | No | `UNKNOWN.UNMAPPED_CODE` |
| VMIN | 42 | Yes | `PARAMETRIC.UNKNOWN` |
| IDDQ | 40 | Yes | `PARAMETRIC.UNKNOWN` |
| CONTINUITY | 17 | Yes | `CONTACT.CONTINUITY` |
| VMAX | 13 | No | `UNKNOWN.UNMAPPED_CODE` |
| OPENS | 13 | No | `UNKNOWN.UNMAPPED_CODE` |
| FUNCTIONAL | 13 | Yes | `FUNCTIONAL.UNKNOWN` |
| SCAN | 12 | Yes | `FUNCTIONAL.SCAN` |
| SHORTS | 10 | No | `UNKNOWN.UNMAPPED_CODE` |
| LEAKAGE | 9 | No | `UNKNOWN.UNMAPPED_CODE` |

Pass rows have a blank `failure_code`. That blank is the pass state, not a missing code.

Software bins observed: 1 (pass, 2,298), 12 (95), 13 (59), 8 (48), 11 (32), 9 (20), 10 (8). Hardware bins: 1 (pass) and 5 (fail). Bin names such as `GOOD` or `IDDQ_FAIL` are in `configs/bin_map.yaml`. They are not columns in the CSV.

### How PRIMARY_FAILURE is selected

`select_primary` in `yield_analysis/attribution.py`, applied only to first-pass attempts whose disposition is FAIL, and only to test rows with `test_pass_fail = FAIL`:

1. If the attempt is an abort and there are no failed tests: key `ABORT`. **Does not occur.**
2. If exactly one failed test has `is_first_fail = true`: that test is primary. Method `is_first_fail`. **This is the method for all 251 first-pass fails.**
3. If more than one test has `is_first_fail = true`: `UNKNOWN_PRIMARY_FAILURE`. **Does not occur.**
4. Else the lowest `sequence_index` among failed tests, if unique.
5. Else a single failed test.
6. Else `UNKNOWN_PRIMARY_FAILURE` / `UNKNOWN.PRIMARY_UNORDERED`.

The attempt’s own `failure_code` matches the earliest failed test’s code on all 262 failing attempts. `sbin` does **not** always match that earliest code. On 20 failing attempts, `sbin` matches a different failed test. The generator sets `failure_code` from the earliest sequence and sets `sbin` from the first id in an unsorted fail list (`v2_generator.py`). FPY does not use `sbin` when `pass_fail` is already PASS or FAIL, so those 20 bins do not change FPY. They can change taxonomy if a caller maps from `sbin` instead of the test code.

### Die-id collision in the per-die copy

Pareto counts are accumulated per failing attempt and sum to 251. Separately, `calculate_fpy` copies the primary onto `DieOutcome` with a dictionary keyed only by `die_id`. Because `D001`–`D100` repeat across wafers, that copy is wrong for **137 of 251** failing dies. Example: `L001 / W01 / D049` has test primary `T001` / `CONTINUITY`, while the copied outcome field says `T004` / `CONTACT`.

The dashboard Pareto uses `primary_fail_pareto`, which is the additive count, not the collided per-die field.

Unmapped codes are not guessed into PROCESS or EQUIPMENT. `configs/taxonomy.yaml` requires `UNKNOWN.UNMAPPED_CODE`.

---

## 16. Spatial data

Persisted spatial columns are only `x` and `y`. Both are integers 1–10. Every coordinate on every wafer is filled.

```text
X increases to the right (1 … 10)
Y increases downward in the map below (1 at the top … 10 at the bottom)

Die number = (y - 1) * 10 + x
D001 = (1, 1) at the top-left
D100 = (10, 10) at the bottom-right
```

First-pass pass/fail for **L001 / W01** (`P` pass, `F` fail). This map is derived from `pass_fail` on attempt 1. It is not a stored image.

```text
y\x  1 2 3 4 5 6 7 8 9 10
 1   F P P P P P P P P P
 2   P P F P P P P P P P
 3   P P P P P P P P P P
 4   P P P P P P P P P P
 5   P P P P P P P P F P
 6   P P P P P P P P P P
 7   P P P P F F P P P P
 8   P P P P P P P P P P
 9   P F P P P P P P P P
10   P P P P P P P P P P
```

| Field | In the CSV? | How it is calculated |
| --- | --- | --- |
| `x`, `y` | Yes | Generated as the 10×10 index |
| `normalized_x` | No | `(x - train_x_min) / train_x_span` in `FeatureBuilder` |
| `normalized_y` | No | same for `y` |
| `radial_distance` | No | `hypot(x, y)` |
| `edge_distance` | No | training maximum radius minus `hypot(x, y)` |
| `spatial_region` | No | ML feature only, unchanged: `EDGE` if radius ≥ training 80th percentile, `CENTER` if radius ≤ training 20th percentile, otherwise `OTHER`. This is not the diagnostic grid region |
| Diagnostic `BORDER` / `INNER` | No | `BORDER` when `x` is the minimum or maximum observed `x`, or `y` is the minimum or maximum observed `y`. `INNER` is every remaining grid position. On this 10×10 grid that is `x` or `y` in {1, 10} |

The diagnostic spatial region is the observed 10×10 grid boundary, not distance from (0, 0) and not a circular wafer. On this dataset `x` and `y` run from 1 to 10, so a border die is one with `x` or `y` equal to 1 or 10. That matches the generator helper `is_edge(x, y, 10, 10)`. Each wafer has 36 border dies and 64 inner dies (900 and 1,600 across 25 wafers). `die_x`, `die_y`, `radial_distance`, and `edge_distance` stay raw measurements. `radial_distance` is still `hypot(x, y)`.

The spatial detector uses `BORDER` and `INNER` when the observed coordinates are a filled integer rectangle whose minimum X and Y are at least 1, which is this 10×10 grid. Centered layouts that include the origin keep the existing radial `EDGE` / `CENTER` / `RING` comparisons, so those scenarios are not reclassified as a grid border. On this dataset the comparison is the grid boundary. It remains a rate difference and a hypothesis input. It does not assign a root cause. Radius thresholds are still recorded and are not the border rule.

`yi_ml_v2` was trained under the previous radius-quantile `spatial_region` (`EDGE` / `CENTER` / `OTHER`) and was not retrained after this correction. The 16-feature contract and the saved artifact are unchanged. A later ML experiment may evaluate the grid-border representation. The ML builder in `ml/features.py` still emits the radius categories.

The generator also has `is_center` (a 4×4 block around the middle). That helper is **not written to any agent-visible column** and is not the diagnostic `INNER` region.

---

## 17. Time data

| Item | Fact |
| --- | --- |
| Column | `timestamp` on attempts, tests, and parametric rows |
| Granularity | 1 second, UTC, format `YYYY-MM-DDTHH:MM:SSZ` |
| First event | `2026-11-01T08:00:00Z` (`L001 / W01 / D001`) |
| Last event | `2026-11-09T21:14:15Z`. This is also the last first-pass timestamp (L005). No retest in the file is later than that stamp |
| Lot spacing | Each lot starts 2 days after the previous lot’s start (`days_per_lot: 2`) |
| Wafer spacing | 3 hours (`hours_per_wafer: 3`) |
| Die spacing | 45 seconds within a wafer (`seconds_per_die: 45`) |
| First-pass order | The 2,500 first-pass timestamps are already sorted in file order |
| Retest time | +30 seconds per extra attempt, same die |

Lots are in calendar order L001, then L002, L003, L004, L005. Wafers inside a lot are in order W01 … W05. Dies inside a wafer follow die-id order.

`timestamp_epoch` is an ML feature (seconds since the earliest timestamp in the **training** fold). The raw timestamp is not one-hot encoded.

The temporal detector (`detectors/temporal.py`) orders lots by the earliest die timestamp and compares early vs late windows, plus a Mann-Kendall test on lot fail rates. Time is therefore used both as an ML feature and as the clock for drift detection.

The generator’s `time` block is what creates this spacing. The dataset does contain a real chronological order across lots. Interpreting a yield trend as a planted process drift is an evaluation question and is not answered here.

---

## 18. Derived data

| Derived field | Formula / logic | Source fields | Used by |
| --- | --- | --- | --- |
| First-pass disposition | First attempt’s `pass_fail` (abort would force FAIL; none do) | `attempt_number`, `pass_fail`, `abort_flag` | FPY, ML target |
| FPY | 2,249 / 2,500 | eligible first-pass dispositions | Dashboard |
| FPY loss | 251 / 2,500 | same | Dashboard |
| Final yield | 2,298 / 2,500 | last disposition | Report |
| Retest recovery | 49 / 251 | first FAIL and final PASS | Report |
| Primary failure | `is_first_fail = true` on the first-pass failed tests | `test_results` | Pareto |
| Taxonomy | `failure_code_map`, else `UNKNOWN.UNMAPPED_CODE` | failure code, `configs/bin_map.yaml` | Pareto labels |
| `radial_distance` | `hypot(x, y)` | `x`, `y` | ML, spatial detector |
| `edge_distance` | train max radius − radius | `x`, `y` | ML |
| `normalized_x`, `normalized_y` | min-max on the training fold | `x`, `y` | ML |
| `spatial_region` | EDGE / CENTER / OTHER from training radius quantiles 0.80 and 0.20. Unchanged in yi_ml_v2 | `x`, `y` | ML feature only |
| Diagnostic BORDER / INNER | outermost observed X/Y versus the remaining grid positions | `x`, `y` | Spatial detector |
| Detector EDGE / CENTER / RING | radius quantiles, kept as radial comparisons and not as the grid border | `x`, `y` | Spatial detector |
| `timestamp_epoch` | unix time minus training minimum | `timestamp` | ML |
| `tester_fail_rate` | mean `first_pass_fail` by `tester_id` on the training lots | tester + training labels | ML |
| `probe_fail_rate` | mean `first_pass_fail` by `probe_card_id` on the training lots | probe card + training labels | ML |
| `die_x`, `die_y` | float cast of `x`, `y` | `x`, `y` | ML |
| Lot FPY, wafer FPY | pass count / 500 or / 100 | first-pass `pass_fail` | This document and any caller that groups FPY |
| `site` | stored, generated as `(x - 1) % 2` | `x` | ML |

`tester_fail_rate` and `probe_fail_rate` are fit inside each training fold (`ml/train.py` fits `FeatureBuilder` on `train_idx` only). They are not global statistics stored on disk.

---

## 19. ML dataset

The ML table is **not a file**. `load_ml_dataset` in `ml/dataset.py` builds it in memory from the agent-visible CSVs. It does not read `evaluation/ground_truth/`.

| Item | Value |
| --- | --- |
| Source | `die_attempts.csv` for rows. `parametric_measurements.csv` is read and then not joined, because none of its names are in `PARAM_NAMES`. `test_results.csv` is loaded and discarded |
| Grain | One row per FPY-eligible die |
| One row is | The first-pass attempt of that die |
| Rows on V2 | **2,500** |
| Target | `first_pass_fail` |
| Positives (fail = 1) | 251 |
| Positive rate | 0.1004 |
| Frame columns before feature build | `lot_id`, `wafer_id`, `die_id`, `attempt_id`, `x`, `y`, `timestamp`, `tester_id`, `probe_card_id`, `prober_id`, `site`, `temperature_c`, `voltage_v` |
| Nulls in that frame | 0 |
| Features emitted by `FeatureBuilder` on V2 | the 16 names below |
| Dedup | One die, one row. Retest attempts are not extra samples |
| Aggregation | Only the two training-set fail rates |

### Features the current builder emits on this dataset

| Feature | Source | Meaning | Type | Used in ML? | Why |
| --- | --- | --- | --- | --- | --- |
| `die_x` | `x` | Column | numeric | Yes | Location |
| `die_y` | `y` | Row | numeric | Yes | Location |
| `normalized_x` | `x` | Training-fold min-max | numeric | Yes | Scale-free location |
| `normalized_y` | `y` | Training-fold min-max | numeric | Yes | Scale-free location |
| `radial_distance` | `x`, `y` | `hypot(x, y)` | numeric | Yes | Radius from (0, 0) |
| `edge_distance` | `x`, `y` | max radius − radius | numeric | Yes | Complement of radius |
| `spatial_region` | `x`, `y` | EDGE / CENTER / OTHER | categorical | Yes | Coarse zone |
| `timestamp_epoch` | `timestamp` | Seconds from training minimum | numeric | Yes | Time |
| `temperature_c` | `temperature_c` | Degrees C | numeric | Yes | Environment |
| `voltage_v` | `voltage_v` | Volts | numeric | Yes | Environment |
| `site` | `site` | 0 or 1 | numeric | Yes | Site index |
| `tester_id` | `tester_id` | T01–T03 | categorical | Yes | Equipment id |
| `probe_card_id` | `probe_card_id` | PC01–PC03 | categorical | Yes | Probe card id |
| `prober_id` | `prober_id` | PR01–PR02 | categorical | Yes | Prober id |
| `tester_fail_rate` | tester + training labels | Training mean fail rate | numeric | Yes | Equipment history inside the training lots |
| `probe_fail_rate` | probe card + training labels | Training mean fail rate | numeric | Yes | Card history inside the training lots |
| `lot_id` | lot | Group key | identity | No | Split only |
| `wafer_id` | wafer | Identity | identity | No | Not a feature |
| `die_id` | die | Identity | identity | No | Not a feature |
| `attempt_id` | attempt | Join key | identity | No | Not a feature |
| `IDDQ`, `VMIN`, `VMAX`, `VDD`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE` | parametric file | Measurements | numeric | **No** | `PARAM_NAMES` in `ml/dataset.py` lists only `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, `TEST_TIME_MS`, which are absent here. The allowlist’s derived-feature list matches those absent names |
| `pass_fail`, `disposition`, `sbin`, `hbin`, `failure_code` | attempt | Outcomes | | No | Denied |
| Test results | test file | Outcomes and sequence | | No | Explicitly unused for the matrix |

Encoding, from `ml/models.py`:

| Kind | Transform | Fit on |
| --- | --- | --- |
| Numeric | median impute, then `StandardScaler` | Training fold only |
| Categorical | most-frequent impute, then `OneHotEncoder(handle_unknown="ignore")` | Training fold only |

V2’s ML frame has no missing values, so the imputers do not change these rows. They remain in the pipeline.

The active artifact `artifacts/ml/yi_ml_v1/feature_list.json` lists the same 16 names. That artifact’s `metadata.json` records `n_samples` 784 and an `analysis_id` that is not `yi_synthetic_v2`. The feature names line up because V2’s parametric columns are dropped. The artifact was not trained on these 2,500 rows. See the verified summary.

---

## 20. ML target

Name: `first_pass_fail`. Built in `build_dataset`:

```text
1  if first_pass_disposition == FAIL
0  if first_pass_disposition == PASS
```

On V2 that is 251 ones and 2,249 zeros.

| Rule | Effect on V2 |
| --- | --- |
| Eligible records | The 2,500 FPY-eligible dies. Exclusions are 0, so every die is a sample |
| Retests | Ignored for the label. A die that fails first and passes later is still 1 |
| Aborts | Would be 1 because `abort_is_first_pass_fail` is true. No aborts exist |
| Excluded classes | ENGINEERING, CALIBRATION, QA_SAMPLE, REWORK, UNKNOWN_NON_PRODUCTION. None are present |
| Missing disposition | Would drop the die. None are missing |
| Test outcome fields in X | Removed. `calculate_fpy` is called with `test_results=None` when the label is built, and test columns are not added to the frame |
| Parametric `pass_fail` | Not in X |

The label is the first-pass fail flag. It is not final yield and it is not “recovered after retest”.

---

## 21. Train / validation / test split

Configuration: `configs/ml.yaml`.

| Setting | Value |
| --- | --- |
| `split.strategy` | `leave_one_lot_out` |
| `split.group_column` | `lot_id` |
| `max_lolo_lots` | 12 |
| `fallback_group_kfold_splits` | 5 |

`make_splits` in `ml/split.py`: if the number of lots is at most 12, use `LeaveOneGroupOut`. V2 has 5 lots, so the strategy that actually runs is **`leave_one_lot_out`**. There is no random row split, no wafer split, and no separate validation lot. Five lots produce five folds. GroupKFold is not used.

Each fold trains on four lots and tests on the held-out lot. The code raises if any lot appears on both sides.

| Fold | Training lots | Test lot | Train dies | Test dies | Train fails (y=1) | Test fails (y=1) | Train passes | Test passes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | L002, L003, L004, L005 | L001 | 2,000 | 500 | 218 | 33 | 1,782 | 467 |
| 2 | L001, L003, L004, L005 | L002 | 2,000 | 500 | 202 | 49 | 1,798 | 451 |
| 3 | L001, L002, L004, L005 | L003 | 2,000 | 500 | 213 | 38 | 1,787 | 462 |
| 4 | L001, L002, L003, L005 | L004 | 2,000 | 500 | 154 | 97 | 1,846 | 403 |
| 5 | L001, L002, L003, L004 | L005 | 2,000 | 500 | 217 | 34 | 1,783 | 466 |

Train and test die counts are equal across folds because every lot has 500 eligible dies and nothing was excluded. Fail counts are not equal. L004 contributes 97 of the 251 fails, so the fold that holds L004 out trains on only 154 fails.

Why group by lot: dies from one lot share a time window and any lot-level condition. Holding out the whole lot keeps those dies out of training. Because every wafer and die belongs to one lot, this also separates the held-out lot’s wafers and dies. `ml/split.py` checks that the training lot set and the test lot set are disjoint.

These fold sizes are what the current split code produces from V2. They are not the sample count stored on the active `yi_ml_v1` artifact.

---

## 22. Preventing leakage

Denied list: `configs/ml_feature_allowlist.yaml` and `SOURCE_FORBIDDEN` in `ml/dataset.py`. Unknown derived names fail closed.

### A. Target leakage

| Field | In V2 files? | Why it is excluded |
| --- | --- | --- |
| `first_pass_fail` | No, it is the label | The label is `y`, not a column of X |
| `first_pass_disposition` | No, derived | Same information as the label |
| `fpy_counts_as` | No, derived | Same information as the label |

### B. Outcome leakage

| Field | In V2 files? | Why it is excluded |
| --- | --- | --- |
| `pass_fail` | Yes, attempts and tests and parameters | Direct outcome |
| `disposition` | Yes | Same as attempt `pass_fail` here |
| `sbin`, `hbin` | Yes | Bins encode pass/fail and fail family |
| `failure_code` | Yes | Fail family |
| `test_pass_fail` | Yes | Test outcome |
| `parametric pass_fail` | Yes (`pass_fail` on the parametric file) | Limit outcome |
| `is_first_fail` | Yes | Which test failed first |
| `primary_failure_key`, `primary_failure_code`, `primary_failure_family`, `primary_failure_detail` | Derived, not in the CSV | Post-hoc fail label |
| `final_disposition` | Derived | Uses later attempts |
| `abort_flag` | Yes, all false | Abort policy forces FAIL |
| `is_retest` | Yes | Retest happens after the first result |
| `is_rework` | Yes, all false | Rework is outside the eligible population |
| `sequence_index` | Yes | Test order used to pick the primary fail |
| `over_limit` | **NOT PRESENT** | Still denied |

### C. Identity / grouping

| Field | Why it is excluded from X |
| --- | --- |
| `lot_id` | Split key. Kept for grouping only |
| `wafer_id` | Identity. Nested inside the lot |
| `die_id` | Identity. Not unique by itself |
| `attempt_id` | Join key |

`product_id`, `step_id`, `part_class`, `attempt_number`, `is_first_attempt`, and `record_status` are on the allowlist of source columns and are not copied into the ML frame by `build_dataset`.

### D. Hidden ground truth

These names are denied. None of them are columns on the agent-visible CSVs (checked): `true_root_cause`, `true_cause`, `true_causes`, `planted_cause`, `planted_causes`, `latent_quality`, `scenario_id`, `expected_hypothesis`, `expected_signal`, `generator_seed`, `injected_effect`, `injected_parameters`, `difficulty`, `ground_truth`, `recoverable_fraction`.

### E. Future information

`timestamp_epoch` uses the training fold’s minimum time, not the held-out lot’s future. `tester_fail_rate` and `probe_fail_rate` use training labels only. An unseen tester or card falls back to the training global mean. Test results after the first fail are not features.

### F. Post-test information

Retest pass/fail, final disposition, primary-failure fields, and software/hardware bins are not features. A recovered retest would leak the outcome of a later touchdown if `final_disposition` were used. It is not used.

---

## 23. Statistics data

Detectors run from `detectors/runner.py` → `run_detectors_on_dir`. Population is the FPY-eligible first-pass die (`detectors/population.py`). Outputs are in-memory `DetectorResult` records (status, hypothesis family, effect size, p-value). They are not V2 data files. Benjamini-Hochberg FDR is applied across detector hypotheses.

| Detector | Input data | Grain | Output |
| --- | --- | --- | --- |
| `spatial` | First-pass fail flag, `x`, `y`, radius `hypot(x, y)` | eligible die | EDGE / CENTER / RING vs complement |
| `lot` | First-pass fail flag, `lot_id` | lot vs other lots | `PROCESS` lot-vs-rest |
| `wafer` | First-pass fail flag, `lot_id/wafer_id` | wafer vs other wafers | `PROCESS` wafer-vs-rest |
| `equipment` | First-pass fail flag, `tester_id` | tester vs other testers | `EQUIPMENT` |
| `contact` | First-pass fail flag, `probe_card_id` | probe card vs others | `CONTACT` |
| `temporal` | First-pass fail flag, `timestamp`, lot order | lot in time order | early-vs-late and Mann-Kendall |
| `temperature` | First-pass fail flag, exact `temperature_c` | temperature value vs others | `ENVIRONMENT` / `TEMPERATURE` |
| `parametric` | First-pass parametric `measurement` by `parameter_name` and lot | measurement values | KS lot-vs-complement and PSI |
| `near_limit` | `measurement`, `lower_limit`, `upper_limit`, fail flag | measurement vs nearest limit | limit-proximity signal |
| `sequence` | First-pass `test_results` with `sequence_index` | attempt-test | fail rate given the preceding test |
| `correlation` | First-pass test fail flags. `NOT_EXECUTED` is tracked | test pair on dies where both ran | co-fail association |
| `no_signal` | Statuses of the detectors above | detector set | Fires when the others do not signal |

`prober_id` is not a detector key. `voltage_v` is not a detector key. `process_tool_id` is not loaded.

---

## 24. Failure Pareto (“Where is yield lost?”)

UI: `frontend/src/components/ParetoChart.tsx`. The heading is “Where is yield lost?”. The subtitle says the values are PRIMARY_FAILURE only, copied from the analysis output.

Path: `test_results.csv` + first-pass fails → `attribute_failures` → `fpy.primary_fail_pareto` → `reporting/summary.py` → dashboard `loss_summary.primary_failure`.

| Rule | Implementation |
| --- | --- |
| Population | 2,500 eligible dies, 251 first-pass fails |
| One primary per failing die | Yes for the Pareto counter |
| Selection | `is_first_fail = true` |
| Overlap on the primary chart | No. `overlap_allowed` is false. The ten counts sum to 251 |
| Share of fails | `n_dies / 251` |
| Share of eligible | `n_dies / 2,500` |
| Any-fail chart | Separate. A die can contribute to more than one test. Those counts sum to 308, which is more than 251 |

Primary Pareto from the current engine:

| Test (failure key) | Failure code | Taxonomy | Dies | Share of fails | Share of eligible |
| --- | --- | --- | --- | --- | --- |
| T004 | CONTACT | UNKNOWN.UNMAPPED_CODE | 92 | 0.3665 | 0.0368 |
| T006 | VMIN | PARAMETRIC.UNKNOWN | 39 | 0.1554 | 0.0156 |
| T005 | IDDQ | PARAMETRIC.UNKNOWN | 38 | 0.1514 | 0.0152 |
| T001 | CONTINUITY | CONTACT.CONTINUITY | 17 | 0.0677 | 0.0068 |
| T002 | OPENS | UNKNOWN.UNMAPPED_CODE | 13 | 0.0518 | 0.0052 |
| T007 | VMAX | UNKNOWN.UNMAPPED_CODE | 12 | 0.0478 | 0.0048 |
| T009 | FUNCTIONAL | FUNCTIONAL.UNKNOWN | 12 | 0.0478 | 0.0048 |
| T003 | SHORTS | UNKNOWN.UNMAPPED_CODE | 10 | 0.0398 | 0.0040 |
| T008 | LEAKAGE | UNKNOWN.UNMAPPED_CODE | 9 | 0.0359 | 0.0036 |
| T010 | SCAN | FUNCTIONAL.SCAN | 9 | 0.0359 | 0.0036 |

Any-fail die counts (overlapping): T004 95, T006 49, T005 43, T007 21, T009 21, T010 21, T001 17, T008 17, T002 14, T003 10.

The Pareto is the distribution of the **first failed test**, after stop-on-fail censoring. It is not a root cause. A CONTACT bar means test T004 was the earliest failed test on those dies. It does not by itself mean the probe card, the process, or the limit is the cause. Later tests that were `NOT_EXECUTED` cannot appear as primary. Unmapped codes stay `UNKNOWN.UNMAPPED_CODE` rather than being renamed into a physical family. Hypothesis text is a later step and is not this chart.

---

## 25. Hidden ground truth

Hidden evaluation files exist. They are not in `data/synthetic/agent_visible/`.

| Location | What it is | Read by the agent, dashboard, FPY, or ML? |
| --- | --- | --- |
| `evaluation/ground_truth/synthetic_v2/yi_synthetic_v2.json` | Generator evaluation record | No |
| `evaluation/ground_truth/synthetic_v2/RUN_SUMMARY.json` | Short run record | No |
| `configs/synthetic_v2.yaml` `lots:` block | Inputs the generator uses and does not write to agent CSVs | No. The API and ML loaders do not read this block |
| `evaluation/results/synthetic_v2_validation.json` | Generator check report | No |

Top-level keys in the hidden JSON: `dataset_id`, `dataset_version`, `difficulty`, `lots`, `seed`, `summary`.

Keys present on each hidden lot entry: `role`, `expected_signal`, `extra_p`, `extra_p_edge`, `extra_p_per_wafer`, `extra_p_tester`, `affected_tester`. Not every lot uses every key. The per-lot values are **EVALUATION ONLY** and are not copied into this document.

| Requested name | Present? |
| --- | --- |
| `scenario_id` | **NOT PRESENT**. The dataset id is `yi_synthetic_v2` |
| `true_cause` / `true_causes` / `true_root_cause` | **NOT PRESENT** |
| `injected_effect` / `injected_parameters` | **NOT PRESENT** under those names. The hidden lot entries use the keys listed above |
| `generator_seed` | **NOT PRESENT** under that name. A `seed` field is in the generator config and the hidden JSON. It is not a column on any agent-visible file |
| `ground_truth` | The hidden file itself. Not a column |
| `recoverable_fraction` | **NOT PRESENT** |
| `expected_signal` | Hidden lot entry only. Not an agent-visible column |

`assert_no_hidden_columns` in the generator refuses to write those forbidden names into the agent folder. A scan of every V2 CSV header found none of them.

ML training code does not open the hidden JSON. The deny list still rejects those names if they appear on an agent-visible table.

---

## 26. Current V2 counts

| Item | Count |
| --- | --- |
| Lots | 5 |
| Wafers (lot-wafer pairs) | 25 |
| Dies | 2,500 |
| Attempts | 2,560 |
| First-pass attempts | 2,500 |
| Retest attempt rows | 60 (57 second attempts + 3 third attempts) |
| Dies that were retested | 57 |
| Test rows | 25,600 |
| Unique test ids | 10 |
| Parametric rows | 20,480 |
| Unique parameters | 8 |
| First-pass passes | 2,249 |
| First-pass fails | 251 |
| All-attempt passes | 2,298 |
| All-attempt fails | 262 |
| Aborted attempts | 0 |
| Unique testers | 3 (T01, T02, T03) |
| Unique probe cards | 3 (PC01, PC02, PC03) |
| Unique probers | 2 (PR01, PR02) |
| Unique attempt failure codes | 10, plus blank on passes |
| Unique test ids | 10 (T001–T010) |

---

## 27. Data quality

Checked by reading the CSVs and by running `calculate_fpy` (read only). Nothing was modified.

| Check | Result | Detail |
| --- | --- | --- |
| Missing lot, wafer, die, attempt, product, step | PASS | No blanks |
| Missing timestamps | PASS | No blanks |
| Missing temperature or voltage | PASS | No blanks |
| Missing measurements | PASS | 20,480 numeric values present |
| Blank `failure_code` on passes | PASS | 2,298 blanks. Expected for PASS |
| Blank `is_first_fail` on non-chosen tests | PASS | Expected. 262 `true`, 59 `false` |
| Blank limits | PASS | One-sided specs. `lower_limit` blank on 15,360 parametric rows. `upper_limit` blank on 2,560 rows (VMAX only) |
| Blank `process_chamber_id` | WARNING | Column exists and is empty on all 25 wafers. Analysis does not load it |
| Blank `parent_equipment_id` | WARNING | Empty on all 8 catalog rows. Analysis does not load the file |
| Duplicate attempt ids | PASS | 0 |
| Duplicate full attempt rows | PASS | 0 |
| `die_id` unique by itself | WARNING | Each of D001–D100 occurs 25 times. The die key includes lot and wafer |
| Invalid coordinates | PASS | All first-pass `x` and `y` are in 1…10 |
| 10×10 complete on every wafer | PASS | 25 wafers |
| Attempt missing a lot row | PASS | 0 |
| Attempt missing a wafer row | PASS | 0 |
| Die missing a part row | PASS | 2,500 = 2,500 |
| Orphan tests or parameters | PASS | 0 |
| Test ids outside T001–T010 | PASS | None |
| Every attempt has 10 tests and 8 parameters | PASS | Yes |
| `parameter` equals `parameter_name` | PASS | All rows |
| `value` equals `measurement` | PASS | All rows |
| `lots.csv` vs `lot_metadata.csv` | WARNING | Identical duplicate files |
| `wafers.csv` vs `wafer_metadata.csv` | WARNING | Identical duplicate files |
| FPY invariant | PASS | 2,500 = 2,249 + 251, exclusions 0 |
| Hierarchy | PASS | 5 × 5 × 100 |
| Failure codes outside the bin map | WARNING | OPENS, SHORTS, CONTACT, VMAX, LEAKAGE map to `UNKNOWN.UNMAPPED_CODE`. CONTACT is the largest Pareto bar |
| `sbin` vs earliest failure code | WARNING | 20 failing attempts. Does not change FPY while `pass_fail` is populated |
| Primary copied onto the die by `die_id` only | WARNING | 137 of 251 per-die primary fields disagree with the attempt’s real primary. Pareto totals are unaffected |
| Values outside published limits | PASS | IDDQ, VMIN, and one VMAX row cross a limit. That is a limit fail, not a corrupt number. Other parameters stay inside their limits |
| Retest measurements | WARNING | Retests copy the first-attempt measurement, temperature, and voltage. They are not a new measurement |
| ML artifact vs this dataset | WARNING | Active `yi_ml_v1` metadata does not name `yi_synthetic_v2` and records 784 samples, not 2,500 |
| V2 parameters absent from ML features | WARNING | Measurements are available to detectors and are not features |
| Hidden labels on agent files | PASS | None found |

No check above is a structural FAIL of the hierarchy, the keys, or the FPY invariant.

---

## 28. One die, end to end

Die **L001 / W01 / D049**. Chosen because it has a failing first pass and a passing retest, which is the case people mis-read as a first-pass pass.

### Lot and wafer

| | |
| --- | --- |
| Lot | L001 (LOT 001), product DEV_A, step WS_SORT |
| Wafer | W01, sequence 1, process tool TOOL-A |
| Die | D049 |
| Location | x = 9, y = 5, site = 0 |
| Class | PRODUCTION. Not rework, not engineering, not calibration |

### Attempt 1 — `E-L001-W01-D049-1`

| Field | Value |
| --- | --- |
| Time | 2026-11-01T08:36:00Z |
| `attempt_number` | 1 |
| `is_first_attempt` | true |
| `is_retest` | false |
| `abort_flag` | false |
| Tester / probe card / prober | T01 / PC03 / PR01 |
| Temperature | 24.696 °C |
| Voltage | 0.8009 V |
| `pass_fail` / `disposition` | FAIL / FAIL |
| `failure_code` | CONTINUITY |
| `sbin` / `hbin` | 9 / 5 |
| `record_status` | VALID |

Tests on attempt 1:

| Seq | Test | Result | Failure code | `is_first_fail` |
| --- | --- | --- | --- | --- |
| 1 | T001 | FAIL | CONTINUITY | true |
| 2 | T002 | NOT_EXECUTED | | |
| 3 | T003 | NOT_EXECUTED | | |
| 4 | T004 | NOT_EXECUTED | | |
| 5 | T005 | NOT_EXECUTED | | |
| 6 | T006 | NOT_EXECUTED | | |
| 7 | T007 | NOT_EXECUTED | | |
| 8 | T008 | NOT_EXECUTED | | |
| 9 | T009 | NOT_EXECUTED | | |
| 10 | T010 | FAIL | SCAN | false |

T002–T009 did not run after T001 failed. T010 is an extra stored fail after the first fail. The earliest fail is T001. Attribution for this lot-wafer-die is primary key **T001**, code **CONTINUITY**, taxonomy **CONTACT.CONTINUITY**, method **is_first_fail**.

Parametric values on attempt 1 (attempt 2 repeats them exactly):

| Parameter | Value | Unit | Limits | Limit result |
| --- | --- | --- | --- | --- |
| CONTACT_RESISTANCE | 1.076273 | ohm | upper 2.5 | PASS |
| IDDQ | 30.993534 | uA | upper 50 | PASS |
| INTERCONNECT_RESISTANCE | 4.107234 | ohm | upper 8 | PASS |
| ON_RESISTANCE | 8.402767 | ohm | upper 15 | PASS |
| SUPPLY_CURRENT | 74.586922 | mA | upper 120 | PASS |
| VDD | 0.77512 | V | 0.72 to 0.88 | PASS |
| VMAX | 1.207171 | V | lower 1.05 | PASS |
| VMIN | 0.756145 | V | upper 0.85 | PASS |

### Attempt 2 — `E-L001-W01-D049-2`

| Field | Value |
| --- | --- |
| Time | 2026-11-01T08:36:30Z |
| `attempt_number` | 2 |
| `is_retest` | true |
| Same tester, card, prober, site, temperature, voltage, x, y | yes |
| `pass_fail` / `disposition` | PASS / PASS |
| `failure_code` | blank |
| `sbin` / `hbin` | 1 / 1 |
| Tests | T001–T010 all PASS |

### What FPY says

| Question | Answer |
| --- | --- |
| First-pass result | FAIL |
| Final result | PASS |
| Counts in FPY as | FAIL |
| Counts in final yield as | PASS |
| ML target `first_pass_fail` | 1 |

There is no third attempt for this die.

---

## 29. One lot, end to end

**L001**, display name LOT 001.

| Lot field | Value |
| --- | --- |
| Product / step | DEV_A / WS_SORT |
| Window | 2026-11-01T08:00:00Z to 2026-11-01T21:14:15Z |
| `quantity_declared` | 500 |
| `hold_flag` | false |
| First-pass FPY | 467 / 500 = 0.9340 |
| First-pass fails | 33 |
| Retest attempt rows | 10 |

```text
L001   FPY 0.9340   (467 pass, 33 fail, 500 dies)
├── W01   100 dies   FPY 0.94   (94 pass, 6 fail)
├── W02   100 dies   FPY 0.94
├── W03   100 dies   FPY 0.94
├── W04   100 dies   FPY 0.89   (89 pass, 11 fail)
└── W05   100 dies   FPY 0.96   (96 pass, 4 fail)
```

Each wafer is a full 10×10 grid, die ids D001–D100. Testers on the lot’s first pass: T01 193, T02 176, T03 131. Probe cards and probers are mixed across dies. Temperature on L001 first pass runs from 20.069 °C to 88.941 °C (mean 32.001 °C).

---

## 30. What the Yield Improvement Agent actually sees

| Information | Agent can see? | Used for |
| --- | --- | --- |
| `die_attempts.csv` columns (identity, x/y, equipment ids, temperature, voltage, time, pass/fail, bins, failure code, attempt flags) | Yes | FPY, detectors, and the ML row before columns are dropped |
| `test_results.csv` | Yes | Primary Pareto, sequence detector, correlation detector |
| `parametric_measurements.csv` | Yes | Parametric and near-limit detectors |
| `manifest.json` | Yes | Dataset name and declared counts |
| Lot id list from `lot_metadata.csv` | Yes | Lot picker. Display names LOT 001–LOT 005 |
| `lots.csv` | Same content as lot metadata | Fallback for the picker |
| `wafers.csv`, `wafer_metadata.csv`, `parts.csv`, `equipment.csv` | Files are on disk | **Not loaded** by FPY, detectors, ML, or report assembly. Equipment and wafer context reach the agent through columns on the attempt |
| FPY, FPY loss, final yield, retest recovery | Derived, yes | Dashboard KPIs |
| Primary Pareto and any-fail Pareto | Derived, yes | “Where is yield lost?” |
| Detector results | Derived, yes | Evidence |
| Hypotheses, opportunity, investigation plan | Derived, yes | Dashboard narrative. Not dataset tables |
| ML features (16) and target | Derived when ML code runs, yes | Model matrix. Not a saved V2 file |
| `lot_id` as a model input | On the frame, excluded from X | LOLO grouping |
| Outcomes (`pass_fail`, bins, failure codes, test results) as model inputs | Seen in the files, blocked from X | Leakage policy |
| V2 parametric names as model inputs | Seen in the file, not joined | Allowlist still names a different parameter set |
| Hidden lot roles, expected signals, seed | No | Evaluation files only |
| Active model `yi_ml_v1` metrics | Yes, from `artifacts/ml/yi_ml_v1/` | Dashboard ML card. Those metrics were not computed on this 2,500-die table |

---

## 31. End-to-end data flow

```text
configs/synthetic_v2.yaml
        |
        v
src/yield_improvement/synthetic/v2_generator.py
        |
        +--> data/synthetic/agent_visible/yi_synthetic_v2/
        |       die_attempts.csv
        |       test_results.csv
        |       parametric_measurements.csv
        |       lot_metadata.csv   (= lots.csv)
        |       wafer_metadata.csv (= wafers.csv)     [not loaded by analysis]
        |       parts.csv                               [not loaded by analysis]
        |       equipment.csv                            [not loaded by analysis]
        |       manifest.json
        |
        +--> evaluation/ground_truth/synthetic_v2/     [evaluation only]
        |
        v
src/yield_improvement/ingestion/loader.py
        |
        v
canonical DieAttempt, TestResult, ParametricMeasurement
        |
        v
yield_analysis/fpy.py + attribution.py + taxonomy.py + configs/fpy_policy.yaml
        |     FPY = 2249/2500,  loss = 251/2500
        v
primary-failure Pareto  -->  frontend ParetoChart.tsx  "Where is yield lost?"
        |
        v
detectors/runner.py   (spatial, lot, wafer, equipment, contact,
                        temporal, temperature, parametric, near_limit,
                        sequence, correlation, no_signal)
        |
        v
ml/dataset.py  -->  2500 rows, target first_pass_fail
ml/features.py -->  16 features
ml/split.py    -->  5-fold leave-one-lot-out
        |
        v
hypotheses/composer.py
opportunity/engine.py
validation/validator.py
reporting/adapter.py  -->  EngineeringReport
        |
        v
api/service.py  -->  dashboard
```

The active model file `artifacts/ml/yi_ml_v1/` sits beside this flow. The dashboard can display it. It is not a product of training on `yi_synthetic_v2`.

---

## 32. Layer summary

| Layer | What exists | Grain | Actual size | Purpose |
| --- | --- | --- | --- | --- |
| Lot | `lot_metadata.csv` (copy: `lots.csv`) | lot | 5 rows | Lot id, product, step, time window, quantity 500 |
| Wafer | `wafer_metadata.csv` (copy: `wafers.csv`) | lot-wafer | 25 rows | Wafer id, slot, tool TOOL-A. Not loaded by analysis |
| Die | `parts.csv` plus die columns on attempts | die | 2,500 | Identity and 10×10 location. Parts file not loaded by analysis |
| Attempt | `die_attempts.csv` | die-attempt | 2,560 | Pass/fail, equipment, environment, time |
| Test | `test_results.csv` | attempt-test | 25,600 | 10 tests, stop-on-fail with occasional extra fail |
| Parametric | `parametric_measurements.csv` | attempt-parameter | 20,480 | 8 measurements |
| Environment | `temperature_c`, `voltage_v` on the attempt | attempt | 2,560 | Temperature and voltage. Humidity not present |
| Equipment | ids on the attempt; catalog file unused by analysis | die | 3 testers, 3 cards, 2 probers | Who touched the die |
| FPY | derived | eligible die | 2,500 | 0.8996 pass, 0.1004 loss |
| Statistics | derived detector context | eligible die | 2,500 | Spatial through no-signal detectors |
| ML | derived frame | eligible die | 2,500 rows, 16 features | `first_pass_fail`, LOLO by lot |
| Ground truth | hidden JSON | dataset / lot scenario | 1 file + run summary | Evaluation only |

---

## VERIFIED V2 DATASET SUMMARY

- Dataset name: Yield Improvement V2
- Dataset path: `data/synthetic/agent_visible/yi_synthetic_v2/`
- Lots: 5 (`L001`–`L005`)
- Wafers: 25 (5 per lot, ids `W01`–`W05`)
- Dies: 2,500 (100 per wafer, ids `D001`–`D100`, unique only with lot and wafer)
- Attempts: 2,560 (2,500 first pass, 57 second attempts, 3 third attempts)
- Tests: 25,600 rows, 10 test ids `T001`–`T010`
- Parameters: 8 (`IDDQ`, `VMIN`, `VMAX`, `VDD`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE`), 20,480 rows
- Equipment: testers T01 T02 T03, probe cards PC01 PC02 PC03, probers PR01 PR02, site 0 or 1
- Environment: `temperature_c` and `voltage_v`. Humidity NOT PRESENT
- FPY: 0.8996 (2,249 / 2,500)
- FPY loss: 0.1004 (251 / 2,500)
- ML sample count: 2,500 eligible dies if `load_ml_dataset` is run on this folder
- ML features: 16 (`die_x`, `die_y`, `normalized_x`, `normalized_y`, `radial_distance`, `edge_distance`, `spatial_region`, `timestamp_epoch`, `temperature_c`, `voltage_v`, `site`, `tester_id`, `probe_card_id`, `prober_id`, `tester_fail_rate`, `probe_fail_rate`)
- ML target: `first_pass_fail` (1 = first-pass FAIL, 0 = first-pass PASS)
- Split strategy: leave-one-lot-out, 5 folds, 2,000 train dies and 500 test dies per fold
- Hidden evaluation data: `evaluation/ground_truth/synthetic_v2/` (not agent-visible; scenario values omitted here)
- Active model: `yi_ml_v1`, architecture logistic regression, registry state ACTIVE. Artifact metadata `n_samples` is 784 and its `analysis_id` is not `yi_synthetic_v2`. Feature names match the 16 above. The artifact was not trained on this dataset
- Files used by analysis: `die_attempts.csv`, `test_results.csv`, `parametric_measurements.csv`. API also reads `manifest.json` and `lot_metadata.csv` (or `lots.csv`)
- Files not used by FPY, detectors, ML, or report assembly: `wafers.csv`, `wafer_metadata.csv`, `parts.csv`, `equipment.csv`. `lots.csv` duplicates `lot_metadata.csv` and is only a fallback for the lot list
