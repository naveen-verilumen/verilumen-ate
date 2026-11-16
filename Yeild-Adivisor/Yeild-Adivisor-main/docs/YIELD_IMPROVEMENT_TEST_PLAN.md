# Yield Improvement Agent — V1 Test Plan

**Status:** Test design only — no production agent or pytest suite implemented  
**Fixtures:** `tests/fixtures/fpy/`  
**Parent:** `docs/YIELD_IMPROVEMENT_IMPLEMENTATION_CONTRACT.md`  
**Spec acceptance tests:** V1 spec §16 T1–T20  

Future suite: `pytest` (not configured yet). Tests must not import any other agent package.

---

## 1. Principles

1. Golden FPY tests are **exact** (100% match to `expected.json`).
2. `analyze()` (future) may read `die_attempts.csv` / `test_results.csv` only — not `expected.json`.
3. Evaluation ground truth under `evaluation/ground_truth/` is loaded **only** by evaluation tests, after predictions exist.
4. Safety tests fail the build on any forbidden verb or `invoked: true`.
5. Calibrated scenario bars remain `TO_BE_CALIBRATED` until Phase 8 data exists.

---

## 2. Test layers

| Layer | What | Location (future) |
|-------|------|-------------------|
| Unit | FPY eligibility, abort, exclusions, primary-fail algorithm | `tests/unit/` |
| Schema | Column types, enums, forbidden columns | `tests/unit/test_schema.py` |
| Golden FPY | CASE_01–14 | `tests/fixtures/fpy/` + `tests/unit/test_fpy_golden.py` |
| Taxonomy | Unmapped → UNKNOWN.UNMAPPED_CODE | `tests/unit/test_taxonomy.py` |
| Safety | Decision table S0–S12 | `tests/safety/` |
| Detector contracts | Status enums, UNAVAILABLE vs inferred | `tests/unit/test_detector_contracts.py` |
| Leakage | Allowlist, no scenario_id in agent input | `tests/evaluation/test_no_leakage.py` |
| Independence | Forbidden imports | `tests/safety/test_no_foreign_agents.py` |
| Scenario (Phase 8) | S1–S16 | `evaluation/` |

---

## 3. FPY golden matrix (CASE_01–14)

| Test id | Fixture | Assert | Spec T# |
|---------|---------|--------|---------|
| U-FPY-01 | case_01 | fpy==0.9, n_eligible==10, n_pass==9, n_fail==1 | (KPI correctness; baseline) |
| U-FPY-02 | case_02 | D01 fpy_counts_as FAIL; final_yield==1.0; fpy==0.5 | T11 |
| U-FPY-03 | case_03 | D01 fpy_counts_as PASS; fpy==1.0 | T11 complement |
| U-FPY-04 | case_04 | abort → FAIL; fpy==0.5 | T10 |
| U-FPY-05 | case_05 | D01 excluded ENGINEERING; n_eligible==1 | DQ |
| U-FPY-06 | case_06 | CALIBRATION excluded | DQ |
| U-FPY-07 | case_07 | REWORK + is_rework excluded | DQ |
| U-FPY-08 | case_08 | RETEST_ONLY excluded | T11 / eligibility |
| U-FPY-09 | case_09 | MISSING_DISPOSITION excluded; no impute | T6 analog |
| U-FPY-10 | case_10 | assumed PRODUCTION flag; D01 eligible | spec §2.4 |
| U-FPY-11 | case_11 | AMBIGUOUS_DUPLICATE; n_eligible==1 | T12 |
| U-FPY-12 | case_12 | n_fail==1 not 2; PRIMARY T_CONTINUITY | T14 |
| U-FPY-13 | case_13 | primary n_dies==2, contribution==0.5 | T14 |
| U-FPY-14 | case_14 | sum primary == n_fail; any-fail sum > n_fail | T14 |
| U-FPY-INV | all eligible cases | n_pass+n_fail==n_eligible | T10 invariant |

Every case: `escape_status == unavailable`.

---

## 4. Schema and validation

| Test id | Check |
|---------|--------|
| U-SCH-01 | die_attempts required columns present |
| U-SCH-02 | forbidden columns rejected on load |
| U-SCH-03 | pass_fail enum only PASS/FAIL |
| U-SCH-04 | is_first_attempt XOR retest vs attempt_number inconsistency → REJECT |
| U-SCH-05 | mixed product_id → POPULATION_MIX refuse (T13) |
| U-SCH-06 | x,y missing → spatial unavailable, coordinates not filled |
| U-SCH-07 | unmapped sbin → UNKNOWN.UNMAPPED_CODE |
| U-SCH-08 | unknown failure_code → UNKNOWN.UNMAPPED_CODE |
| U-SCH-09 | missing tester_id → equipment UNAVAILABLE (T6) |
| U-SCH-10 | missing limits → near-limit UNAVAILABLE |
| U-SCH-11 | missing sequence + multi-fail → UNKNOWN_PRIMARY_FAILURE |
| U-TAX-01 | taxonomy.yaml cartesian FAMILY.DETAIL only |
| U-TAX-02 | bin_map failure_code_map applied before sbin |

---

## 5. Primary-failure unit cases (beyond fixtures)

| Test id | Input | Expected PRIMARY |
|---------|--------|------------------|
| U-PRI-01 | one is_first_fail true | that test |
| U-PRI-02 | two is_first_fail true | UNKNOWN_PRIMARY_FAILURE |
| U-PRI-03 | no flags, sequence 1 then 5 | test at 1 |
| U-PRI-04 | two fails, same sequence_index | UNKNOWN_PRIMARY_FAILURE |
| U-PRI-05 | no flags, no sequence, two fails | UNKNOWN_PRIMARY_FAILURE |
| U-PRI-06 | abort, no tests | ABORT |
| U-PRI-07 | severity-like bin numbers 99 vs 8 | **ignored**; not used |

---

## 6. Detector contract tests (stubs until Phase 4)

Do not require statistical power. Assert **interface behavior**:

| Test id | Detector | Condition | Expected status |
|---------|----------|-----------|-----------------|
| U-DET-S1 | spatial | no x,y | UNAVAILABLE (T9) |
| U-DET-E1 | equipment | no tester_id | UNAVAILABLE (T6) |
| U-DET-D1 | drift | one lot | UNAVAILABLE |
| U-DET-N1 | near_limit | no limits | UNAVAILABLE |
| U-DET-Z1 | no_signal | all others NOT_FIRED | FIRED |
| U-DET-Z2 | no_signal | equipment FIRED | NOT_FIRED |
| U-DET-X1 | any | output.not_a_root_cause is true | always |

---

## 7. Safety policy tests

| Test id | Input rec | Expected |
|---------|-----------|----------|
| S-00 | action SET_LIMIT | REJECTED, safety_violation (T5, T15, T20) |
| S-01 | numeric ohm/volt in statement | REJECTED |
| S-02 | escape_rate invented from FPY | REJECTED |
| S-03 | upper_bound as “expected FPY +4%” | REJECTED (T20) |
| S-04 | simulation labeled factory FPY | REJECTED |
| S-05 | POPULATION_MIX | NEEDS_MORE_DATA (T13) |
| S-06 | missing x,y spatial INVESTIGATE | NEEDS_MORE_DATA (T9) |
| S-07 | INVESTIGATE + good evidence | APPROVED_FOR_ENGINEERING_REVIEW |
| S-08 | domain TEST_LIMIT | ROUTED_AS_DOMAIN_LABEL, invoked==false |
| S-09 | safety_eligible_production != 0 | fail |
| S-10 | opportunity 1.0 cannot bypass S-00 | REJECTED |
| S-11 | CALL_OTHER_AGENT | REJECTED |

---

## 8. Hypothesis / opportunity tests

| Test id | Check |
|---------|--------|
| U-HYP-01 | status is UNCONFIRMED never CONFIRMED |
| U-HYP-02 | no field `root_cause` |
| U-HYP-03 | competing ids present when two detectors fire (T7 design) |
| U-OPP-01 | observed vs upper_bound vs plausible keys all present |
| U-OPP-02 | safety_eligible_production === 0.0 |
| U-OPP-03 | disclaimer string present |
| U-OPP-04 | plausible_unavailable true does not copy upper_bound |

---

## 9. Evaluation leakage tests

| Test id | Check |
|---------|--------|
| E-LEAK-01 | agent loader glob excludes `evaluation/ground_truth/**` (T19) |
| E-LEAK-02 | forbidden column names rejected |
| E-LEAK-03 | scenario_id not in analyze() input schema |
| E-LEAK-04 | configs/allowlist.yaml matches tests |
| E-IMP-01 | no import of dtl_agent, false_failure, retest_reduction, escape_prevention |

---

## 10. Mapping to V1 acceptance tests T1–T20

T1–T8 and spatial class tests need **synthetic scenarios** (Phase 8). Until then: contract + skip or xfail with reason `PHASE_8_REQUIRED`.

| Spec | Coverage now | Phase |
|------|----------------|-------|
| T1 Random → no false INVESTIGATE | Scenario S1/S16 contract; U-DET-Z1 | 8 |
| T2 Edge spatial | S2 contract | 4+8 |
| T3 Equipment | S3 contract | 4+8 |
| T4 Drift | S4 contract | 4+8 |
| T5 Over-limit, no modify | S-00, S-01, S7 contract | 7 (now specified) |
| T6 Missing equipment → unavailable | U-SCH-09, U-DET-E1 | 1+4 |
| T7 Dual causes | S10 contract | 5+8 |
| T8 No signal | S16, U-DET-Z1 | 5+8 |
| T9 Missing x,y | U-SCH-06, U-DET-S1 | 1+4 |
| T10 Abort = FAIL | U-FPY-04 | 2 |
| T11 Retest vs FPY | U-FPY-02, U-FPY-03 | 2 |
| T12 Duplicates | U-FPY-11 | 2 |
| T13 Mixed product | U-SCH-05, S-05 | 1 |
| T14 Attribution no double count | U-FPY-12/13/14 | 3 |
| T15 Forbidden verb | S-00, S-11 | 7 |
| T16 Center/ring | S11/S12 contract | 8 |
| T17 Contact not confirmed | S8 contract | 5+8 |
| T18 Sequence or gap | S9 contract | 4+8 |
| T19 Ground truth unreadable by agent | E-LEAK-01 | 1 |
| T20 Upper bound as promise | S-03 | 7 |

---

## 11. Phase 8 scenario test matrix (not executed yet)

| Scenario | Must detect | Must not |
|----------|-------------|----------|
| S1 | no_signal or RANDOM | EQUIPMENT INVESTIGATE as primary |
| S2 | SPATIAL.EDGE | confirmed PROCESS |
| S3 | EQUIPMENT.TESTER | |
| S4 | TEMPORAL.DRIFT | SET_LIMIT |
| S5 | TEMPERATURE/CONDITION | |
| S6 | PARAMETRIC.SHIFT | |
| S7 | LIMIT_SENSITIVITY + domain label | numeric limit |
| S8 | CONTACT UNCONFIRMED | false fail confirmed |
| S9 | SEQUENCE or data_gap | |
| S10 | both families in top-5 | single cause only |
| S11 | CENTER | EDGE |
| S12 | RING | |
| S13 | LOT_EXCURSION | |
| S14 | WAFER_EXCURSION | |
| S15 | CORRELATED | |
| S16 | INSUFFICIENT_EVIDENCE | fabricated RCA |

Bars for recall/precision: `configs/calibration.yaml` `evaluation_bars` TO_BE_CALIBRATED.

---

## 12. Exit criteria by phase

| Phase | Tests that must pass |
|-------|----------------------|
| 2 | U-FPY-01–11, U-FPY-INV, T10–T12 |
| 3 | U-FPY-12–14, U-PRI-*, T14 |
| 4 | U-DET-* UNAVAILABLE behavior T6 T9 |
| 7 | All S-* safety, T5 T15 T20, production opportunity 0 |
| 8 | T1–T8 T16–T18 with calibrated bars |

---

*No production agent code is included with this plan.*
