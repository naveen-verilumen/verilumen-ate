# Yield Improvement Agent — V1 Specification

**Project:** Yield Improvement Agent  
**Status:** V1 specification — **not yet approved for implementation**  
**Supersedes:** Discovery §12 / §15 orchestration architecture. This spec is authoritative for V1.  
**Date:** 2026-09-22  

This document freezes V1 scope, FPY policy, data contracts, analysis formulas, safety, evaluation, and independence rules. It does **not** authorize production code.

---

## How to read this document

| Marker | Meaning |
|--------|---------|
| **FROZEN** | V1 decision. Implement this unless a later review explicitly changes it. |
| **TO BE CALIBRATED** | Method frozen; numeric threshold not yet justified. |
| **OPEN** | Must be decided before or during implementation review. Do not silently pick. |
| **ILLUSTRATIVE** | Example values for format only — not measured factory data. |

**Independence (FROZEN):** This agent is a new, self-contained product. It must run, evaluate, and report using only its own data, code, models, safety layer, and configuration. It must not import, call, or depend on any other agent.

---

## 1. V1 Scope

### 1.1 Objective (FROZEN)

Build a standalone semiconductor Yield Improvement Agent focused on:

**WAFER-SORT FIRST PASS YIELD DIAGNOSIS**

The agent must:

1. Calculate FPY under the V1 FPY policy (§2).
2. Identify where first-pass yield is lost.
3. Quantify failure-mode contributions without double-counting die-level FPY loss.
4. Detect important spatial, temporal, equipment, parametric, and distribution patterns.
5. Generate **competing** root-cause **hypotheses** (never confirmed causes).
6. Identify yield-improvement **investigation** opportunities.
7. Estimate opportunity as **observed / upper-bound / plausible / safety-eligible**.
8. Attach evidence, counter-evidence, confidence, and data gaps.
9. If a problem looks like a future specialist domain, **describe it** as `potential_specialist_investigation` — **do not invoke another agent**.
10. Produce a machine-readable analysis object and a human-readable engineering report.

### 1.2 Architecture (FROZEN)

```text
                YIELD IMPROVEMENT AGENT
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   Data Analysis     Statistical       Optional
                    methods            ML (V1 limited)
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                  Root Cause Analysis
                    (hypotheses only)
                         │
                         ▼
                 Yield Opportunity
                     Detection
                         │
                         ▼
                Recommendation Engine
                  (investigate / review /
                   monitor / do not change)
                         │
                         ▼
                Independent Safety
                    & Validation
                         │
                         ▼
                 Engineering Report
```

The entire pipeline must work with **only** this project’s dataset.

### 1.3 Explicit non-goals (FROZEN)

V1 must **not**:

- Modify ATE limits, ATE configurations, test programs, process recipes, or equipment settings.
- Automatically change production conditions.
- Automatically approve a yield optimization.
- Treat correlation as causation.
- Treat an ML prediction as a confirmed root cause.
- Call, import, or depend on Dynamic Test Limits, False Failure Reduction, Retest Reduction, or Escape Prevention.
- Reuse another project’s code, models, configs, datasets, simulation engines, or safety implementations.
- Write to MES / ATE / recipe systems.
- Mix final-test or assembly populations into wafer-sort FPY.

### 1.4 V1 insertion and population (FROZEN)

| Item | V1 value |
|------|----------|
| Insertion | Wafer sort / circuit probe only |
| Unit of yield | Unique physical die |
| Primary KPI | First Pass Yield (§2) |
| Secondary KPIs | Final disposition yield, retest rate, retest recovery — reported separately, never mixed into FPY |
| Product mix | One `product_id` + one `step_id` per analysis run |
| Production action | Always `forbidden` |

### 1.5 Independence from other agents (FROZEN)

Other agents may exist later as **separate products**. V1 must not:

- Import their modules or models
- Call their APIs
- Assume their data exists
- Route execution through them
- Design schemas around their candidate-limit or false-fail engines

If evidence suggests a problem that *could* belong to another domain, emit:

```text
potential_specialist_investigation:
  domain: TEST_LIMIT | FALSE_FAILURE | RETEST_POLICY | ESCAPE_RISK | OTHER
  reason: <evidence summary>
  action: DESCRIBE_ONLY
```

That is a **label in the report**, not an RPC.

### 1.6 Project structure (FROZEN, files not created yet)

Self-contained repository. Evaluation ground truth is isolated so the runtime cannot see it.

```text
yield-improvement-agent/
│
├── data/
│   ├── raw/                      # immutable inputs
│   ├── processed/                # canonical tables (no ground-truth columns)
│   └── synthetic/
│       └── agent_visible/        # generator output the agent may read
│
├── configs/                      # FPY policy, taxonomy, safety, analysis
│
├── src/
│   └── yield_agent/
│       ├── ingestion/
│       ├── validation/
│       ├── preprocessing/
│       ├── canonical/            # grain indexes (justified: prevents grain mix)
│       ├── features/
│       ├── yield_analysis/
│       ├── spatial_analysis/
│       ├── temporal_analysis/
│       ├── root_cause/
│       ├── models/
│       ├── opportunity/
│       ├── recommendation/
│       ├── safety/
│       └── reporting/
│
├── models/                       # this project only
├── simulations/                  # this project’s counterfactuals
├── evaluation/                   # metrics + scenario contracts
│   └── ground_truth/             # FORBIDDEN to agent runtime
├── tests/
├── notebooks/
├── docs/
├── pyproject.toml
└── README.md
```

`canonical/` is the only structural addition to the suggested tree: yield data has multiple grains (die, attempt, test, parametric). A canonical layer prevents concatenating them.

---

## 2. FPY Policy

### 2.1 Term definitions (FROZEN)

These terms are **project definitions**. They apply only to wafer-sort V1.

| Term | Definition |
|------|------------|
| **Unit** | One physical die, identified by `(lot_id, wafer_id, die_id)`. If `die_id` is absent, `(lot_id, wafer_id, x, y)` may be used as identity **only when both coordinates are present and unique on the wafer**. |
| **Wafer-sort production testing** | Probe/sort insertion with `insertion = WAFER_SORT` and `part_class = PRODUCTION`. |
| **Test execution** | One ATE attempt on one unit (`test_execution_id`). |
| **FIRST PASS** | The earliest **valid** test execution for that unit at wafer-sort, after applying the eligibility rules below. There is at most one first pass per unit. |
| **PASS** | First-pass disposition is a configured **pass bin** (or `pass_fail = PASS` when bins are absent). Equality on a parametric limit is PASS if a scalar compare is required: UPPER fail iff `measurement > upper_limit`; LOWER fail iff `measurement < lower_limit`. |
| **FAIL** | First-pass disposition is a configured **fail bin**, `pass_fail = FAIL`, or a first-pass **abort** (see abort rule). |
| **RETEST** | Any valid execution on the same unit **after** the first pass. Retest-pass does **not** count as first-pass PASS. |
| **REWORK** | Unit flagged as returning to wafer-sort after a prior disposition (`rework_flag = true` or `part_class = REWORK`). Not first pass. |
| **FINAL PASS** | Last valid disposition in the analysis window after allowed retests (still wafer-sort only). Used for **final yield**, not FPY. |
| **SCRAP** | Final fail / scrap bin after the analysis window’s disposition rules. Still counted in the FPY denominator **if** the unit had a valid first pass. |
| **ESCAPE** | A defective unit shipped as good. **Not observed in V1 wafer-sort data.** Always `unavailable` unless a future quality dataset is added. Must not be inferred from FPY. |
| **Invalid execution** | Failed validation: duplicate collapsed, corrupt record, missing required disposition fields, or `record_status = REJECT`. |
| **Eligible unit** | A unique production die that **enters wafer-sort production testing and has a valid first-pass disposition**. |

### 2.2 Primary formula (FROZEN)

\[
\mathrm{FPY} = \frac{N_{\mathrm{first\_pass\_pass}}}{N_{\mathrm{fpy\_eligible}}}
\]

\[
\mathrm{FPY\_loss} = 1 - \mathrm{FPY} = \frac{N_{\mathrm{first\_pass\_fail}}}{N_{\mathrm{fpy\_eligible}}}
\]

**Denominator \(N_{\mathrm{fpy\_eligible}}\):** count of unique eligible units (unique dies), **not** count of test executions.

**Numerator:** eligible units whose **first-pass disposition is PASS**.

Invariant (must be tested):

\[
N_{\mathrm{fpy\_eligible}} = N_{\mathrm{first\_pass\_pass}} + N_{\mathrm{first\_pass\_fail}}
\]

If this fails, the FPY calculation is invalid (`DATA_QUALITY_FAILURE`).

### 2.3 Eligibility algorithm (FROZEN)

For each unique die identity in the analysis population:

1. Restrict to `insertion = WAFER_SORT`.
2. Drop `record_status = REJECT` and schema-invalid rows.
3. Drop `part_class ∈ {ENGINEERING, CALIBRATION, QA_SAMPLE, UNKNOWN_NON_PRODUCTION}` when the class is present.
4. Drop units with `rework_flag = true` from **FPY** (they may appear in a separate rework yield metric; V1 does not compute that metric).
5. Collect remaining executions ordered by `(timestamp, test_execution_id)`.
6. **First pass** = the earliest execution with a **valid disposition** (`pass_fail` in `{PASS, FAIL}` **or** a mappable bin **or** abort classified under §2.4).
7. If no such execution exists → unit is **not FPY-eligible** (excluded from \(N\)). Record as `excluded_reason`.
8. If the earliest valid execution is a retest-only row (`first_test_indicator = false` and no earlier first-test row) → **not FPY-eligible**.
9. FPY uses **only** that first-pass disposition. Later executions never change FPY.

### 2.4 Edge-case policy (FROZEN unless marked OPEN)

| Edge case | V1 handling | Rationale |
|-----------|-------------|-----------|
| Unit tested multiple times | Only the first valid execution is first pass. Later rows are retest. | FPY is first attempt, not last. |
| Missing first-pass result | Exclude from \(N\). Count in `exclusions.missing_first_pass`. Do not impute PASS or FAIL. | Unknown disposition must not inflate or deflate FPY. |
| Retest-only record | Exclude from \(N\). | No first attempt observed. |
| Aborted first execution | **Count as FAIL** (`abort_is_first_pass_fail = true`). | Abort is not a successful first pass. Excluding aborts would inflate FPY. |
| Abort on retest only | Does not affect FPY (first pass already set). Affects final yield only. | |
| Invalid measurement, valid die disposition | Use die-level `pass_fail` / bin. Flag measurement invalid for parametric analysis. | FPY is die disposition, not a single PTR. |
| Invalid measurement and no die disposition | Exclude from \(N\). | |
| Engineering samples | Exclude when `part_class = ENGINEERING`. | Not production FPY. |
| Calibration units | Exclude when `part_class = CALIBRATION`. | |
| `part_class` missing | **Treat as PRODUCTION** and flag `part_class_assumed_production = true`. | **OPEN to reverse** if real data is mostly unlabeled engineering. |
| Duplicate records | Keep earliest valid execution per die; drop others as `REJECT` duplicates. If two rows share timestamp and execution id, drop both and exclude die (`ambiguous_duplicate`). | Do not pick arbitrarily. |
| Missing bin, `pass_fail` present | Use `pass_fail`. Bin contribution = `unavailable` for that die. | |
| Missing bin and missing `pass_fail` | Exclude from \(N\). | |
| Missing test-level results but die bin present | Die is FPY-eligible from bin. Test-level Pareto uses only dies with test results; report coverage. | |
| Units from rework | Exclude from FPY. | Not first pass. |
| Multiple testers | First chronological valid execution wins, regardless of tester. Equipment analysis still stratifies first-pass tester. | |
| Multiple sites / heads on one die | One die still one FPY unit. Site is a stratifier, not a second unit. | |
| Continuity / no-contact fail bin | FAIL (included). | It consumed a first-pass attempt. Hypothesis layer may later call it contact-related. |
| Partial wafer / notched / unused die | Only dies present in the datalog with identity. Do not invent missing map locations. | |
| Mixed product/step in one file | Analysis run **must** filter to one product+step. If mixed and unfiltered → refuse (`POPULATION_MIX`). | |

### 2.5 Related metrics (FROZEN — separate from FPY)

Let \(N = N_{\mathrm{fpy\_eligible}}\).

| Metric | Formula | Must not |
|--------|---------|----------|
| Final yield | \(N_{\mathrm{final\_pass}} / N\) | Replace FPY |
| Retest rate (of eligible) | \(N_{\mathrm{retested}} / N\) | Enter FPY numerator |
| Retest rate (of first-pass fails) | \(N_{\mathrm{retested}} / N_{\mathrm{first\_pass\_fail}}\) | Be unlabeled |
| Retest recovery | \(N_{\mathrm{first\_fail\_then\_final\_pass}} / N_{\mathrm{first\_pass\_fail}}\) | Prove false fail |
| Exclusion rate | \(N_{\mathrm{excluded}} / (N + N_{\mathrm{excluded}})\) | Be hidden |

Escape rate: **`unavailable`** in V1.

### 2.6 Reporting requirements (FROZEN)

Every FPY number must be accompanied by:

- `population` (product, step, insertion, time window, lot set)
- `n_eligible`, `n_pass`, `n_fail`
- `n_excluded` by reason
- `abort_policy = FIRST_PASS_ABORT_IS_FAIL`
- `part_class_assumption` if used

---

## 3. Canonical Data Model

All agent-visible tables are **this project’s** schema. STDF and synthetic generators must map **into** these tables. Grains must not be concatenated.

### 3.1 Identity rules (FROZEN)

- `lot_id`, `wafer_id`, `die_id`, `test_id`, `test_execution_id` are strings.
- `die_id` is unique **within** `(lot_id, wafer_id)`, not globally.
- Natural die key: `(lot_id, wafer_id, die_id)`.
- Surrogate `part_sk` may exist internally; analysis keys remain natural keys.
- Null foreign keys are allowed only for optional entities (process, environment). They produce `unavailable`, not inferred values.
- Ground-truth columns (`true_*`, `latent_*`, `planted_*`, generator seeds) are **forbidden** on agent-visible tables.

### 3.2 Entities

#### `lot_dim`

| | |
|--|--|
| **Grain** | One manufacturing lot |
| **PK** | `lot_id` |
| **Required** | `lot_id`, `product_id`, `step_id` |
| **Optional** | `start_ts`, `quantity_declared`, `hold_flag` |
| **Types** | ids: string; `start_ts`: datetime UTC; `quantity_declared`: int ≥ 0; `hold_flag`: bool |

#### `wafer_dim`

| | |
|--|--|
| **Grain** | One wafer inside a lot |
| **PK** | `(lot_id, wafer_id)` |
| **FK** | `lot_id` → `lot_dim` |
| **Required** | `lot_id`, `wafer_id` |
| **Optional** | `slot`, `process_tool_id`, `process_chamber_id`, `start_ts` |

#### `part_dim` (die)

| | |
|--|--|
| **Grain** | One physical die |
| **PK** | `(lot_id, wafer_id, die_id)` |
| **FK** | `(lot_id, wafer_id)` → `wafer_dim` |
| **Required** | `lot_id`, `wafer_id`, `die_id`, `part_class` |
| **Optional** | `x`, `y` (int or float; same type per dataset), `site`, `rework_flag` |
| **Allowed `part_class`** | `PRODUCTION`, `ENGINEERING`, `CALIBRATION`, `QA_SAMPLE`, `REWORK`, `UNKNOWN` |
| **Notes** | `x`,`y` missing → spatial analysis disabled for that die, not fabricated. `UNKNOWN` + V1 assumption → treated as PRODUCTION for FPY with a flag. |

#### `equipment_dim`

| | |
|--|--|
| **Grain** | One equipment asset (tester, prober, probe card, handler, process tool) |
| **PK** | `equipment_id` |
| **Required** | `equipment_id`, `equipment_type` |
| **Optional** | `parent_equipment_id`, `vendor`, `model` |
| **Allowed `equipment_type`** | `TESTER`, `PROBER`, `PROBE_CARD`, `HANDLER`, `LOAD_BOARD`, `PROCESS_TOOL`, `OTHER` |

#### `test_dim`

| | |
|--|--|
| **Grain** | One named test in the program (not a measurement row) |
| **PK** | `test_id` |
| **Required** | `test_id`, `test_name`, `test_type` |
| **Optional** | `sequence_index`, `unit`, `parameter_name` |
| **Allowed `test_type`** | `PARAMETRIC`, `FUNCTIONAL`, `CONTINUITY`, `IDDQ`, `OTHER` |

#### `bin_dim`

| | |
|--|--|
| **Grain** | One bin code in a versioned map |
| **PK** | `(bin_map_version, bin_number, bin_kind)` |
| **Required** | `bin_number`, `bin_kind`, `disposition` |
| **Optional** | `bin_name`, `failure_family` |
| **Allowed `bin_kind`** | `SBIN`, `HBIN` |
| **Allowed `disposition`** | `PASS`, `FAIL`, `RETEST`, `OTHER` |

#### `test_execution`

| | |
|--|--|
| **Grain** | One die × one test **attempt** (the ATE insertion attempt, not each PTR) |
| **PK** | `test_execution_id` |
| **FK** | part key; optional `tester_id`, `prober_id`, `probe_card_id` → `equipment_dim` |
| **Required** | `test_execution_id`, `lot_id`, `wafer_id`, `die_id`, `timestamp`, `attempt_number`, `first_test_indicator`, `retest_indicator`, `disposition_pass_fail` **or** mappable `sbin`/`hbin` |
| **Optional** | `tester_id`, `prober_id`, `probe_card_id`, `site`, `temperature_c`, `voltage_v`, `abort_flag`, `program_name`, `program_rev` |
| **Rules** | `first_test_indicator` XOR semantics: if `attempt_number = 1` then `first_test_indicator` must be true after normalization. `retest_indicator` true iff `attempt_number ≥ 2`. Inconsistent flags → execution invalid. |

#### `test_result`

| | |
|--|--|
| **Grain** | One die × one test × one execution (`test_execution_id × test_id`) |
| **PK** | `(test_execution_id, test_id)` |
| **FK** | `test_execution_id` → `test_execution`; `test_id` → `test_dim` |
| **Required** | `test_execution_id`, `test_id`, `test_pass_fail` |
| **Optional** | `is_first_fail`, `test_alarm`, `sequence_index` |
| **Allowed `test_pass_fail`** | `PASS`, `FAIL`, `NOT_EXECUTED`, `INVALID` |

#### `failure_event`

| | |
|--|--|
| **Grain** | One die × one first-pass failure attribution record (see §8) |
| **PK** | `(lot_id, wafer_id, die_id, attribution_role, failure_key)` |
| **Required** | part key, `attribution_role`, `failure_key`, `taxonomy_code` |
| **Optional** | `bin_number`, `failure_code`, `test_id` |
| **Allowed `attribution_role`** | `PRIMARY` (exactly one per first-pass fail die), `COFAIL` (zero or more) |

#### `parametric_measurement`

| | |
|--|--|
| **Grain** | One die × one parameter × one measurement on one execution (and condition if present) |
| **PK** | `(test_execution_id, parameter_name, condition_id)` where `condition_id` defaults to `NONE` |
| **Required** | `test_execution_id`, `parameter_name`, `measurement` (float, finite) |
| **Optional** | `lower_limit`, `upper_limit`, `unit`, `pass_fail`, `condition_id`, `temperature_c`, `voltage_v` |
| **Notes** | At least one of `lower_limit` / `upper_limit` required to classify limit proximity. Missing both → parametric limit analysis `unavailable` for that row. |

#### `process_fact` (optional V1)

| | |
|--|--|
| **Grain** | One wafer (or lot if wafer-level process is unavailable) × process snapshot |
| **PK** | `(lot_id, wafer_id)` or `lot_id` |
| **Required** | keys |
| **Optional** | `recipe_id`, `recipe_rev`, `process_tool_id`, `chamber_id`, `operation_id` |
| **Rule** | If table absent or sparse → process hypotheses `unavailable`. Never fill from tester_id. |

#### `environment_fact` (optional V1)

| | |
|--|--|
| **Grain** | Timestamped facility/handler observation **joinable** to executions |
| **PK** | `env_id` |
| **Required** | `timestamp`, at least one of `temperature_c`, `humidity_pct` |
| **Join rule** | Join only if clocks are both UTC (or documented offset). If not joinable → `environment unavailable`. Do not use tester temperature as factory humidity. |

### 3.3 Grain summary (FROZEN)

| Table | Grain |
|-------|--------|
| `lot_dim` | lot |
| `wafer_dim` | lot × wafer |
| `part_dim` | lot × wafer × die |
| `test_execution` | lot × wafer × die × attempt |
| `test_result` | attempt × test |
| `failure_event` | first-pass fail die × attribution role × key |
| `parametric_measurement` | attempt × parameter × condition |
| `equipment_dim` | equipment asset |
| `process_fact` | lot × wafer (optional) |
| `environment_fact` | time-series (optional) |

### 3.4 Analysis population object (FROZEN)

Every run binds:

```text
AnalysisPopulation
  product_id, step_id
  insertion = WAFER_SORT
  lot_ids[] (or time window that resolves to lots)
  fpy_policy_version
  bin_map_version
  taxonomy_version
```

---

## 4. MVP Data Contract

### 4.1 Field classes (FROZEN)

- **REQUIRED FOR MVP:** without these, refuse analysis (`DATA_QUALITY_FAILURE`), except as noted per-field.
- **OPTIONAL FOR V1:** enable additional analyses; if missing, that analysis is `unavailable`.
- **FUTURE:** out of V1 runtime; may exist in schema as unused.

### 4.2 Field dictionary

| Field | Class | Data type | Description | Example | Validation rule | Typical source |
|-------|-------|-----------|-------------|---------|-----------------|----------------|
| `lot_id` | REQUIRED MVP | string | Lot identifier | `L021` | non-empty; one product/step per run | STDF MIR.LOT_ID / synthetic |
| `wafer_id` | REQUIRED MVP | string | Wafer identifier | `W05` | non-empty | STDF WIR.WAFER_ID |
| `die_id` | REQUIRED MVP | string | Die identifier unique on wafer | `D184` | non-empty; unique per wafer | synthetic / derived from X/Y+index |
| `x` | OPTIONAL V1 | number | Wafer X | `12` | finite; not invented | STDF PRR.X_COORD |
| `y` | OPTIONAL V1 | number | Wafer Y | `-3` | finite; not invented | STDF PRR.Y_COORD |
| `part_class` | OPTIONAL V1 | enum | Production vs other | `PRODUCTION` | enum; missing → assume PRODUCTION + flag | typically not in STDF |
| `rework_flag` | OPTIONAL V1 | bool | Rework return | `false` | bool | MES / synthetic |
| `test_execution_id` | REQUIRED MVP | string | Unique attempt | `E-L021-W05-D184-1` | unique | synthetic / constructed |
| `timestamp` | REQUIRED MVP | datetime UTC | Attempt time | `2026-03-12T08:14:22Z` | parseable UTC | STDF PIR/PRR time + MIR date |
| `attempt_number` | REQUIRED MVP | int ≥ 1 | 1 = first | `1` | integer ≥ 1 | derived from order if needed |
| `first_test_indicator` | REQUIRED MVP | bool | Is first pass attempt | `true` | consistent with `attempt_number` | derived / STDF PART_FLG |
| `retest_indicator` | REQUIRED MVP | bool | Is retest | `false` | true iff attempt ≥ 2 | derived |
| `pass_fail` | REQUIRED MVP | enum PASS/FAIL | Die-level disposition for that attempt | `FAIL` | required unless mappable bin exists | PRR PART_FLG + bins |
| `sbin` | REQUIRED MVP* | int | Software bin | `8` | *required unless `pass_fail` present | PRR.SOFT_BIN |
| `hbin` | OPTIONAL V1 | int | Hardware bin | `1` | | PRR.HARD_BIN |
| `failure_code` | OPTIONAL V1 | string | Semantic fail code | `IR_DROP` | | bin map / synthetic |
| `test_id` | OPTIONAL V1** | string | Test name/id | `T_IDDQ` | **required for test Pareto; FPY can run on die disposition only | PTR/FTR TEST_NUM |
| `test_pass_fail` | OPTIONAL V1** | enum | Per-test result | `FAIL` | | PTR TEST_FLG |
| `is_first_fail` | OPTIONAL V1 | bool | First failing test on this attempt | `true` | at most one true per failed execution | derived from sequence |
| `parameter_name` | OPTIONAL V1 | string | Parametric name | `IDDQ` | | PTR |
| `measurement` | OPTIONAL V1 | float | Measured value | `52.1` | finite | PTR RESULT |
| `lower_limit` | OPTIONAL V1 | float | Lo limit | | finite if present | PTR LO_LIMIT |
| `upper_limit` | OPTIONAL V1 | float | Hi limit | `50.0` | finite if present | PTR HI_LIMIT |
| `equipment_id` | OPTIONAL V1 | string | Generic equipment | `EQ-09` | | |
| `tester_id` | OPTIONAL V1 | string | ATE id | `T03` | | MIR.NODE_NAM / SDR |
| `probe_card_id` | OPTIONAL V1 | string | Probe card | `PC-17` | | custom / SDR |
| `prober_id` | OPTIONAL V1 | string | Prober | `PB-02` | | SDR |
| `site` | OPTIONAL V1 | int | Parallel site | `3` | | PIR SITE_NUM |
| `temperature_c` | OPTIONAL V1 | float | Test/handler temp | `85.0` | finite | condition table / SDR |
| `voltage_v` | OPTIONAL V1 | float | VDD condition | `0.80` | finite | program / GDR |
| `abort_flag` | OPTIONAL V1 | bool | Attempt aborted | `true` | missing → false | PRR PART_FLG |
| `sequence_index` | OPTIONAL V1 | int | Test order | `12` | ≥ 0 | program / BPS-EPS |
| `product_id` | REQUIRED MVP | string | Device | `DEV_A` | constant per run | MIR.PART_TYP |
| `step_id` | REQUIRED MVP | string | Operation | `WS_SORT` | must be wafer-sort | config / MIR.JOB_NAM |
| `recipe_id` | FUTURE | string | Process recipe | | | MES |
| `humidity_pct` | FUTURE | float | Facility humidity | | joinable UTC only | facilities |
| `escape_label` | FUTURE | enum | Quality return | | evaluation-only if synthetic | quality systems |

\*If both `sbin` and `pass_fail` are missing, the execution is invalid.  
\*\*V1 **minimum diagnosis** can compute FPY + bin Pareto from die disposition alone. Test-level and parametric analyses require those fields; if absent, those sections are `unavailable`, not guessed.

### 4.3 MVP vs V1 capability matrix (FROZEN)

| Capability | Minimum fields |
|------------|----------------|
| FPY / FPY loss | lot, wafer, die, execution, timestamp/attempt, first-pass flags, pass_fail or bin, product, step |
| Bin contribution | + sbin or failure_code + bin map |
| Test contribution | + test_result |
| Spatial | + x,y |
| Equipment | + tester_id (and probe_card_id if contact hypotheses) |
| Parametric / limit proximity | + measurement and at least one limit |
| Drift | + ordered lots/timestamps across history |
| Temperature correlation | + temperature_c |
| Process hypotheses | + process_fact |
| Environment hypotheses | + joinable environment_fact |

---

## 5. STDF Mapping

### 5.1 Role of STDF (FROZEN)

STDF is a **supported input adapter**, not the internal schema. V1 also accepts canonical tables directly (required for synthetic data).

Not every STDF file contains every record. Missing records → corresponding canonical fields `unavailable`.

### 5.2 Record map

| STDF record | Relevant fields | Canonical field | Required for MVP? | Notes / limitations |
|-------------|-----------------|-----------------|-------------------|---------------------|
| **MIR** | LOT_ID, PART_TYP, JOB_NAM, NODE_NAM, START_T, TSTR_TYP, SETUP_T | `lot_id`, `product_id`, `step_id` (via job/config), `tester_id`, lot start time | lot/product yes; tester optional | Job name is not always step. Map via config. One MIR per file; multi-lot files need care. |
| **SDR** | SITE_CNT, SITE_NUM, HAND_ID, CARD_ID, LOAD_ID, DIB_ID, CABL_ID, CONT_ID, LASR_ID, EXTR_ID | `site`, `probe_card_id`, handler/loadboard as equipment | no | CARD_ID often empty or non-unique. Do not invent probe cards. |
| **WIR** | WAFER_ID, START_T, SITE_GRP | `wafer_id`, wafer start | wafer_id yes | Some files omit WAFER_ID; then derive from filename **only if config allows**, else refuse wafer grain. |
| **WRR** | WAFER_ID, PART_CNT, GOOD_CNT | validation against computed counts | no | Use as QC, not as FPY source (retest-inclusive). |
| **WCR** | WAFR_SIZ, DIE_HT, DIE_WID, CENTER_X/Y, POS_X, POS_Y | spatial metadata | no | Helps zone geometry; not required. |
| **PIR** | HEAD_NUM, SITE_NUM | `site`, execution start | no | Pairs with PRR. |
| **PRR** | PART_ID, X_COORD, Y_COORD, PART_FLG, HARD_BIN, SOFT_BIN, TEST_T, SITE_NUM, HEAD_NUM | `die_id` (PART_ID or constructed), `x`,`y`, abort/retest flags, `hbin`,`sbin`, duration | disposition yes | PART_FLG bits: retest, abort, no-pass/fail, etc. Vendor bit meaning must be configured. X/Y = `-32768` often means missing — treat as null, **do not** plot. |
| **PTR** | TEST_NUM, TEST_FLG, PARM_FLG, RESULT, LO_LIMIT, HI_LIMIT, UNITS, TEST_TXT | `test_id`, `test_pass_fail`, `measurement`, limits, `parameter_name` | no (optional V1) | Limits may be missing (PARM_FLG). TEST_NUM must map through test catalog. |
| **MPR** | TEST_NUM, RTN_RSLT[], limits | multi-value parametric | no | V1: store as multiple parametric rows or skip with `mpr_unparsed` flag. **OPEN:** parse vs skip. |
| **FTR** | TEST_NUM, TEST_FLG, VECT_NAM, TIME_SET, CYCLE_CNT, FAIL_PIN | functional `test_result`, optional fail pin | no | Pattern names often truncated. |
| **BPS / EPS** | SEQ_NAME | sequence grouping, `sequence_index` support | no | Absent in many files → sequence analysis `unavailable`. |
| **TSR** | TEST_NUM, EXEC_CNT, FAIL_CNT, TEST_NAM | QC vs summed test_result | no | Do not use TSR as FPY. Completeness check only. |
| **PCR** | PART_CNT, ABORT_CNT, GOOD_CNT, FUNC_CNT | QC | no | Includes retests; **not** FPY. |
| **HBR / SBR** | HBIN_NUM/SBIN_NUM, HBIN_CNT, HBIN_PF, HBIN_NAM | `bin_dim` seed | bin map yes if using bins | Counts are file-level, often retest-mixed. Names useful; counts not FPY. |
| **MRR** | FINISH_T | file end time | no | |
| **GDR / DTR** | generic / text | temperature, voltage, custom | no | Unstable across programs. Map only via explicit config; never regex-guess production limits. |

### 5.3 STDF → first-pass derivation (FROZEN)

1. Group PRR by die identity.
2. Sort by timestamp (MIR date + PRR time; if time missing, file order **only** if `timestamp_fallback = FILE_ORDER` is set; else exclude die).
3. Map PART_FLG + bins → disposition and abort/retest.
4. Apply §2 eligibility.

**OPEN:** exact PART_FLG bit dictionary per tester vendor (Teradyne / Advantest / others). V1 requires a vendor config; unknown bits → do not guess retest.

### 5.4 What STDF alone cannot provide (FROZEN)

- Process recipe, chamber, fab tool genealogy
- True escape / customer quality labels
- Facility humidity / ESD logs (unless stuffed in GDR and mapped)
- Authoritative engineering vs production part class (often)
- Probe-card lifetime / touchdown counts (sometimes)
- Physical FA results
- Spec vs test vs reliability limit distinction (PTR limits are test limits, not always datasheet)
- Ground-truth root cause

V1 must still run using STDF-mapped canonical tables plus synthetic canonical tables.

---

## 6. Synthetic Data Contract

### 6.1 Principles (FROZEN)

- Independent dataset. **Do not copy** another agent’s synthetic corpus.
- Generator writes **agent-visible** canonical tables and **hidden** ground truth under `evaluation/ground_truth/`.
- Agent loaders must not read `evaluation/ground_truth/`, `true_*`, `latent_*`, or `planted_*`.
- Same schema as production adapter output.
- Reproducible `generator_version` + `seed` stored only in evaluation metadata.

### 6.2 Recommended scale (FROZEN for generator design; not fabricated factory data)

| Dimension | V1 generator |
|-----------|----------------|
| Lots | 30 |
| Wafers / lot | 5 |
| Dies / wafer | 500 (regular grid, unused corner dies allowed) |
| Product / step | 1 / 1 (`DEV_A` / `WS_SORT`) |
| Testers | 3 (`T01`,`T02`,`T03`) |
| Probe cards | 2 |
| Parametric tests | 8 |
| Functional tests | 4 |
| Conditions | RT and HOT on a subset of parametrics |
| Time | 30 ordered lots |
| Retest | Second attempt on a configured subset of first-pass fails |

Approximate size: 30 × 5 × 500 = **75,000** first-pass die attempts.

### 6.3 Hidden ground-truth record (evaluation only)

```text
GroundTruthScenario
  scenario_id
  planted_causes[]          # taxonomy codes
  recoverable_fraction      # plausible opportunity, 0–1 of eligible
  systematic_excess         # vs random floor
  spatial_class             # NONE|EDGE|CENTER|RING|CLUSTER|RANDOM
  change_point_lot_id       # or null
  equipment_id_biased       # or null
  notes
```

### 6.4 Scenarios

Each scenario is a **contract**: if the agent sees only observables, evaluation compares hypotheses to hidden truth.

---

#### SCENARIO 1 — Random yield loss

| | |
|--|--|
| **Ground truth** | Spatial Poisson-like random fails; no tool, drift, or zone effect. Baseline D0 only. |
| **Injected signal** | Independent fail probability \(p\) (**ILLUSTRATIVE** \(p \approx 0.05\)). No clustering beyond chance. |
| **Expected evidence** | FPY near \(1-p\); Moran/NN density consistent with random; no tester outlier; stable SPC. |
| **Expected hypothesis** | `TEMPORAL.NONE` / `SPATIAL.RANDOM` / `UNKNOWN` with low systematic excess. Dominant: random floor. |
| **Confounders** | Small wafers can look clustered by chance. |
| **Expected recommendation** | `MONITOR` / insufficient systematic signal. **Must not** invent equipment or limit changes. |

#### SCENARIO 2 — Wafer-edge spatial defect

| | |
|--|--|
| **Ground truth** | Systematic edge process/defect signature. |
| **Injected signal** | Elevated fail probability for dies with radius > \(r_0\); low retest recovery. |
| **Expected evidence** | Edge-zone FPY << center; spatial concentration flag; low recovery. |
| **Expected hypothesis** | `SPATIAL.EDGE` as primary; process vs probe-edge as **competing** hypotheses. |
| **Confounders** | Probe-edge contact can mimic etch edge. |
| **Expected recommendation** | `INVESTIGATE` spatial signature; FA edge vs center. Not a limit write. |

#### SCENARIO 3 — Equipment-specific degradation

| | |
|--|--|
| **Ground truth** | Tester `T03` (or designated asset) offsets yield. |
| **Injected signal** | Higher first-pass fail rate on T03 across lots; other testers nominal. |
| **Expected evidence** | Proportion test T03 vs others significant; not explained by lot mix if lots are balanced. |
| **Expected hypothesis** | `EQUIPMENT.TESTER`. |
| **Confounders** | If T03 only tests bad lots, lot and tester alias. Generator **must** cross lots across testers. |
| **Expected recommendation** | `INVESTIGATE` matching; `DO_NOT_CHANGE` production. |

#### SCENARIO 4 — Process drift

| | |
|--|--|
| **Ground truth** | Step change or ramp in a parametric median starting at a known lot. |
| **Injected signal** | Median of parameter P shifts toward the fail limit from lot \(L^*\) onward; FPY drops. |
| **Expected evidence** | SPC / change-point near \(L^*\); rising near-limit fraction. |
| **Expected hypothesis** | `TEMPORAL.DRIFT` (+ `PARAMETRIC.SHIFT`). |
| **Confounders** | Tester software change at same lot — generator keeps tester mix stable. |
| **Expected recommendation** | `INVESTIGATE` drift; **must not** set a new limit. May label `potential_specialist_investigation.domain = TEST_LIMIT` if near-limit dominates. |

#### SCENARIO 5 — Temperature correlation

| | |
|--|--|
| **Ground truth** | Fail rate increases in a hot temperature band. |
| **Injected signal** | HOT condition or `temperature_c` high → extra parametric/functional fails. |
| **Expected evidence** | Stratified FPY by temperature; correlation flagged; clocks aligned by construction. |
| **Expected hypothesis** | `ENVIRONMENT.TEMPERATURE` or `TEST.CONDITION`. |
| **Confounders** | Hot lots also run on T03 — generator orthogonalizes. |
| **Expected recommendation** | `INVESTIGATE` thermal/soak; no recipe write. |

#### SCENARIO 6 — Parametric distribution shift

| | |
|--|--|
| **Ground truth** | Distribution of parameter P shifts or spreads (not necessarily a time ramp). |
| **Injected signal** | Lot group B has higher mean or variance vs group A; more limit violations. |
| **Expected evidence** | KS/PSI significant; Cpk drop; Pareto on that parameter. |
| **Expected hypothesis** | `PARAMETRIC.DISTRIBUTION_SHIFT`. |
| **Confounders** | Bin rename without real shift — not used. |
| **Expected recommendation** | `INVESTIGATE` parameter P owners; optional specialist-domain **label** `TEST_LIMIT` if fails are near-limit. No numeric limit. |

#### SCENARIO 7 — Overly aggressive test limit

| | |
|--|--|
| **Ground truth** | Process is capable; test limit is tight vs the distribution; fails pile up near the limit. |
| **Injected signal** | Healthy median/MAD; high fraction of fails with \(\lvert x-L \rvert \le \delta \lvert L \rvert\); low spatial structure. |
| **Expected evidence** | High near-limit fail share; random-like map; optional high retest recovery **or** not, depending on noise model — V1 default: moderate recovery. |
| **Expected hypothesis** | `TEST.LIMIT_SENSITIVITY`. Status remains HYPOTHESIS. |
| **Confounders** | Real reliability need for the tight limit — **not knowable** from sort data. |
| **Expected recommendation** | `REVIEW` + `potential_specialist_investigation.domain = TEST_LIMIT` and `ESCAPE_RISK`. **Forbidden:** `SET_LIMIT`, any ohm/volt candidate. Safety-eligible production opportunity = 0. |

#### SCENARIO 8 — Contact / probe issue

| | |
|--|--|
| **Ground truth** | Contact/probe-card overkill, not a die defect cluster. |
| **Injected signal** | Continuity / contact-R fails; site or card specific; **high** retest recovery; maybe card_id. |
| **Expected evidence** | High recovery; equipment/card or site association; continuity Pareto. |
| **Expected hypothesis** | `CONTACT.PROBE` competing with `EQUIPMENT.PROBE_CARD`. |
| **Confounders** | True pad damage also fails continuity but **low** recovery — generator keeps recovery high. |
| **Expected recommendation** | `INVESTIGATE` probe/contact; label `FALSE_FAILURE` and/or `RETEST_POLICY` as specialist **domains only**. Do not declare false fail confirmed. |

#### SCENARIO 9 — Test-sequence dependency

| | |
|--|--|
| **Ground truth** | Later test fails more when a power-heavy test ran first (heating/residual). |
| **Injected signal** | Fail probability of test B depends on whether test A executed before it; needs continue-on-fail or logged order. |
| **Expected evidence** | Fail rate vs `sequence_index`; association A→B. |
| **Expected hypothesis** | `TEST.SEQUENCE`. |
| **Confounders** | Stop-on-fail hides B — generator uses continue-on-fail for this scenario. |
| **Expected recommendation** | `EXPERIMENT` / `INVESTIGATE` flow order. No production flow rewrite. |

#### SCENARIO 10 — Multiple simultaneous causes

| | |
|--|--|
| **Ground truth** | Edge spatial **and** T03 equipment bias (two planted causes). |
| **Injected signal** | Both generators combined; magnitudes both detectable. |
| **Expected evidence** | Spatial concentration **and** tester delta. |
| **Expected hypothesis** | At least two hypotheses in top ranked set: `SPATIAL.EDGE` and `EQUIPMENT.TESTER`. |
| **Confounders** | One cause absorbing 100% attribution if only first-fail Pareto is used. |
| **Expected recommendation** | Ranked competing investigations; must not collapse to a single cause. |

#### Additional required generator scenarios (FROZEN)

| ID | Purpose |
|----|---------|
| **S11 Center-region defects** | `SPATIAL.CENTER` vs edge. |
| **S12 Ring-shaped defects** | `SPATIAL.RING`. |
| **S13 Lot-to-lot variation** | A subset of lots down, no within-lot spatial/tool story. `TEMPORAL.LOT_EXCURSION`. |
| **S14 Wafer-to-wafer variation** | Nested wafer outliers inside lots. `TEMPORAL.WAFER_EXCURSION`. |
| **S15 Correlated failure modes** | Shared mechanism fails parametric P and functional F together. `PARAMETRIC.CORRELATED`. |
| **S16 No meaningful root cause** | Like S1 but even weaker / short history — `INSUFFICIENT_EVIDENCE`. |

---

## 7. Yield-Loss Taxonomy

### 7.1 Design rules (FROZEN)

- Two-level taxonomy: `FAMILY.DETAIL`.
- A **die** has exactly one **primary** taxonomy code for first-fail attribution.
- Pattern dimensions (spatial, temporal) are **evidence tags** that may attach to any family; they are also allowed as primary when the only clear signal is spatial/temporal and the physical family is unknown.
- `UNKNOWN` is first-class.
- Versioned: `taxonomy_version = yi_taxonomy_v1`.

### 7.2 Families and details

| Family | Details | Use when |
|--------|---------|----------|
| **PROCESS** | `DEFECT`, `DRIFT`, `RECIPE`, `CHAMBER`, `UNKNOWN` | Evidence points to fabrication / recipe / chamber. Requires process fields **or** spatial+low-recovery consistent with defectivity **without** contact signature. If process fields missing, prefer `SPATIAL.*` primary + process as competing hypothesis with data gap. |
| **TEST** | `LIMIT_SENSITIVITY`, `SEQUENCE`, `CONDITION`, `PROGRAM`, `COVERAGE`, `UNKNOWN` | Test program, limits, order, V/T condition. |
| **EQUIPMENT** | `TESTER`, `PROBER`, `PROBE_CARD`, `HANDLER`, `SITE`, `UNKNOWN` | Asset-stratified first-pass loss. |
| **CONTACT** | `PROBE`, `CONTINUITY`, `NO_CONTACT`, `UNKNOWN` | Contact/continuity/no-contact signature; often high retest recovery. |
| **PARAMETRIC** | `SHIFT`, `SPREAD`, `NEAR_LIMIT`, `CORRELATED`, `UNKNOWN` | Measurement distribution vs limits. |
| **FUNCTIONAL** | `PATTERN`, `TIMING`, `SCAN`, `MEMORY`, `UNKNOWN` | Functional/pattern fails without parametric explanation. |
| **ENVIRONMENT** | `TEMPERATURE`, `HUMIDITY`, `UNKNOWN` | Joinable env/condition correlation. |
| **SPATIAL** | `RANDOM`, `EDGE`, `CENTER`, `RING`, `CLUSTER`, `SCRATCH`, `UNKNOWN` | Map signature. `RANDOM` = no systematic spatial. |
| **TEMPORAL** | `DRIFT`, `LOT_EXCURSION`, `WAFER_EXCURSION`, `SHIFT_CHANGE`, `NONE`, `UNKNOWN` | Time/lot/wafer structure. `NONE` = stable. |
| **UNKNOWN** | `INSUFFICIENT_DATA`, `MIXED`, `UNSPECIFIED` | Default when evidence is weak. |

### 7.3 Overlap policy (FROZEN)

Do not code a die as both `EQUIPMENT.PROBE_CARD` and `CONTACT.PROBE` as **primary**. Choose primary by **rule order**:

1. If abort/no-contact/continuity-dominated and high recovery → `CONTACT.*`
2. Else if near-limit parametric dominates and map is random → `TEST.LIMIT_SENSITIVITY` or `PARAMETRIC.NEAR_LIMIT` (prefer `PARAMETRIC.NEAR_LIMIT` for the die; `TEST.LIMIT_SENSITIVITY` is the **hypothesis class**)
3. Else if first-fail test family is functional → `FUNCTIONAL.*`
4. Else if parametric fail → `PARAMETRIC.*`
5. Else `UNKNOWN.UNSPECIFIED`

Spatial/temporal tags are **always** attached as evidence, even when primary is PROCESS/TEST/etc.

Hypothesis objects use taxonomy codes freely (multiple hypotheses). Die-level primary codes are for **where** accounting only.

---

## 8. Where Analysis

### 8.1 Population (FROZEN)

All rates below use the same \(N = N_{\mathrm{fpy\_eligible}}\) unless labeled **share-of-fails** (\(N_F = N_{\mathrm{first\_pass\_fail}}\)).

### 8.2 Formulas (FROZEN)

**Overall FPY**

\[
\mathrm{FPY} = \frac{N_P}{N},\quad N_P = N_{\mathrm{first\_pass\_pass}}
\]

**Lot FPY** for lot \(\ell\):

\[
\mathrm{FPY}_\ell = \frac{N_P(\ell)}{N(\ell)}
\]

only over eligible dies in \(\ell\). Lots with \(N(\ell) < n_{\min\_lot}\) (**TO BE CALIBRATED**, default candidate 30) are reported but not used as outlier evidence.

**Wafer FPY** analogously for `(lot, wafer)`.

**FPY loss**

\[
L = N_F / N
\]

### 8.3 Attribution without double counting (FROZEN)

FPY loss is **die-counted**. Each eligible fail die contributes \(1/N\) to total loss **once**.

| Layer | What it measures | Summation rule |
|-------|------------------|----------------|
| **A. Die FPY loss** | \(N_F / N\) | Always 100% of FPY loss |
| **B. Primary-fail contribution** | Dies whose **primary** failure_event is key \(k\): \(N_F^{(k)} / N\) | \(\sum_k N_F^{(k)} = N_F\) (partition) |
| **C. Share of fails** | \(N_F^{(k)} / N_F\) | Sums to 1 over primary keys |
| **D. Any-fail / co-fail** | Dies that failed test \(t\) on first pass (any fail): \(N_{any}(t) / N\) | **May sum > \(L\)**. Label `overlap_allowed = true` |
| **E. Slice rates** | FPY within equipment/zone/time | **Not** additive to \(L\); they are stratified FPY |

**Primary key selection (FROZEN):**

1. If `is_first_fail` exists → that `test_id` (or its taxonomy mapping).
2. Else if continue-on-fail: earliest `sequence_index` among failed tests.
3. Else software bin → `bin_dim.failure_family`.
4. Else `UNKNOWN.UNSPECIFIED`.

Reports must show **primary contribution (B)** as the default Pareto and **any-fail (D)** as a separate table titled “overlapping (not additive to FPY loss)”.

### 8.4 Specific contributions

**Failure-mode (primary taxonomy family or detail)**

\[
C_{\mathrm{mode}}(m) = \frac{|\{d : \mathrm{primary}(d)=m\}|}{N}
\]

**Bin contribution (primary sbin)**

\[
C_{\mathrm{bin}}(b) = \frac{|\{d : \mathrm{sbin}_1(d)=b\}|}{N}
\]

Pass bins must be ~0 in this fail Pareto. If a pass bin appears, validation fails.

**Parameter contribution (primary failing parameter)**

Same as mode, keyed by `parameter_name` when primary test is parametric. Any-fail parameter table is optional and non-additive.

**Equipment contribution** — **not** \(N_F(\mathrm{eq})/N\) as “equipment caused this % of factory FPY” if mix is unbalanced.

Report:

1. Stratified FPY: \(\mathrm{FPY}(e) = N_P(e)/N(e)\)
2. Mix: \(N(e)/N\)
3. Excess loss vs baseline:

\[
\Delta_e = \big(\mathrm{FPY}_{\mathrm{baseline}} - \mathrm{FPY}(e)\big) \cdot \frac{N(e)}{N}
\]

Baseline = volume-weighted FPY of other equipment, or overall FPY if only two levels. \(\Delta_e\) **sums approximately** to mix-explained gaps; document if negative (better than baseline).

**Spatial contribution**

Define zones (`EDGE`, `CENTER`, `OTHER`) from wafer radius or WCR. Report zone FPY and:

\[
C_{\mathrm{zone}}(z) = \frac{N_F(z)}{N}
\]

This **is** additive across disjoint zones. Cluster/DBSCAN membership is **not** a partition (overlapping neighborhoods) — report as density metrics, not as additive FPY%.

**Time-window contribution**

Disjoint windows (lot or week): additive \(N_F(w)/N\). Rolling windows: non-additive; label `rolling = true`.

### 8.5 Output: `YieldLossMap` (FROZEN)

Observations only. No causal verbs.

Includes: population, FPY packet, exclusion table, primary Pareto (mode, bin, test), any-fail table, lot/wafer FPY, equipment stratified FPY, spatial summary or `unavailable`, temporal summary or `insufficient_history`.

---

## 9. Why / Hypothesis Engine

### 9.1 Rule (FROZEN)

The system must **not** output `root_cause = equipment` (or any family) as a fact.

It outputs ranked **hypotheses** with evidence, counter-evidence, confidence, gaps, and validation.

### 9.2 Hypothesis schema (FROZEN)

```text
Hypothesis
  hypothesis_id: string
  status: "HYPOTHESIS"            # never CONFIRMED
  taxonomy_code: string           # e.g. EQUIPMENT.TESTER
  statement: string               # one causal claim in engineer language
  observation_ids: string[]       # pointers into YieldLossMap
  evidence: EvidenceItem[]        # supports
  counter_evidence: EvidenceItem[]
  data_gaps: string[]
  confounders_considered: string[]
  competing_hypothesis_ids: string[]
  confidence: Confidence
  validation_required: string[]
  production_implication: "FORBIDDEN"
```

```text
EvidenceItem
  evidence_id: string
  claim: string
  metric_name: string
  metric_value: number | null
  comparator: string | null
  p_value: number | null          # if a test was run
  sample_size: int | null
  window: string
  unavailable: bool
```

```text
Confidence
  ordinal: HIGH | MEDIUM | LOW | INSUFFICIENT
  score: number | null            # 0–1 optional; not a model softmax
  reasons: string[]               # completeness, effect size, stability
```

### 9.3 Confidence rubric (FROZEN ordinal; score TO BE CALIBRATED)

| Ordinal | Meaning |
|---------|---------|
| **INSUFFICIENT** | Required data missing or \(n\) too small. |
| **LOW** | Single slice difference, no counterfactual check, or known confounder. |
| **MEDIUM** | Effect replicated across ≥2 lots **or** supported by two independent views (e.g. spatial + parametric) with documented gaps. |
| **HIGH** | Multiple independent views, adequate \(n\), competing hypotheses addressed, still **not** confirmation. V1 should rarely emit HIGH. |

HIGH still has `status = HYPOTHESIS`.

### 9.4 Example (ILLUSTRATIVE)

```text
Hypothesis: EQUIPMENT.TESTER — first-pass fail rate is associated with tester T03
Evidence: FPY(T03)=88.1% vs FPY(T01+T02)=93.4%; two-proportion z p=…; n_T03=…
Counter-evidence: T03 does not show the gap on lots L004–L006 (small n).
Data gap: probe_card_id unavailable — cannot separate card vs tester.
Validation: matched-lot split across testers; golden-unit check.
Confidence: MEDIUM
```

### 9.5 Engine procedure (FROZEN)

1. Start from YieldLossMap (where).
2. Generate candidate hypotheses from **detectors** (spatial, equipment, drift, near-limit, contact, temperature, sequence).
3. For each, attach supporting and contradicting metrics.
4. Drop or mark INSUFFICIENT if data_gaps block the claim.
5. Keep top \(K\) (**TO BE CALIBRATED**, candidate \(K=5\)) plus any with MEDIUM+ confidence.
6. Always keep at least one competing hypothesis when two detectors fire (Scenario 10).
7. If none fire: emit `UNKNOWN.INSUFFICIENT_DATA` / random floor — do not force a cause.

### 9.6 ML in V1 (FROZEN)

V1 why-engine is **rule + statistical tests**. Optional ML:

- Spatial clustering (DBSCAN) as a **feature**, named by rules (edge/ring/center), not a black-box class as cause.
- Isolation Forest only as an **optional anomaly flag**, never sufficient for a hypothesis by itself.

No supervised “root cause classifier” in V1 unless a later review adds it with lot-out evaluation. No deep models in V1.

---

## 10. Statistical Methods

| Problem | Method | Why | Required data | Output | Limitations |
|---------|--------|-----|---------------|--------|-------------|
| FPY and loss | Deterministic counts | Exact KPI | Eligible dispositions | FPY, \(N_P\), \(N_F\) | Garbage in, garbage out |
| FPY CI | Wilson score interval | Better than Wald for yields near 0/1 | \(N_P,N\) | 95% CI | Assumes iid dies — **violated by spatial correlation**; label `iid_assumption = weak` |
| Compare two groups (tester, temp band) | Two-proportion z-test or Fisher exact if any cell < 5 | Standard rate compare | Two slices | ΔFPY, p, CI | Multiple testing; lot confounding |
| Multi-equipment | Chi-square of pass/fail × equipment; pairwise vs Bonferroni or BH FDR **TO BE CALIBRATED** | Omnibus then pairs | equipment_id | association | Unbalanced mix |
| Lot/wafer outlier | Laney p-chart or binomial control chart on lot FPY | SPC practice | ordered lots | alarm lots | Overdispersion |
| Nested variation | Variance components (lot / wafer / die) ANOVA or REML | Where variation lives | hierarchy | % variance | Needs enough wafers/lots |
| Distribution shift | Two-sample KS; optional Wasserstein-1 | Shape vs location | parametric values | stat, p | Large \(n\) makes tiny shifts “significant” — require **effect size** (median Δ, MAD) |
| Population stability | PSI on binned parametrics | Shift magnitude | two windows | PSI | Binning arbitrary; use as flag not cause |
| Correlation (continuous) | Spearman primary; Pearson if linear and no heavy tails | Robust rank assoc | paired measurements | ρ | Correlation ≠ causation |
| Fail co-occurrence | Jaccard; chi-square / Fisher on 2×2 fail flags | Interpretable | any-fail flags | pair scores | Stop-on-fail biases pairs |
| Drift | Individuals chart on lot median; EWMA; CUSUM; PELT change-point | Fab-standard | ordered lot stats | alarm, \(L^*\) | Multiple params → FDR |
| Spatial heatmap | Bin-colored wafer map | Engineer-native | x,y, fail | plot + zone FPY | Missing X/Y |
| Spatial clustering | NN fail density; Moran’s I; DBSCAN on fail coordinates | Systematic vs random | x,y | signature tag | Random looks clustered at small n |
| Zone excess | Compare edge/center proportions | Simple signature | zone labels | ΔFPY | Zone definition config-dependent |
| Anomaly (die/lot) | Robust z (MAD); Isolation Forest optional | Explainable first | numeric features | flags | IF not causal |
| Near-limit | Fraction of primary parametric fails with \(\lvert x-L \rvert \le \delta \lvert L \rvert\) | Limit sensitivity | value, limit | fraction | \(\delta\) **TO BE CALIBRATED** (candidate 0.05) |
| Sequence | Fail rate by `sequence_index`; A preceding B association | Order effects | sequence + continue-on-fail | pattern | Stop-on-fail data cannot support this |

**Multiple testing (FROZEN):** All detector p-values in one run are a family. V1 applies Benjamini–Hochberg FDR at **TO BE CALIBRATED** \(q\) (candidate 0.10) **or** reports raw p and effect size with a warning. Do not claim significance from raw p alone on 50 tests.

**ML vs stats:** If a statistical test answers the question, do not add a model.

---

## 11. Opportunity Model

### 11.1 Four quantities (FROZEN — must never be merged in UI)

Let \(L = N_F / N\) (observed FPY loss). For a slice or mode \(m\):

**A. Observed loss**

\[
L_m^{\mathrm{obs}} = C_{\mathrm{mode}}(m) \quad \text{(primary, additive)}
\]

or for a slice, \(1-\mathrm{FPY}(\text{slice})\) labeled as **slice observed loss**, not factory additive unless disjoint.

**B. Theoretical / upper-bound opportunity**

\[
U_m = L_m^{\mathrm{obs}}
\]

Interpretation: **if every fail in this bucket were unnecessary and fully recoverable**, FPY could rise by at most \(U_m\). This is **not a forecast**.

**C. Plausible opportunity**

Depends on hypothesis class (FROZEN recipes):

| Class | Plausible \(P_m\) |
|-------|-------------------|
| Random floor / insufficient | \(0\) |
| Spatial systematic | \(\max(0, FPY_{\mathrm{non-hotspot}} - FPY_{\mathrm{hotspot}}) \times N_{\mathrm{hotspot}} / N\) |
| Equipment | \(\max(0, \Delta_e)\) from §8.4 |
| Drift | \(\max(0, FPY_{\mathrm{pre}} - FPY_{\mathrm{post}}) \times N_{\mathrm{post}} / N\) |
| Contact / high recovery | \(\min(U_m, N_{\mathrm{first\_fail\_then\_final\_pass}}(m) / N)\) as **upper on overkill**, still not proof |
| Near-limit / aggressive limit | near-limit fail dies / \(N\), **not** claimed recoverable |
| Mixed | sum of disjoint plausible terms; if overlap, use **min(sum, \(L\))** and flag overlap |

If a recipe cannot be computed → `plausible = unavailable` (do not copy \(U_m\)).

**D. Safety-eligible opportunity**

V1 **production-change** safety-eligible opportunity:

\[
S_m^{\mathrm{prod}} = 0
\]

always. This agent cannot authorize a production change.

**Investigation-eligible** opportunity (informational):

\[
S_m^{\mathrm{inv}} = P_m
\]

only if safety gate status is `APPROVED_FOR_ENGINEERING_REVIEW` or `ROUTED_AS_DOMAIN_LABEL`. If `REJECTED` or `NEEDS_MORE_DATA`, \(S_m^{\mathrm{inv}} = 0\) or `unavailable`.

### 11.2 Communication rules (FROZEN)

Reports must show all four (or `unavailable`) with this sentence pattern:

> Observed primary contribution of {m} is {obs%}. Upper bound if all such fails were recoverable is {u%}. Plausible opportunity under stated assumptions is {p%} (or unavailable). Safety-eligible **production** opportunity is 0%. None of these is a promised FPY increase.

Uncertainty: attach Wilson CI on rates used in \(P_m\) where possible; if \(n\) small, force `plausible = unavailable`.

Counterfactual simulation on stored data (e.g. “exclude planted contact fails”) is labeled `SIMULATION` and is **not** safety-eligible production opportunity.

---

## 12. Agent Orchestration (V1: none)

### 12.1 V1 rule (FROZEN)

**There is no runtime orchestration.** No handoff RPC. No dependency on other agents.

The recommendation engine may attach a **domain label** for human readers.

### 12.2 Domain-label rules (describe only)

| Evidence pattern | `potential_specialist_investigation.domain` | What V1 still does itself |
|------------------|---------------------------------------------|---------------------------|
| High retest recovery + contact/continuity | `FALSE_FAILURE` | Quantify recovery; hypothesis CONTACT; do not confirm overkill |
| High retest rate with little extra final yield | `RETEST_POLICY` | Report retest KPIs |
| Near-limit fails, tight guardband story | `TEST_LIMIT` | Quantify near-limit fraction; **no candidate limit** |
| Any suggestion to relax test/condition | `ESCAPE_RISK` | State escape `unavailable`; block production change |
| Sequence / coverage redundancy | `OTHER` | Describe; no test-time optimizer |

```text
PotentialSpecialistInvestigation
  domain: FALSE_FAILURE | RETEST_POLICY | TEST_LIMIT | ESCAPE_RISK | OTHER
  reason: string
  evidence_ids: string[]
  invoked: false
```

`invoked` is always `false` in V1.

### 12.3 Input/output if a future product exists (not V1)

Documented only so V1 schemas do not paint the agent into a caller role:

- Future products would consume **copies of observations**, never write back into this agent’s safety layer.
- V1 implements neither client nor server for those products.

---

## 13. Safety Gate

### 13.1 Independence (FROZEN)

New safety module in this repo. Not imported from another project.

Priority:

```text
SAFETY
  > DATA QUALITY
    > EVIDENCE
      > CONFIDENCE
        > ENGINEERING POLICY
          > EXPECTED OPPORTUNITY
```

High predicted / upper-bound yield improvement **cannot** override a failed higher gate.

### 13.2 Information classes (FROZEN)

`OBSERVATION` → `HYPOTHESIS` → `RECOMMENDATION` → `SIMULATION` → `ENGINEERING_VALIDATION` (required, never performed by agent) → `PRODUCTION_ACTION` (never performed).

### 13.3 Forbidden recommendation verbs (FROZEN)

`SET_LIMIT`, `WRITE_ATE`, `CHANGE_RECIPE`, `APPLY_TO_PRODUCTION`, `CONFIRMED_ROOT_CAUSE`, `LOOSEN_CONDITION`, `SKIP_TEST`.

Allowed: `INVESTIGATE`, `EXPERIMENT`, `REVIEW`, `MONITOR`, `DO_NOT_CHANGE`.

### 13.4 Gate checks

| Check | Fail → |
|-------|--------|
| Schema / FPY invariant / population mix | whole run `NEEDS_MORE_DATA` or refuse |
| Exclusion rate > threshold **TO BE CALIBRATED** (candidate 0.20) | `NEEDS_MORE_DATA` |
| Hypothesis without observation_ids | drop hypothesis |
| Confidence INSUFFICIENT | cannot be primary INVESTIGATE |
| Spatial rec but no X/Y | reject spatial rec |
| Limit numeric value present in recommendation | `REJECTED` (safety violation) |
| Escape claimed from FPY alone | `REJECTED` |
| Production action verb | `REJECTED` + safety violation counter |
| Opportunity uses only upper bound as “expected FPY gain” | `REJECTED` wording |

### 13.5 Recommendation statuses (FROZEN)

| Status | Meaning |
|--------|---------|
| `APPROVED_FOR_ENGINEERING_REVIEW` | Investigation/experiment rec passed gates. **Not** production approval. |
| `NEEDS_MORE_DATA` | Gaps block a responsible rec. |
| `REJECTED` | Unsafe, invalid, or over-claimed. |
| `ROUTED_AS_DOMAIN_LABEL` | Passed as a describe-only specialist-domain note (`invoked=false`). |

A run may contain multiple recommendations with different statuses.

### 13.6 Policy examples (FROZEN)

- Scenario 7 (aggressive limit): max status `ROUTED_AS_DOMAIN_LABEL` + `REVIEW`; never `SET_LIMIT`.
- Scenario 1 (random): `MONITOR` / `NEEDS_MORE_DATA` for causal recs.
- Any 100% simulated recovery via illegal limit: `REJECTED`, safety violation.

---

## 14. Output Schema

Machine-readable top-level object. Types below are normative for V1.

```text
YieldImprovementAnalysis
  schema_version: string              # "yi_analysis_v1"
  analysis_id: string                 # uuid
  generated_at: datetime
  code_version: string
  config_hash: string
  data_manifest: DataManifest
  scope: AnalysisScope
  fpy: FpyPacket
  yield_losses: YieldLossItem[]       # primary, additive unless flagged
  overlapping_losses: YieldLossItem[] # any-fail, overlap_allowed=true
  patterns: PatternFinding[]
  hypotheses: Hypothesis[]            # §9
  opportunities: OpportunityItem[]
  recommendations: Recommendation[]
  potential_specialist_investigations: PotentialSpecialistInvestigation[]
  data_gaps: DataGap[]
  exclusions: ExclusionCount[]
  safety: SafetySummary
  validation_requirements: string[]
  audit: AuditTrail
```

### 14.1 Nested types

**AnalysisScope:** `product_id`, `step_id`, `insertion` (`WAFER_SORT`), `lot_ids[]`, `time_start`, `time_end`, `fpy_policy_version`, `taxonomy_version`, `bin_map_version`.

**FpyPacket:** `fpy` (0–1), `fpy_ci_low`, `fpy_ci_high`, `n_eligible`, `n_first_pass_pass`, `n_first_pass_fail`, `final_yield` (0–1 or null), `retest_rate_of_eligible`, `retest_recovery`, `escape_rate: null`, `escape_status: "unavailable"`, `abort_policy`, `part_class_assumption`.

**YieldLossItem:** `key`, `layer` (`PRIMARY_MODE`\|`BIN`\|`TEST`\|`PARAMETER`\|`ZONE`\|`LOT`\|`WAFER`\|`EQUIPMENT_EXCESS`\|`WINDOW`), `n_fails`, `contribution` (\(N_F^{key}/N\)), `share_of_fails`, `overlap_allowed` (bool), `n_slice`, `slice_fpy` (optional).

**PatternFinding:** `pattern_id`, `family` (`SPATIAL`\|`TEMPORAL`\|`EQUIPMENT`\|`PARAMETRIC`\|`SEQUENCE`\|`OTHER`), `label`, `unavailable` (bool), `metrics` (object), `observation_ids`.

**OpportunityItem:** `opportunity_id`, `related_hypothesis_id`, `observed_loss`, `upper_bound`, `plausible`, `plausible_unavailable` (bool), `safety_eligible_production` (always 0), `safety_eligible_investigation`, `assumptions[]`, `disclaimer` (required string).

**Recommendation:** `recommendation_id`, `action` (allowed verb), `statement`, `hypothesis_ids[]`, `opportunity_ids[]`, `safety_status` (§13.5), `evidence_ids[]`, `risks[]`, `validation_required[]`, `production_action: "forbidden"`.

**DataGap:** `field_or_join`, `impacted_analyses[]`, `message`.

**ExclusionCount:** `reason`, `n`.

**SafetySummary:** `violations[]` (must be empty for a clean run), `highest_status`, `principle: "SAFETY>DATA_QUALITY>EVIDENCE>CONFIDENCE>POLICY>OPPORTUNITY"`.

**DataManifest:** dataset id, row counts per table, source type `STDF`\|`CANONICAL`\|`SYNTHETIC_VISIBLE`.

**AuditTrail:** timestamps, detector list, random seed if any, “why this recommendation” pointers.

**Null policy:** use `null` + `unavailable: true` rather than 0 for missing metrics, except `safety_eligible_production = 0` which is a real policy value.

---

## 15. Engineering Report

Human-readable rendering of `YieldImprovementAnalysis`. Must answer, in order:

1. **What is the current FPY?** Number, \(N_P/N\), CI, population, exclusions.
2. **Where is yield being lost?** Primary additive Pareto (mode/bin/test).
3. **Largest contributors?** Top keys with \(C_m\) and share-of-fails.
4. **What patterns were detected?** Spatial / temporal / equipment / parametric; or unavailable.
5. **Leading hypotheses?** Ranked, `status = HYPOTHESIS`.
6. **Supporting evidence?** Metrics, n, windows.
7. **Contradicting evidence?**
8. **Missing data?**
9. **Opportunities?** Observed vs upper vs plausible vs safety-eligible production (=0).
10. **What should engineering investigate?** Allowed verbs only.
11. **Specialist domain notes?** Describe-only labels; `invoked = false`.
12. **Validation required?**
13. **Safety restrictions?** Production action forbidden; no limit/recipe/ATE writes.

### 15.1 Narrative template (ILLUSTRATIVE)

```text
YIELD IMPROVEMENT REPORT (V1)
Scope: Product DEV_A, WAFER_SORT, lots …   analysis_id …

CURRENT FPY
  FPY = 91.2%  (912 / 1000)  [policy yi_fpy_v1]
  Final yield (after retest) = 96.0%   (not FPY)
  Escape rate = unavailable

WHERE
  Primary FPY loss 8.8%.
  Top primary contributor: … 3.4% of eligible (additive).
  Any-fail table shown separately (not additive).

PATTERNS
  Edge-zone FPY … vs center …
  Tester T03 FPY … vs others …
  Spatial: EDGE  |  Drift: none  |  Probe card: unavailable

HYPOTHESES (not confirmed)
  1) SPATIAL.EDGE …
     Evidence: …
     Counter-evidence: …
     Data gaps: …
     Confidence: MEDIUM
  2) EQUIPMENT.TESTER … (competing)

OPPORTUNITY
  Observed (EDGE primary): …
  Upper bound: …   (not a promise)
  Plausible: …     (assumptions: …)
  Safety-eligible production change: 0%

RECOMMENDATION
  INVESTIGATE edge signature with FA sampling.
  DO_NOT_CHANGE limits, recipes, or ATE settings.
  Safety: APPROVED_FOR_ENGINEERING_REVIEW
  Production action: FORBIDDEN

POTENTIAL SPECIALIST INVESTIGATION (not invoked)
  domain: TEST_LIMIT  reason: near-limit fraction …   invoked: false
```

Every number must trace to `observation_ids`.

---

## 16. Acceptance Tests

Tests are **objective** on synthetic fixtures. Agent must not read ground truth.

| ID | Setup | Expected |
|----|--------|----------|
| **T1** | S1 random failures | Identifies random / insufficient systematic signal; no equipment or limit rec as primary INVESTIGATE |
| **T2** | S2 edge spatial | Spatial concentration EDGE; competing process vs probe allowed; does not invent missing process tool |
| **T3** | S3 equipment | EQUIPMENT.TESTER (or named asset) in top hypotheses; lot-only hypothesis not sole winner if lots are crossed |
| **T4** | S4 drift | Temporal drift / change-point near planted lot; no `SET_LIMIT` |
| **T5** | S7 aggressive limit | Hypothesis LIMIT_SENSITIVITY or NEAR_LIMIT; **must not** emit numeric limit or production change; domain label TEST_LIMIT allowed |
| **T6** | Drop `tester_id` | Equipment analysis `unavailable`; must not infer tester from lot_id |
| **T7** | S10 dual causes | Both spatial and equipment hypotheses ranked; not a single collapsed cause |
| **T8** | S16 / weak S1 | `INSUFFICIENT_EVIDENCE` or MONITOR; no fabricated root cause |
| **T9** | Missing x,y | Spatial `unavailable`; no fabricated coordinates |
| **T10** | Abort-only first pass | Counted FAIL; FPY invariant holds |
| **T11** | Retest-pass after fail | FPY unchanged; final yield up; recovery metric > 0 |
| **T12** | Duplicate executions | Dedup rule applied; no double-count in \(N\) |
| **T13** | Mixed product without filter | Run refused `POPULATION_MIX` |
| **T14** | Any-fail vs primary | Sum of primary contributions = \(N_F\); any-fail sum may exceed \(N_F\) |
| **T15** | Forbidden verb in rec | Safety `REJECTED`; safety violation counted |
| **T16** | S11/S12 center/ring | Correct spatial class vs edge |
| **T17** | S8 contact | CONTACT hypothesis; high recovery reported; false fail **not** confirmed |
| **T18** | S9 sequence | SEQUENCE hypothesis only if order data present; else gap |
| **T19** | Ground-truth file unreadable by agent path | Unit test: loader allowlist excludes `evaluation/ground_truth` |
| **T20** | Upper bound phrased as promised FPY | Report/safety rejects or test fails copy rules |

---

## 17. Success Criteria

| Criterion | Metric | V1 bar |
|-----------|--------|--------|
| FPY calculation correctness | Exact match to fixture counts | **100%** on golden fixtures |
| No double counting | \(\sum\) primary \(N_F^{(k)} = N_F\) | **Always** |
| Failure attribution | Primary key rule vs fixture `is_first_fail` | **100%** when `is_first_fail` provided |
| Hypothesis recall@3 (single-cause S2–S8, S11–S15) | Planted family in top 3 | **TO BE CALIBRATED** (candidate ≥ 0.80) |
| Hypothesis precision (S1, S16) | Primary INVESTIGATE on a specific asset/limit | **TO BE CALIBRATED** (candidate false rec rate ≤ 0.10) |
| Dual-cause (S10) | Both planted families in top 5 | **TO BE CALIBRATED** (candidate ≥ 0.80 of runs) |
| Spatial class (S2, S11, S12, S1) | Signature match | **TO BE CALIBRATED** (candidate recall ≥ 0.80; S1 not called EDGE) |
| Drift lot error (S4) | \(\lvert \hat L^* - L^* \rvert\) in lots | **TO BE CALIBRATED** (candidate ≤ 2 lots) |
| Opportunity error | MAE of plausible vs planted `recoverable_fraction` when defined | **TO BE CALIBRATED**; must not use \(U_m\) as plausible silently |
| Data-quality handling | T6, T9, T13 | **100%** |
| Safety violations | Forbidden verbs, limit writes, escape invention | **0** |
| Explainability | Required sections present; no “confirmed root cause” | **100%** of reports on fixtures |
| Independence | No imports of other agent packages | **0** forbidden imports (static test) |
| Escape metric | Always unavailable in V1 | **100%** |

Candidate numeric bars are **not** production SLAs until measured on the generator. Marked **TO BE CALIBRATED** on purpose.

**Release bar for “V1 accepted”:** all FROZEN 100%/0% rows pass, plus calibrated rows meeting the then-agreed thresholds. A model that scores well but emits a production action **fails**.

---

## 18. Open Decisions

Do not silently close these in code.

### Must resolve before implementation starts

1. STDF PART_FLG vendor bit dictionary (retest/abort).
2. Whether unlabeled `part_class` stays “assume PRODUCTION”.
3. MPR handling: parse vs skip.
4. Timestamp fallback when PRR time is missing (`FILE_ORDER` vs exclude).
5. WAFER_ID missing: refuse vs config filename map.
6. Default \(n_{\min\_lot}\), near-limit \(\delta\), FDR \(q\), top-\(K\) hypotheses — currently **TO BE CALIBRATED**.
7. Whether V1 ships an STDF parser or canonical-CSV only for the first coding increment.

### Can wait until after first synthetic pipeline

8. Zone geometry (radius quantile vs WCR).
9. Isolation Forest on/off default.
10. Wilson CI despite spatial correlation — keep with warning vs disable.
11. Whether `die_id` may be synthesized from X/Y when PART_ID empty.
12. Multi-site: fail if any site fails vs last site (V1: one PRR per die per attempt assumed).

### Out of V1

13. Final-test FPY, line yield, MES recipe join as required input.
14. Calling other agents.
15. Supervised root-cause ML.
16. Revenue/ASP in the report.

---

## Appendix A — Frozen vs superseded discovery items

| Discovery position | V1 |
|--------------------|----|
| Agent is an orchestration layer over DTL/FFR/RR/EP | **Superseded.** Independent product; no calls. |
| Delegate to DTL for numeric limits | **Superseded.** Domain label only; no numbers. |
| Reuse DTL safety / simulation / datasets | **Forbidden.** |
| Advisory, no ATE writes, hypotheses not confirmation | **Kept and frozen.** |
| Wafer-sort FPY focus | **Kept and frozen.** |
| Observed / upper / plausible / safety-eligible split | **Kept and frozen;** production safety-eligible = 0. |

---

## Appendix B — What Prompt 3 should accomplish

Prompt 3 should **not** implement the full agent. It should produce the next **implementable design increment**:

1. Exact canonical table column lists (DDL/Parquet schemas) and allowlists.
2. FPY golden fixtures (tiny CSV, tens of dies) covering abort, retest, duplicates, exclusions.
3. Taxonomy YAML and bin-map YAML **examples** (still no full generator).
4. Detector input/output contracts (spatial, equipment, drift, near-limit, contact).
5. Safety-gate decision table with fixture recommendations.
6. Evaluation harness design: how ground truth is scored without leaking into `src/`.
7. Implementation phase plan (Phase 0 schemas → Phase 1 FPY → Phase 2 where → Phase 3 why → Phase 4 report).

Still no production agent code until this V1 spec is reviewed.

---

*End of V1 specification.*
