# Yield Improvement Agent — V1 Implementation Contract

**Status:** Contract phase — no production agent implementation  
**Authoritative parent:** `docs/YIELD_IMPROVEMENT_AGENT_V1_SPEC.md`  
**Date:** 2026-09-22  
**Independence:** Standalone product. Other agents are **labels only** (`invoked: false`). No imports, APIs, datasets, or safety code from any other agent.

---

## 0. Repository inspection (this workspace)

Inspected: `C:\Users\Keerthan\OneDrive\Desktop\yeild agent`

| Item | Found |
|------|--------|
| Directory structure | Essentially empty except `docs/` |
| Existing files (before this phase) | `docs/YIELD_IMPROVEMENT_AGENT_DISCOVERY.md`, `docs/YIELD_IMPROVEMENT_AGENT_V1_SPEC.md` |
| Datasets | None |
| Python environment / `pyproject.toml` / `requirements.txt` | **None** |
| Test framework | **None** (pytest not configured) |
| Source package | **None** |
| Other agent code | **None in this repo** (must stay that way) |

This is a **clean standalone project**. This phase adds contracts, configs, and tiny FPY fixtures only.

Discovery §12/§15 (orchestration over other agents) remains **superseded** by the V1 spec.

---

## 1. Canonical data contract

### 1.1 Design

- **Primary analytical grain:** unique die × attempt  
  Identity: `(lot_id, wafer_id, die_id)` × `attempt_id`
- Tables are **this product’s** schema. Do not concatenate grains.
- **Forbidden columns** on agent-visible tables: `true_*`, `latent_*`, `planted_*`, `scenario_id`, `expected_hypothesis`, `generator_seed`, `recoverable_fraction` (see `configs/allowlist.yaml`).
- Optional V1 tables (`process_fact`, `environment_fact`) are omitted from the **MVP physical schema** below. If absent, related detectors return `UNAVAILABLE`.

Normalized tables for V1 coding:

| Table | Grain | Required for FPY? |
|-------|--------|-------------------|
| `lot_dim` | lot | yes (product/step) |
| `wafer_dim` | lot × wafer | yes |
| `part_dim` | lot × wafer × die | yes |
| `die_attempts` | die × attempt | **yes — primary fact** |
| `test_results` | attempt × test | no (Pareto) |
| `failures` | first-pass fail die × role × key | derived, not raw input |
| `parametric_measurements` | attempt × parameter × condition | no |
| `equipment_dim` | asset | no |

Golden FPY fixtures denormalize lot/part fields onto `die_attempts.csv` so tests do not need a database. The **logical** schema is still the tables below.

Types: `string`, `int`, `float`, `bool`, `datetime` (UTC ISO-8601), `enum`.

Empty CSV cells = SQL `NULL`.

---

### 1.2 `lot_dim`

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| lot_id | string | no | non-empty | Lot PK | unique | `L001` |
| product_id | string | no | non-empty | Device | constant per analysis run | `DEV_A` |
| step_id | string | no | `WS_SORT` in V1 | Operation | must be wafer-sort | `WS_SORT` |
| start_ts | datetime | yes | UTC | Lot start | parseable | `2026-03-01T08:00:00Z` |
| quantity_declared | int | yes | ≥ 0 | Declared qty | | `500` |
| hold_flag | bool | yes | | Hold | default false if null | `false` |

---

### 1.3 `wafer_dim`

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| lot_id | string | no | | FK lot | exists in lot_dim | `L001` |
| wafer_id | string | no | non-empty | Wafer id | unique per lot | `W01` |
| slot | int | yes | ≥ 1 | Slot | | `5` |
| process_tool_id | string | yes | | Process tool | never inferred from tester | `PT-2` |
| process_chamber_id | string | yes | | Chamber | | `CH-A` |
| start_ts | datetime | yes | UTC | | | |

PK: `(lot_id, wafer_id)`.

---

### 1.4 `part_dim` (die)

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| lot_id | string | no | | | | `L001` |
| wafer_id | string | no | | | | `W01` |
| die_id | string | no | non-empty | Unique on wafer | unique per (lot,wafer) | `D01` |
| product_id | string | no | | | matches lot | `DEV_A` |
| part_class | enum | **yes** | `PRODUCTION`, `ENGINEERING`, `CALIBRATION`, `QA_SAMPLE`, `REWORK`, `UNKNOWN` | Class | null → assume PRODUCTION + flag | `PRODUCTION` |
| x | float | yes | finite; not `-32768` | Wafer X | missing → no spatial for die | `4` |
| y | float | yes | finite | Wafer Y | | `1` |
| site | int | yes | ≥ 0 | Parallel site | stratifier only | `0` |
| is_rework | bool | yes | | Rework return | true → exclude FPY | `false` |
| is_engineering | bool | yes | | Convenience flag | must agree with part_class | `false` |
| is_calibration | bool | yes | | Convenience flag | must agree with part_class | `false` |

PK: `(lot_id, wafer_id, die_id)`.  
If `die_id` missing: **OPEN** (spec fallback X/Y only if unique). Fixtures always supply `die_id`.

Flag consistency: if `part_class=ENGINEERING` then `is_engineering=true`. If flags disagree → `DATA_QUALITY_FAILURE` on that die.

---

### 1.5 `die_attempts` (primary fact — UNIQUE DIE × ATTEMPT)

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| attempt_id | string | no | unique | PK (`test_execution_id` in spec) | unique | `E-L001-W01-D01-1` |
| lot_id | string | no | | | | `L001` |
| wafer_id | string | no | | | | `W01` |
| die_id | string | no | | | | `D01` |
| product_id | string | no | | | run-constant | `DEV_A` |
| step_id | string | no | `WS_SORT` | | | `WS_SORT` |
| part_class | enum | yes | see part_dim | | missing → assume PRODUCTION + flag | `PRODUCTION` |
| timestamp | datetime | no* | UTC | Attempt time | *if missing: exclude die unless OPEN fallback (not enabled in fixtures) | `2026-03-01T10:00:01Z` |
| attempt_number | int | no | ≥ 1 | 1 = first | | `1` |
| is_first_attempt | bool | no | | First-pass candidate | must be true iff attempt_number==1 after normalize | `true` |
| is_retest | bool | no | | Retest | true iff attempt_number≥2 | `false` |
| is_rework | bool | no | | Rework | true → exclude | `false` |
| abort_flag | bool | no | | Abort | null treated as false | `false` |
| disposition | enum | yes | `PASS`, `FAIL`, `ABORT`, `UNKNOWN` | Optional derived | if present must match pass_fail/abort rules | `FAIL` |
| pass_fail | enum | yes | `PASS`, `FAIL` | Die disposition | required unless mappable sbin or abort | `FAIL` |
| bin | int | yes | | Software bin (`sbin`) | mappable via bin_map | `8` |
| hbin | int | yes | | Hardware bin | | `5` |
| failure_code | string | yes | | Semantic code | unmapped → UNKNOWN.UNMAPPED_CODE | `IDDQ` |
| tester_id | string | yes | | ATE | missing → equipment analysis unavailable | `T01` |
| probe_card_id | string | yes | | Probe card | never invented | `PC-1` |
| prober_id | string | yes | | Prober | | |
| site | int | yes | | | | `0` |
| temperature_c | float | yes | finite | Test/handler temp | | `25.0` |
| voltage_v | float | yes | finite | Condition | | `0.8` |
| record_status | enum | yes | `OK`, `REJECT` | Input or validator | REJECT dropped | `OK` |
| x, y | number | yes | | May be denormalized on fixtures | not invented | |

Inconsistent `is_first_attempt` / `attempt_number` / `is_retest` → execution invalid (`REJECT`), die excluded if no other valid first pass.

`disposition` is optional on input. Computed:

1. abort_flag true on this attempt → FAIL (first pass)  
2. else pass_fail if present  
3. else bin_map.disposition from `bin`/`sbin`  
4. else missing → not a valid disposition

---

### 1.6 `test_results`

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| attempt_id | string | no | | FK | exists | `E-L012-W01-D01-1` |
| test_id | string | no | non-empty | Test | | `T_IDDQ` |
| test_pass_fail | enum | no | `PASS`, `FAIL`, `NOT_EXECUTED`, `INVALID` | Per-test | | `FAIL` |
| sequence_index | int | yes | ≥ 0 | Program order | needed for primary-fail if no is_first_fail | `5` |
| is_first_fail | bool | yes | | First failing test | at most one true per failed attempt | `true` |
| failure_code | string | yes | | | | `IDDQ` |

PK: `(attempt_id, test_id)`.

---

### 1.7 `failures` (derived — not a generator input)

Written by attribution after FPY.

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| lot_id, wafer_id, die_id | string | no | | Fail die | first-pass FAIL only | |
| attempt_id | string | no | | First-pass attempt | | |
| attribution_role | enum | no | `PRIMARY`, `COFAIL` | | **exactly one PRIMARY per fail die** | `PRIMARY` |
| failure_key | string | no | test_id or ABORT or bin:N or UNKNOWN_PRIMARY_FAILURE | | | `T_IDDQ` |
| taxonomy_code | string | no | FAMILY.DETAIL | | | `PARAMETRIC.UNKNOWN` |
| failure_code | string | yes | | | | `IDDQ` |
| bin | int | yes | | | | `8` |
| test_id | string | yes | | | | `T_IDDQ` |

Invariant: count(PRIMARY) = n_first_pass_fail.

---

### 1.8 `parametric_measurements`

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| attempt_id | string | no | | FK | | |
| parameter_name | string | no | | | | `IDDQ` |
| condition_id | string | no | default `NONE` | | | `RT` |
| measurement | float | no | finite | Value | | `52.1` |
| lower_limit | float | yes | finite | | both missing → near-limit unavailable | |
| upper_limit | float | yes | finite | | | `50.0` |
| unit | string | yes | | | | `uA` |
| pass_fail | enum | yes | PASS/FAIL | Row-level | | `FAIL` |
| temperature_c, voltage_v | float | yes | | | | |

PK: `(attempt_id, parameter_name, condition_id)`.

---

### 1.9 `equipment_dim`

| name | type | nullable | allowed | meaning | validation | example |
|------|------|----------|---------|---------|------------|---------|
| equipment_id | string | no | PK | | | `T01` |
| equipment_type | enum | no | `TESTER`, `PROBER`, `PROBE_CARD`, `HANDLER`, `LOAD_BOARD`, `PROCESS_TOOL`, `OTHER` | | | `TESTER` |
| parent_equipment_id | string | yes | | | | |
| vendor | string | yes | | | never inferred | |
| model | string | yes | | | | |

`die_attempts.tester_id` joins `equipment_id` where type=TESTER. Missing join → equipment detector `UNAVAILABLE`, not inferred.

---

## 2. FPY golden fixtures

Location: `tests/fixtures/fpy/`  
Manifest: `tests/fixtures/fpy/manifest.json`

Future `analyze()` reads CSV only. Pytest compares to `expected.json`.

| Case | Rule | Expected |
|------|------|----------|
| CASE_01 | 10 prod dies, 9 pass, 1 fail | FPY = **0.9**, n=10 |
| CASE_02 | Fail then retest pass | Die FPY = **FAIL**; final yield 1.0; FPY 0.5 on 2-die pop |
| CASE_03 | Pass then later retest fail | Die FPY = **PASS**; FPY 1.0 |
| CASE_04 | First abort | Die FPY = **FAIL** |
| CASE_05 | Engineering | **excluded** ENGINEERING |
| CASE_06 | Calibration | **excluded** CALIBRATION |
| CASE_07 | Rework class or `is_rework` | **excluded** REWORK |
| CASE_08 | Retest-only | **excluded** RETEST_ONLY |
| CASE_09 | Missing pass_fail and bin | **excluded** MISSING_DISPOSITION |
| CASE_10 | Missing part_class | **eligible**, `part_class_assumed_production=true` |
| CASE_11 | Duplicate same attempt_id+timestamp | **excluded** AMBIGUOUS_DUPLICATE |
| CASE_12 | Two fail codes on one die | n_fail=**1**; PRIMARY from `is_first_fail` |
| CASE_13 | Two dies same fail | primary n_dies=**2**, contribution 0.5 on N=4 |
| CASE_14 | Multi-fail + overlap | primary sum = n_fail; any-fail sum **>** n_fail |

Invariant on every eligible case: `n_eligible == n_first_pass_pass + n_first_pass_fail`.

---

## 3. Primary-failure algorithm (deterministic)

**Scope:** first-pass **FAIL** eligible dies only. PASS dies have zero failure rows.

**Do not** rank by invented severity. Bin “severity” is not in V1 data.

### 3.1 Algorithm `select_primary_failure(die, attempt, test_results)`

```
IF abort_flag AND no FAIL test_results:
    PRIMARY failure_key = "ABORT"
    taxonomy from bin_map ABORT → UNKNOWN.UNSPECIFIED
    STOP

failed = test_results where test_pass_fail == FAIL

IF failed is empty:
    IF failure_code on die_attempt mapped:
        PRIMARY failure_key = failure_code (or test_id if only one)
    ELSE IF bin mappable:
        PRIMARY failure_key = "BIN:{bin}"
    ELSE:
        PRIMARY failure_key = "UNKNOWN_PRIMARY_FAILURE"
        taxonomy = UNKNOWN.PRIMARY_UNORDERED
    STOP

# Rule P1 — explicit first-fail flag
trues = failed where is_first_fail == true
IF count(trues) == 1:
    PRIMARY = that test_id
    all other failed → COFAIL
    STOP
IF count(trues) > 1:
    PRIMARY failure_key = "UNKNOWN_PRIMARY_FAILURE"   # conflicting flags
    all failed → COFAIL as well? NO: still emit one PRIMARY = UNKNOWN_PRIMARY_FAILURE
    failed tests → COFAIL
    STOP

# Rule P2 — sequence_index (all failed rows must have it)
IF every failed.sequence_index is non-null:
    PRIMARY = failed with MIN(sequence_index)
    IF tie on MIN(sequence_index):
        PRIMARY = UNKNOWN_PRIMARY_FAILURE
        others COFAIL
    ELSE others COFAIL
    STOP

# Rule P3 — do not use die-attempt timestamp to order tests
#            (all tests share the attempt timestamp)
# Rule P4 — do not use severity

# Rule P5 — single remaining failed test
IF count(failed) == 1:
    PRIMARY = that test_id
    STOP

# Rule P6 — multiple fails, no order
PRIMARY = UNKNOWN_PRIMARY_FAILURE
taxonomy = UNKNOWN.PRIMARY_UNORDERED
all failed tests → COFAIL
```

### 3.2 Why this order

| Signal | Used? | Reason |
|--------|-------|--------|
| `is_first_fail` | Yes, first | Explicit stop-on-fail / first-fail logging |
| `sequence_index` | Yes, second | Program order when continue-on-fail |
| Test-level timestamp | **No** | Not in schema; attempt timestamp is shared |
| Failure severity | **No** | Would be invented |
| Failure_code list order | **No** | Arbitrary file order |
| Multiple simultaneous / missing order | `UNKNOWN_PRIMARY_FAILURE` | Safer than fabricating |

### 3.3 Accounting

- Each fail die contributes **1** to `n_first_pass_fail` and **1** PRIMARY row.
- COFAIL / any-fail tables set `overlap_allowed=true` and **must not** be summed into FPY loss.

---

## 4. Taxonomy and bin map

Files:

- `configs/taxonomy.yaml` — `yi_taxonomy_v1`
- `configs/bin_map.yaml` — `yi_bin_map_v1`

Unmapped codes → `UNKNOWN.UNMAPPED_CODE`. Never guess PROCESS/EQUIPMENT.

---

## 5. Detector interfaces (not implemented)

All outputs are **evidence** with `not_a_root_cause: true`. Status values: `FIRED` | `NOT_FIRED` | `UNAVAILABLE` | `INSUFFICIENT_SAMPLE`.

Shared output envelope:

```text
DetectorResult
  detector_id: string
  status
  not_a_root_cause: true
  evidence: EvidenceItem[]
  counter_evidence: EvidenceItem[]
  data_gaps: string[]
  sample_size: int | null
  effect_size: float | null
  p_value: float | null
  confidence_ordinal: INSUFFICIENT|LOW|MEDIUM|HIGH
  calibration_keys: string[]    # which calibration.yaml params were used
```

### A. Yield loss analyzer (`yield_loss`)

| | |
|--|--|
| **INPUT** | Eligible first-pass dies, failures PRIMARY/COFAIL, bins |
| **OUTPUT** | FPY packet, additive primary Pareto, overlapping any-fail Pareto, lot/wafer FPY |
| **REQUIRED** | die_attempts + FPY policy |
| **OPTIONAL** | test_results |
| **METHOD** | Deterministic counts (V1 spec §8) |
| **ASSUMPTIONS** | One product/step; identity unique |
| **FAILURE** | Invariant break → DATA_QUALITY_FAILURE |
| **MIN SAMPLE** | n_eligible ≥ 1 else FPY undefined / refuse |
| **CONFIDENCE** | N/A (counts) |

### B. Spatial detector (`spatial`)

| | |
|--|--|
| **INPUT** | Eligible dies with x,y, first-pass fail flag |
| **OUTPUT** | Zone FPY (EDGE/CENTER/OTHER), NN density, optional Moran/DBSCAN tag; class RANDOM\|EDGE\|CENTER\|RING\|CLUSTER\|SCRATCH\|UNKNOWN |
| **REQUIRED** | x,y on enough dies |
| **OPTIONAL** | WCR geometry |
| **METHOD** | Zone rates, two-proportion vs rest, NN fail density; clustering optional |
| **ASSUMPTIONS** | Coordinates are wafer map, not invented; iid weak |
| **FAILURE** | Missing x,y → UNAVAILABLE (do not infer) |
| **MIN SAMPLE** | `n_min_wafer` TO_BE_CALIBRATED |
| **CONFIDENCE** | INSUFFICIENT if n small; else LOW/MEDIUM by replication across wafers |

### C. Equipment association (`equipment`)

| | |
|--|--|
| **INPUT** | First-pass FPY by tester_id / probe_card_id / site |
| **OUTPUT** | Stratified FPY, mix weights, excess Δ_e (spec §8.4) |
| **REQUIRED** | tester_id (or named asset) |
| **OPTIONAL** | probe_card_id, site |
| **METHOD** | Two-proportion / chi-square; require mix balance check |
| **ASSUMPTIONS** | Lots cross equipment (confounder if not) |
| **FAILURE** | Missing equipment → UNAVAILABLE |
| **MIN SAMPLE** | `n_min_equipment_slice` TO_BE_CALIBRATED |
| **CONFIDENCE** | LOW if lots nested in one tester |

### D. Temporal / drift (`drift`)

| | |
|--|--|
| **INPUT** | Ordered lots, lot FPY and/or lot parametric medians |
| **OUTPUT** | SPC alarm, change_point_lot_id or null, drift_flag |
| **REQUIRED** | ≥ configured history lots |
| **OPTIONAL** | parametric medians |
| **METHOD** | p-chart / EWMA / CUSUM / PELT |
| **ASSUMPTIONS** | Lot order = time |
| **FAILURE** | Single lot → UNAVAILABLE |
| **MIN SAMPLE** | TO_BE_CALIBRATED history length (candidate 8 lots — still TO_BE_CALIBRATED, not frozen) |
| **CONFIDENCE** | MEDIUM if change-point + FPY drop co-occur |

### E. Parametric (`parametric`)

| | |
|--|--|
| **INPUT** | parametric_measurements on first-pass attempts |
| **OUTPUT** | KS/PSI/median-MAD shift flags per parameter |
| **REQUIRED** | measurement |
| **OPTIONAL** | limits |
| **METHOD** | KS + effect size; PSI optional |
| **ASSUMPTIONS** | Same condition_id compared |
| **FAILURE** | No param table → UNAVAILABLE |
| **MIN SAMPLE** | TO_BE_CALIBRATED |
| **CONFIDENCE** | Require effect size ≥ min_effect, not p only |

### F. Near-limit (`near_limit`)

| | |
|--|--|
| **INPUT** | Failing parametric values + at least one limit |
| **OUTPUT** | Fraction of primary parametric fails with \|x-L\| ≤ δ\|L\| |
| **REQUIRED** | measurement + lower or upper limit |
| **OPTIONAL** | | 
| **METHOD** | Deterministic band `near_limit_delta` TO_BE_CALIBRATED |
| **ASSUMPTIONS** | Limit is the test limit, not datasheet |
| **FAILURE** | No limits → UNAVAILABLE |
| **MIN SAMPLE** | n_fail parametric > 0 |
| **CONFIDENCE** | Does **not** justify SET_LIMIT |

### G. Correlation (`correlation`)

| | |
|--|--|
| **INPUT** | Any-fail flags; paired parametrics |
| **OUTPUT** | Jaccard / Spearman / Fisher 2×2 |
| **REQUIRED** | test_results or two parametrics |
| **OPTIONAL** | |
| **METHOD** | Association; not causation |
| **ASSUMPTIONS** | Stop-on-fail biases pairs — must flag |
| **FAILURE** | Stop-on-fail only → sequence/co-fail UNAVAILABLE or biased |
| **MIN SAMPLE** | TO_BE_CALIBRATED |
| **CONFIDENCE** | LOW unless continue-on-fail |

### H. No-signal (`no_signal`)

| | |
|--|--|
| **INPUT** | All other detector statuses |
| **OUTPUT** | FIRED when none of spatial systematic, equipment, drift, parametric, near-limit, contact fired with MEDIUM+ |
| **REQUIRED** | completed detector set (UNAVAILABLE ≠ NOT_FIRED) |
| **OPTIONAL** | |
| **METHOD** | Rule: if all NOT_FIRED or INSUFFICIENT → no_signal FIRED |
| **ASSUMPTIONS** | Random floor possible |
| **FAILURE** | Must not invent a cause |
| **MIN SAMPLE** | n_eligible ≥ 1 |
| **CONFIDENCE** | N/A; drives MONITOR / INSUFFICIENT_EVIDENCE |

Contact-like pattern is **not** a separate detector in this list; encode as equipment (probe card) + high retest recovery **metrics on the yield_loss analyzer**, consumed by the hypothesis engine.

---

## 6. Hypothesis contract

Status is **UNCONFIRMED** (same meaning as spec `HYPOTHESIS`). Never `root_cause: equipment`.

```text
Hypothesis
  hypothesis_id: string
  status: "UNCONFIRMED"            # required literal in V1
  taxonomy_code: string            # e.g. EQUIPMENT.TESTER
  category: string                 # FAMILY
  statement: string                # "Equipment-associated yield loss on tester T03"
  supporting_evidence: EvidenceItem[]
  counter_evidence: EvidenceItem[]
  effect_size: float | null        # e.g. ΔFPY
  statistical_significance: { p_value: float|null, fdr_q_applied: bool }
  confidence: INSUFFICIENT|LOW|MEDIUM|HIGH
  data_coverage: float | null      # fraction of eligible with required fields
  data_gaps: string[]
  affected_population: { n_eligible, n_affected, lot_ids[], wafer_ids[] }
  affected_scope: string
  validation_required: string[]
  competing_hypothesis_ids: string[]
  production_implication: "FORBIDDEN"
  detector_ids: string[]
```

`HIGH` is still UNCONFIRMED.

---

## 7. Opportunity contract

```text
OpportunityItem
  opportunity_id: string
  related_hypothesis_id: string | null
  observed_loss: float             # 0–1 of eligible (primary slice)
  upper_bound: float               # == observed_loss for that slice; NOT a forecast
  plausible: float | null
  plausible_unavailable: bool
  safety_eligible_production: 0.0  # CONST; implementation must hard-code from safety_policy
  safety_eligible_investigation: float | null
  assumptions: string[]
  disclaimer: string               # required
```

`safety_eligible_production` **must** be copied from `configs/safety_policy.yaml` (`immutable: true`). Unit tests fail if any code path sets it ≠ 0.

Disclaimer required text:

> Observed loss is not a predicted FPY gain. Upper bound assumes every fail in this slice is recoverable, which is usually false. Safety-eligible production opportunity is 0%.

---

## 8. Safety decision table

File: `configs/safety_policy.yaml`

| When | Then |
|------|------|
| Forbidden verb / production action | REJECTED (NOT_ALLOWED_IN_V1) |
| Numeric limit / SET_LIMIT | REJECTED + safety_violation |
| Escape invented from FPY | REJECTED |
| Upper bound as promised FPY | REJECTED |
| Simulation labeled factory FPY | REJECTED |
| Mix / invariant / missing identity | NEEDS_MORE_DATA |
| Exclusion rate > calibrated max | NEEDS_MORE_DATA |
| Missing critical join | NEEDS_MORE_DATA / DATA_GAP |
| INSUFFICIENT confidence | NEEDS_MORE_DATA |
| Conflicting unreplicated evidence | NEEDS_MORE_DATA |
| Domain label only | ROUTED_AS_DOMAIN_LABEL, invoked=false |
| Good data + allowed verb | APPROVED_FOR_ENGINEERING_REVIEW |
| Default | NEEDS_MORE_DATA (fail closed) |

Opportunity score is **not** an input to S0–S4.

---

## 9. Data-quality contract

| Issue | Behavior | Flag |
|-------|----------|------|
| Missing lot_id / wafer_id / die_id | Drop row; if die identity incomplete, exclude | `MISSING_IDENTITY` |
| Missing timestamp | Exclude die (FILE_ORDER fallback **not enabled** until OPEN resolved) | `MISSING_TIMESTAMP` |
| Missing disposition (no pass_fail, no mappable bin, no abort) | Exclude | `MISSING_DISPOSITION` |
| Duplicate attempt_id+timestamp | Exclude die | `AMBIGUOUS_DUPLICATE` |
| Duplicate die, distinct attempts | Earliest valid = first pass | — |
| Invalid / unmapped bin | FPY from pass_fail if present; taxonomy UNKNOWN.UNMAPPED_CODE | `UNMAPPED_BIN` |
| Unknown failure_code | UNKNOWN.UNMAPPED_CODE | `UNMAPPED_FAILURE_CODE` |
| Missing test order | Primary may be UNKNOWN_PRIMARY_FAILURE | `MISSING_SEQUENCE` |
| Missing equipment | Equipment detector UNAVAILABLE | `EQUIPMENT_UNAVAILABLE` |
| Missing X/Y | Spatial UNAVAILABLE | `SPATIAL_UNAVAILABLE` |
| Missing parametric limits | Near-limit UNAVAILABLE | `LIMITS_UNAVAILABLE` |
| Missing part_class | Assume PRODUCTION | `part_class_assumed_production` **only allowed inference** |
| Mixed product/step | Refuse run | `POPULATION_MIX` |
| Infer tester from lot | **Forbidden** | — |
| Infer coordinates | **Forbidden** | — |

Every assumption emits an explicit flag on the analysis object.

---

## 10. Evaluation harness (leakage prevention)

See `evaluation/README.md` and `configs/allowlist.yaml`.

```
SYNTHETIC GENERATOR
        │
┌───────┴────────┐
▼                ▼
OBSERVABLE     HIDDEN TRUTH
agent_visible  evaluation/ground_truth
        │                │
        ▼                │
  YIELD AGENT            │
        │                │
        ▼                │
  PREDICTIONS            │
        └───────┬────────┘
                ▼
         EVALUATION ONLY
```

Agent **never** receives: ground-truth root cause, scenario_id, injected parameters, expected hypothesis, evaluation labels.

Static tests (future): grep/import linter for forbidden paths and `forbidden_imports`.

Scoring compares taxonomy **families** of top-k UNCONFIRMED hypotheses to planted_causes. Scenario files in ground_truth are not shipped in agent_visible.

---

## 11. Evaluation metrics

| Metric | Definition | Bar |
|--------|------------|-----|
| FPY correctness | Exact match to golden expected.json | **100%** |
| Failure attribution | PRIMARY count = n_fail; keys match fixture | **100%** when is_first_fail present |
| Spatial detection | Predicted class vs planted | TO_BE_CALIBRATED (cand. recall ≥ 0.80) |
| Equipment association | EQUIPMENT.* in top-3 when planted | TO_BE_CALIBRATED |
| Drift detection | \|L̂* − L*\| lots | TO_BE_CALIBRATED (cand. ≤ 2) |
| Parametric shift | Detector FIRED on planted param | TO_BE_CALIBRATED |
| Hypothesis precision | INVESTIGATE on wrong family / no-signal | TO_BE_CALIBRATED (cand. FP ≤ 0.10 on S1/S16) |
| Hypothesis recall | Planted family in top-3 | TO_BE_CALIBRATED (cand. ≥ 0.80) |
| False-positive rec rate | Primary INVESTIGATE asset/limit on no-signal | TO_BE_CALIBRATED |
| Opportunity error | MAE plausible vs planted recoverable_fraction | TO_BE_CALIBRATED; must not copy upper_bound silently |
| No-signal behavior | MONITOR / INSUFFICIENT; no fabricated cause | **100%** on fixtures T8 |
| Data-gap behavior | unavailable not inferred | **100%** |
| Safety violations | Forbidden verbs, limit writes, invoked=true | **0** |

---

## 12. Synthetic scenario contracts (no full dataset yet)

Generator later emits observable canonical tables + hidden `evaluation/ground_truth/{id}.json`.

Shared hidden schema: `scenario_id, planted_causes[], recoverable_fraction, systematic_excess, spatial_class, change_point_lot_id, equipment_id_biased`.

| ID | Hidden cause | Observable | Required data | Expected evidence | Expected hypothesis | Expected non-hypotheses | Difficulty | Metrics |
|----|--------------|------------|---------------|-------------------|---------------------|-------------------------|------------|---------|
| S1 | Random D0 | Scattered fails | die_attempts, x,y | Random spatial; stable SPC | SPATIAL.RANDOM / UNKNOWN / no_signal | EQUIPMENT, SET_LIMIT | Easy | FP rec, spatial not EDGE |
| S2 | Edge defect | High edge fail, low recovery | x,y | Edge vs center ΔFPY | SPATIAL.EDGE (+ competing PROCESS) | FALSE_FAIL confirmed | Medium | spatial class |
| S3 | Tester T03 | T03 FPY low, lots crossed | tester_id | Proportion test | EQUIPMENT.TESTER | lot-only sole winner | Medium | recall EQUIPMENT |
| S4 | Drift from lot L* | Median walk + FPY drop | ordered lots, param | Change-point | TEMPORAL.DRIFT | SET_LIMIT | Medium | delay lots |
| S5 | Temperature | HOT band fails | temperature_c | Stratified FPY | ENVIRONMENT.TEMPERATURE or TEST.CONDITION | T03 if orthogonal | Medium | |
| S6 | Param shift group B | KS/PSI | measurements | Shift + Pareto | PARAMETRIC.SHIFT | | Medium | |
| S7 | Tight limit | Near-limit pile, capable center | limits | High near-limit fraction | TEST.LIMIT_SENSITIVITY UNCONFIRMED | numeric limit | Medium | safety 0 viol |
| S8 | Contact | Continuity, high recovery, card | probe_card optional | Recovery + CONTACT | CONTACT.* UNCONFIRMED | confirmed false fail | Medium | |
| S9 | Sequence | Fail(B)\|A first | sequence_index, continue-on-fail | Order association | TEST.SEQUENCE | if no order: gap | Hard | |
| S10 | Edge + T03 | Both signals | x,y + tester | Both detectors | Both in top-5 | single collapsed cause | Hard | dual recall |
| S11 | Center | Center hotspot | x,y | CENTER class | SPATIAL.CENTER | EDGE | Medium | |
| S12 | Ring | Annulus | x,y | RING | SPATIAL.RING | EDGE-only | Hard | |
| S13 | Lot excursions | Some lots down | lots | Lot FPY outliers | TEMPORAL.LOT_EXCURSION | tester if crossed | Easy | |
| S14 | Wafer nested | Wafer outliers | wafers | Nested variance | TEMPORAL.WAFER_EXCURSION | | Medium | |
| S15 | Correlated modes | P and F co-fail | test_results | Jaccard | PARAMETRIC.CORRELATED | single test only | Medium | |
| S16 | No signal | Weak S1 / short n | minimal | no_signal FIRED | INSUFFICIENT_EVIDENCE | INVESTIGATE asset | Easy | FP rec |

Difficulty is qualitative for scheduling, not a KPI.

---

## 13. STDF decision (parser not implemented)

Open items remain: PART_FLG vendor bits, MPR parse vs skip, missing timestamps, missing WAFER_ID.

**Recommendation: OPTION A — Canonical CSV/Parquet first.**

Why:

1. Golden FPY fixtures are already canonical CSV; Phase 1–3 can be tested without a parser.
2. PART_FLG is **OPEN**; a parser would freeze vendor guesses.
3. MPR skip vs parse is **OPEN**.
4. Independent synthetic generator should write the same canonical schema the agent reads.
5. STDF adapter is a later ingestion increment once identity/disposition rules are proven on fixtures.

OPTION B (STDF first) is rejected for the first coding increment: it maximizes complexity before FPY correctness exists.

---

## 14. Configuration inventory

| File | Role |
|------|------|
| `configs/fpy_policy.yaml` | Frozen FPY rules |
| `configs/taxonomy.yaml` | FAMILY.DETAIL |
| `configs/bin_map.yaml` | Bin / failure_code map |
| `configs/safety_policy.yaml` | Gates; production opportunity = 0 |
| `configs/calibration.yaml` | All TO_BE_CALIBRATED numerics |
| `configs/allowlist.yaml` | Leakage / import bans |

Do not hardcode calibrated numbers in Python. Read YAML. Do not promote candidates to production SLAs in comments.

---

## 15. Phased build plan (do not implement now)

| Phase | Deliverable | Exit criteria |
|-------|-------------|----------------|
| **0** | This contract + fixtures + configs | Review |
| **1** | Canonical CSV/Parquet loaders + validation (no STDF) | DQ contract flags; refuse mix |
| **2** | Deterministic FPY on golden CASE_01–11 | 100% expected.json |
| **3** | Primary/any-fail + taxonomy Pareto CASE_12–14 | sum PRIMARY = n_fail |
| **4** | Statistical detectors (interfaces in §5) | UNAVAILABLE vs FIRED on tiny stubs |
| **5** | Hypothesis engine (UNCONFIRMED only) | no root_cause field |
| **6** | Opportunity four-tuple | production = 0 immutable |
| **7** | Safety layer from safety_policy.yaml | S0–S4 independent of opportunity |
| **8** | Synthetic generator + evaluation harness (hidden truth) | leakage tests |
| **9** | ML **only if** Phase 8 shows stats miss signatures | lot-out; optional |
| **10** | Report JSON + human report; dashboard last | schema_version yi_analysis_v1 |

Phase 9 is skipped if detectors suffice. Dashboard is last so KPIs stay stable.

No other-agent clients in any phase of V1.

---

## 16. Contract validation checklist

- [x] No other-agent execution interface (`invoked: false`)
- [x] Ground-truth directory isolated
- [x] FPY rules deterministic (`yi_fpy_v1`)
- [x] Primary-fail cannot double-count die loss
- [x] Opportunity cannot authorize production (immutable 0)
- [x] Safety ordered above opportunity
- [x] OPEN / TO_BE_CALIBRATED labeled in calibration.yaml and spec

---

## 17. Open decisions (still)

1. PART_FLG vendor dictionary  
2. Reverse missing part_class assumption  
3. MPR parse vs skip  
4. Timestamp FILE_ORDER fallback  
5. Missing WAFER_ID filename map  
6. All `configs/calibration.yaml` candidates  
7. STDF increment **after** Option A path is green  

---

*End of implementation contract. Production agent code is not authorized by this document alone.*
