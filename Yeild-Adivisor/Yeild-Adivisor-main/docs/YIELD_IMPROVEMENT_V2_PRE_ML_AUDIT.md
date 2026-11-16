# V2 Pre-ML Audit

This audit answers one question: must Yield Improvement V2 be cleaned up before `yi_ml_v2` is trained?

Nothing in the repository was changed to produce this document. No dataset, config, model, dashboard, or API file was edited. Counts below were recomputed from `data/synthetic/agent_visible/yi_synthetic_v2/` and from the current FPY, Pareto, and ML code.

## Executive Summary

**Proceed to `yi_ml_v2`.** Cleanup is not a prerequisite for a correct ML dataset.

The ML matrix is already one row per physical die. The physical key is `(lot_id, wafer_id, die_id)`. There are 2,500 such dies, 251 first-pass failures, and the target is `first_pass_fail`. Leave-one-lot-out does not use `die_id`. Test names, failure-code taxonomy, and the dashboard overlay are not model inputs.

A real bug does exist: primary-failure fields copied onto each die are keyed by `die_id` alone, so 137 of 251 per-die primary labels are wrong. The Pareto chart does not use those fields. Its 251 total and its test-id bars are intact. Fix that copy before any screen that shows a per-die primary failure. Do not block training on it.

Do not invent further T001–T010 meanings before training. The generator already binds each test id to one failure code. The existing display catalog in `configs/v2_test_catalog.yaml` contradicts those codes. Treat it as a label overlay, not as evidence.

Do not join the eight V2 parametric measurements into the first `yi_ml_v2`. Keep `yi_ml_v1` unchanged. It was not trained on this dataset.

## Current V2 Dataset

| Item | Value |
| --- | --- |
| Name | Yield Improvement V2 |
| Id | `yi_synthetic_v2` |
| Path | `data/synthetic/agent_visible/yi_synthetic_v2/` |
| Lots | 5 (`L001`–`L005`) |
| Wafers | 25 (`W01`–`W05` on every lot) |
| Dies | 2,500 |
| Attempts | 2,560 |
| First attempts | 2,500 |
| Retest attempt rows | 60 |
| Aborts | 0 |
| Test rows | 25,600 (10 tests on every attempt) |
| Parametric rows | 20,480 (8 parameters on every attempt) |
| First-pass pass | 2,249 |
| First-pass fail | 251 |
| FPY | 2,249 / 2,500 = 0.8996 (89.96%) |
| FPY loss | 251 / 2,500 = 0.1004 (10.04%) |
| ML rows if built on this folder | 2,500 |
| Active model | `yi_ml_v1`, not trained on this dataset |

Die identity that is unique: `(lot_id, wafer_id, die_id)`.

`die_id` alone is not unique. `D001`–`D100` each appear 25 times. `wafer_id + die_id` is not unique either. `W01/D001` exists on all five lots.

`attempt_id` is globally unique. Its format is `E-{lot}-{wafer}-{die}-{n}`.

## 1. die_id Identity Audit

### How the code identifies a die

| Stage | Key actually used | Affected by repeating `die_id`? |
| --- | --- | --- |
| FPY grouping | `DieAttempt.die_key()` = `(lot_id, wafer_id, die_id)` in `yield_analysis/fpy.py` | No. Eligible count stays 2,500 |
| First-pass selection | That same tuple | No |
| Pareto counts | One count per failing first-pass attempt, keyed by test id | No. Sum is 251 |
| Primary copy onto the die record | `{p.die_id: p for p in attribution.primary_failures}` | **Yes.** Later dies with the same `die_id` overwrite earlier ones |
| Detectors | `d.failed` and `attempt_id`. `primary_failure_*` is copied onto `DieView` and then not read | Scoring: no. Stored fields: yes, they are the bad copy |
| Opportunity | `lot_id/wafer_id/die_id` in `opportunity/populations.py` | No |
| ML rows | One `fpy.per_die` outcome, joined by `attempt_id` | No |
| ML features | `die_id` is not a feature. Split column is `lot_id` | No |
| Dashboard Pareto | `loss_summary.primary_failure`, which is the test-id Pareto | No |
| API lot list | `lot_id` only | No |

The correct unique identity is **`lot_id + wafer_id + die_id`**. It is not `wafer_id + die_id`, and it is not `die_id`.

### The 137-die disagreement

`calculate_fpy` builds the correct primary on each failing attempt, then copies it onto `DieOutcome` with a dictionary keyed only by `die_id`:

```text
primary_by_die = {p.die_id: p for p in attribution.primary_failures}
```

Among 251 first-pass failing dies, 92 distinct `die_id` values appear, and 69 of those ids are shared by more than one failing die (maximum 10). After the overwrite, **137 of 251** `DieOutcome.primary_failure_*` values disagree with that die’s own primary.

Checked example: `L001 / W01 / D049`.

| Source | Primary |
| --- | --- |
| Attempt 1 tests | `T001` FAIL, `is_first_fail = true`, code `CONTINUITY` |
| Attribution row for this lot, wafer, and die | `T001` / `CONTINUITY` / `CONTACT.CONTINUITY` |
| Field copied onto `DieOutcome` | `T004` / `CONTACT` / `UNKNOWN.UNMAPPED_CODE` |

The copied field belongs to some other failing die that is also named `D049`.

### Answers

| Question | Answer |
| --- | --- |
| A. Real analytical bug? | Yes, for any consumer of `DieOutcome.primary_failure_*` |
| B. Current dashboard Pareto? | No. The chart uses the additive Pareto, not the collided field |
| C. The 251 total? | No |
| D. Pareto categories? | No. Bars are test ids counted per failing attempt |
| E. Statistical detectors? | No for the rates they compute. They score first-pass fail vs pass |
| F. ML data? | No. Join key is `attempt_id`. Sample key is the full die tuple |
| G. Leakage or bad grouping? | No. Lots do not share dies. `die_id` is not a model input |
| H. Fix before `yi_ml_v2`? | No |

**Conclusion: NOT REQUIRED BEFORE ML. REQUIRED ONLY FOR ANALYTICS/UI** that displays the per-die primary. The Pareto and the ML table do not need this fix.

## 2. Test Catalog Audit

Ten tests exist: `T001`–`T010`. Every attempt has all ten rows. There is no test-name column in `test_results.csv`.

The behavioral catalog is `configs/synthetic_v2.yaml`. Each test has one `sequence_index` and one `failure_code`. FAIL rows in the CSV match that table:

| Test id | Sequence | Failure code when the test fails | Name stored in the CSV |
| --- | --- | --- | --- |
| T001 | 1 | CONTINUITY | NOT PRESENT |
| T002 | 2 | OPENS | NOT PRESENT |
| T003 | 3 | SHORTS | NOT PRESENT |
| T004 | 4 | CONTACT | NOT PRESENT |
| T005 | 5 | IDDQ | NOT PRESENT |
| T006 | 6 | VMIN | NOT PRESENT |
| T007 | 7 | VMAX | NOT PRESENT |
| T008 | 8 | LEAKAGE | NOT PRESENT |
| T009 | 9 | FUNCTIONAL | NOT PRESENT |
| T010 | 10 | SCAN | NOT PRESENT |

What the generator actually does:

- A failed die receives one or more of these test ids. The earliest sequence is `is_first_fail`.
- Later tests are `NOT_EXECUTED` unless they are also in the fail set. 59 attempts have a second FAIL after the first.
- Parametric rows are not tied to a `test_id`. All eight measurements hang off `attempt_id`.
- `sequence_index` is the order. Detectors that look at tests (`sequence`, `correlation`) use `test_id` and `sequence_index`, not a semantic type.
- The dashboard already prints a label. `frontend/src/services/formatTestLabel.ts` turns a test id into `T00x — <name>` using `configs/v2_test_catalog.yaml`.

That overlay is display metadata. It says it must not change generator codes. Its assigned names do not match the generator:

| Test id | Overlay label already on the dashboard path | Generator failure code | Supported by the data? |
| --- | --- | --- | --- |
| T001 | Continuity / Open-Short Test | CONTINUITY | Continuity only. Opens are T002. Shorts are T003 |
| T002 | DC Parametric Test | OPENS | Semantic meaning is not supported by the current dataset |
| T003 | Leakage Test | SHORTS | Semantic meaning is not supported. Leakage is the T008 code |
| T004 | Functional Test | CONTACT | Semantic meaning is not supported. Functional is the T009 code |
| T005 | Timing / AC Test | IDDQ | Semantic meaning is not supported. The overlay cites `SETUP_SLACK_PS` and `HOLD_SLACK_PS`, which are not in the V2 parametric file |
| T006 | Power / Thermal Test | VMIN | Semantic meaning is not supported |
| T007 | Unclassified V2 Test | VMAX | The unclassified label is honest. A physical type is not supported beyond the code `VMAX` |
| T008 | Unclassified V2 Test | LEAKAGE | Same |
| T009 | Unclassified V2 Test | FUNCTIONAL | Same |
| T010 | Unclassified V2 Test | SCAN | Same |

So “T001 — Continuity / Open-Short Test” is not a correction the data can carry. The only meaning the files support is: **T001 is the continuity fail slot in this synthetic program.**

| Use of a new semantic name | Needed? |
| --- | --- |
| A. Analytical correctness | No. FPY and Pareto already use test id and failure code |
| B. Interpretability | Only if the label repeats the generator code. A new physical type would mislead |
| C. Dashboard usability | Labels already exist. Several of them disagree with the codes |
| D. Dangerous | Yes, if the overlay is treated as the test’s physical meaning |
| E. Not needed before ML | Yes |

**Conclusion: UI ONLY. Not required before ML. Do not add more semantic types as part of training.** If labels are corrected later, align them to the generator failure code, or keep T007–T010 unclassified and stop extending T001–T006.

**Display overlay correction:** `configs/v2_test_catalog.yaml` now copies each generator `failure_code` as the program-slot display name (`T007 — VMAX`, not `Unclassified V2 Test`). Stored failure codes, Pareto keys, and CSV bytes are unchanged. The table above remains the historical mismatch that was corrected.

## 3. Test ↔ Failure-Code Audit

The supported test-to-code relationship is the generator table above. It is one code per test id. It is not a guess. `CONTACT → T001` is false. `CONTACT` is T004.

`UNKNOWN.UNMAPPED_CODE` is produced by `yield_analysis/taxonomy.py`: if `failure_code` is absent from `configs/bin_map.yaml` `failure_code_map`, the code stays unmapped. The mapper does not infer a family from the word.

| Failure code | Current mapping | Why | Test association in the data | Safe to map now? |
| --- | --- | --- | --- | --- |
| CONTACT | `UNKNOWN.UNMAPPED_CODE` | Not in `failure_code_map` | T004 only | No automatic map. `CONTACT.PROBE` and `CONTACT.UNKNOWN` exist in the taxonomy, but the files do not say which detail applies. Choosing one is a new policy |
| OPENS | `UNKNOWN.UNMAPPED_CODE` | Not in the map | T002 only | No. No OPENS detail exists. Mapping it to `CONTACT.CONTINUITY` would merge it with T001 |
| SHORTS | `UNKNOWN.UNMAPPED_CODE` | Not in the map | T003 only | No. Same reason |
| VMAX | `UNKNOWN.UNMAPPED_CODE` | Not in the map | T007 only | The least invented later choice is `PARAMETRIC.UNKNOWN`, because `VMIN` is already mapped that way and both share software bin 13. That is still a bin-map edit, not a fact already stored |
| LEAKAGE | `UNKNOWN.UNMAPPED_CODE` | Not in the map | T008 only | The parallel of `IDDQ` is `PARAMETRIC.UNKNOWN` (both use software bin 8 in the generator). Again a policy edit, not required for ML |

Mapped today, for comparison: `CONTINUITY` → `CONTACT.CONTINUITY`, `IDDQ` → `PARAMETRIC.UNKNOWN`, `VMIN` → `PARAMETRIC.UNKNOWN`, `FUNCTIONAL` → `FUNCTIONAL.UNKNOWN`, `SCAN` → `FUNCTIONAL.SCAN`.

What the unmapped string does **not** change:

| Consumer | Uses the taxonomy string? |
| --- | --- |
| FPY | No. Uses `pass_fail` on the first attempt |
| Primary test id | No. Uses `is_first_fail` |
| Pareto bar identity | No. The bar key is `test_id` |
| Pareto taxonomy column | Yes. The label becomes `UNKNOWN.UNMAPPED_CODE` |
| Detector rates | No |
| Hypotheses | Built from detector families in `hypotheses/identity.py`, not from this map |
| Opportunity | Uses the full die key and fail flag |
| ML target | No |
| ML features | No. `failure_code` is denied |

**Conclusion: NOT REQUIRED BEFORE ML. ANALYTICS ONLY** if someone will act on the taxonomy text. The test-id relationship is already defined by the generator and does not need a new mapping to train.

## 4. UNKNOWN.UNMAPPED_CODE Audit

Scope: first-pass dies whose **primary** taxonomy is `UNKNOWN.UNMAPPED_CODE`. That is the set that can change a Pareto taxonomy label. Test rows that fail with these codes but are not the primary are extra and are not in this count.

| Measure | Value |
| --- | --- |
| Primary failures with this taxonomy | 136 |
| Unique physical dies `(lot, wafer, die)` | 136 |
| Unique `die_id` values among them | 67 (the id repeats; the physical die does not) |
| First-pass failing dies | 251 |
| Share of first-pass failures | 136 / 251 = 54.2% |
| Eligible dies | 2,500 |
| Share of eligible | 136 / 2,500 = 5.44% |
| Lots | All five: L001 12, L002 46, L003 36, L004 27, L005 15 |
| Wafers | 24 of 25 lot-wafer pairs |

Tests involved, and their Pareto contribution:

| Test | Code | Primary dies | Share of the 251 fails |
| --- | --- | --- | --- |
| T004 | CONTACT | 92 | 36.7% |
| T002 | OPENS | 13 | 5.2% |
| T007 | VMAX | 12 | 4.8% |
| T003 | SHORTS | 10 | 4.0% |
| T008 | LEAKAGE | 9 | 3.6% |
| Total | | 136 | 54.2% |

The other 115 primaries already have a taxonomy: T006 VMIN 39, T005 IDDQ 38, T001 CONTINUITY 17, T009 FUNCTIONAL 12, T010 SCAN 9.

This is a **label** on the taxonomy field. It does not move a die into or out of the fail set, and it does not move a die from one test-id bar to another. Analytical conclusions that are “T004 is the largest first-fail test” stay true. Conclusions that are “this loss is `CONTACT.PROBE`” are not supported, because the mapper refused to say that.

**Conclusion: NOT REQUIRED before ML. ANALYTICS ONLY for taxonomy text. Not display-only in the sense that the taxonomy column is wrong for 136 dies, but the yield numbers and the test-id Pareto do not depend on repairing it.**

## 5. FPY Verification

Recomputed with `calculate_fpy` on the current V2 attempts and test results:

| Quantity | Value |
| --- | --- |
| Eligible dies | 2,500 |
| First-pass PASS | 2,249 |
| First-pass FAIL | 251 |
| Excluded | 0 |
| FPY | 2,249 / 2,500 = 0.8996 = 89.96% |
| FPY loss | 251 / 2,500 = 0.1004 = 10.04% |
| Invariant | 2,500 = 2,249 + 251 |

Formula, from `configs/fpy_policy.yaml` and `yield_analysis/fpy.py`:

```text
FPY      = n_first_pass_pass / n_fpy_eligible
FPY loss = n_first_pass_fail / n_fpy_eligible
```

The first attempt is `attempt_number == 1`. Disposition is `pass_fail`. Retests do not replace it. Aborts would count as fail; there are none.

| Proposed change | Can it change 251 or 89.96%? |
| --- | --- |
| Fix `die_id` primary copy | No. Eligibility is already the full die key |
| Rename T001–T010 | No. Names are not read by FPY |
| Map unmapped failure codes | No. FPY returns before taxonomy is used for the count. Taxonomy is attached after the pass/fail tally |

**The 251 does not depend on these cleanups.**

## 6. Pareto Verification

Chart: “Where is yield lost?” in `frontend/src/components/ParetoChart.tsx`. It plots `primary_failure` from the report. The axis label is the catalog display name when one exists. The count still comes from the analysis row.

Grain: one primary per first-pass failing die. Selection is `is_first_fail = true` on tests with `test_pass_fail = FAIL`. That path does not use `die_id` as the aggregation key. `failure_code` on the bar is the code of that earliest failed test. `UNKNOWN.UNMAPPED_CODE` is stored beside the bar; it does not decide which bar the die joins.

Primary counts from this run:

| Test id | Dies | Running total |
| --- | --- | --- |
| T004 | 92 | 92 |
| T006 | 39 | 131 |
| T005 | 38 | 169 |
| T001 | 17 | 186 |
| T002 | 13 | 199 |
| T007 | 12 | 211 |
| T009 | 12 | 223 |
| T003 | 10 | 233 |
| T008 | 9 | 242 |
| T010 | 9 | 251 |

**Pareto total: 251. PASS for the total and for the test-id distribution.**

Category reliability:

| Layer | Reliable? |
| --- | --- |
| Which test id failed first, and how many dies | Yes |
| Taxonomy family on CONTACT, OPENS, SHORTS, VMAX, LEAKAGE | No. They are `UNKNOWN.UNMAPPED_CODE` |
| Dashboard words such as “Functional Test” on T004 | No. Those words come from the overlay, not from the fail code `CONTACT` |
| Per-die primary stored on `DieOutcome` | No. 137 dies are wrong. The chart does not read that field |

**Pareto integrity: WARNING.** The total is correct. The test-id bars are correct. The taxonomy text and several dashboard names are not a safe reading of those bars.

## 7. ML Dataset Audit

Built in memory by `ml/dataset.py`. Not a saved table. Hidden ground-truth files are not read.

| Item | Value |
| --- | --- |
| Grain | One row per FPY-eligible die |
| Physical identity | `(lot_id, wafer_id, die_id)` on the frame, joined to the first-pass attempt by `attempt_id` |
| Rows | 2,500 |
| Unique physical dies | 2,500 |
| Target | `first_pass_fail`: 1 if first-pass disposition is FAIL, else 0 |
| Positives | 251 |
| `test_id` in X | No |
| `failure_code` in X | No. Denied |
| Primary failure in X | No |
| Parametric measurements in X | No. The builder only pivots `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, `TEST_TIME_MS`. None of those names exist in V2 |
| `die_id` as a feature | No |
| `lot_id` / `wafer_id` | On the frame. `lot_id` is the split key only. Neither is a feature |
| Duplicate `die_id` leakage | No. Samples are not collapsed by `die_id`. A die cannot sit in two lots, so leave-one-lot-out cannot put the same physical die on both sides |

Features emitted on this dataset (16):

`die_x`, `die_y`, `normalized_x`, `normalized_y`, `radial_distance`, `edge_distance`, `spatial_region`, `timestamp_epoch`, `temperature_c`, `voltage_v`, `site`, `tester_id`, `probe_card_id`, `prober_id`, `tester_fail_rate`, `probe_fail_rate`.

Split if this folder is evaluated with `configs/ml.yaml`: leave-one-lot-out, 5 folds, 2,000 train dies and 500 test dies. Fail counts differ by lot. They are not changed by taxonomy or test names.

**ML dataset integrity: PASS** for sample identity, row count, target, and leakage relative to `die_id`, test outcomes, and hidden labels. The missing parametric features are a scope choice, not a corrupted sample list.

## 8. Parametric Data / ML Join Audit

The eight measurements are on `parametric_measurements.csv` and are already inputs to the parametric and near-limit detectors.

| Question | Finding |
| --- | --- |
| Join key | `attempt_id` on the first-pass attempt. Globally unique. Reliable |
| Cardinality | Exactly 8 measurements per attempt. A pivot is one ML row per die, not 8 |
| Duplication | None, if the join is restricted to attempt 1 and pivoted by `parameter_name` |
| Retests | 480 retest measurement cells are exact copies of attempt 1. They must not become extra samples |
| Available before the outcome? | The numbers are on the same attempt as `pass_fail`. They are test-time measurements, not a later retest result |
| Target leakage | `pass_fail` on the parametric file is a limit verdict. It must stay out of X. Raw `IDDQ`, `VMIN`, and `CONTACT_RESISTANCE` are near the label: the generator marks the die failed when the value crosses the limit and then assigns T005, T006, or T004 |
| Useful as predictors? | Possibly, in a later experiment. They are not required to define a valid V2 model |
| Why they are separate today | `PARAM_NAMES` and the feature allowlist still name a different parameter set. Detectors own the distribution tests. ML is denied outcome columns |

**Recommendation: DO NOT JOIN in the first `yi_ml_v2`.** Keep the current 16-feature contract. A later model can add the raw measurements only, with parametric `pass_fail` still excluded, and with a written note that limit breaches help create the synthetic label.

## 9. yi_ml_v1 Audit

From `artifacts/ml/registry/registry.json` and `artifacts/ml/yi_ml_v1/metadata.json`:

| Item | Value |
| --- | --- |
| Version | `yi_ml_v1` |
| State | ACTIVE |
| Architecture | logistic regression |
| Samples stored on the artifact | 784 |
| `analysis_id` | not `yi_synthetic_v2` |
| Target | first-pass fail (same rule family, different population) |
| Feature list | the same 16 names |
| Trained on V2? | No |

The feature names match because V2’s parametric columns are dropped, not because this artifact saw the 2,500 dies.

| Action | Audit position |
| --- | --- |
| Leave `yi_ml_v1` unchanged | Yes |
| Retire it in this step | No |
| Quote its metrics as V2 performance | No |
| Retrain it in place | No. The trainer refuses to overwrite `artifacts/ml/yi_ml_v1/` |
| Replace it later with `yi_ml_v2` | Yes, through the existing model lifecycle, as a new version |

**Status: historical active model. Not a V2 model. Do not modify it while building `yi_ml_v2`.**

## 10. Required Changes Before yi_ml_v2

| Proposed change | Required before ML? | Required before analytics? | UI only? | Risk if skipped | Recommendation |
| --- | --- | --- | --- | --- | --- |
| 1. Fix `die_id` ambiguity | No | Yes, before any per-die primary display | The Pareto chart is already safe | 137 per-die primaries stay wrong. ML stays correct | Fix later. Key the copy by `(lot_id, wafer_id, die_id)` |
| 2. Define T001–T010 semantics | No | No | Labels already exist and several are unsupported | Users read T004 as a functional test when the code is CONTACT | Do not add meanings. Do not use the overlay as analytical truth |
| 3. Define test ↔ failure-code mapping | No | The generator mapping already exists | No | None for ML. A new taxonomy map would only change labels | Keep the generator table. Do not invent CONTACT → T001 |
| 4. Fix `UNKNOWN.UNMAPPED_CODE` | No | Only if taxonomy text will be acted on | The Pareto test-id bars do not need it | 136 primaries keep an unknown family label. Counts stay 251 | Optional policy edit after ML. Do not guess OPENS/SHORTS/CONTACT |
| 5. Update dashboard labels | No | No | Yes, and it is already wired | Current labels can misname the largest bar (T004) | Not part of training. If edited later, match the generator code |
| 6. Verify FPY | Already verified | — | — | None. 2,249 / 2,500 and 251 are stable | Record 89.96% and move on |
| 7. Verify Pareto | Already verified | Taxonomy text still weak | Display names can still mislead | Total 251 is safe. Reading the taxonomy or overlay as root cause is not | Trust test-id counts. Do not trust overlay names |
| 8. Join parametric data | No | Detectors already use it | No | First model lacks IDDQ/VMIN/resistance features. Joining `pass_fail` would leak | Keep out of the first `yi_ml_v2` |
| 9. `sbin` vs earliest code on 20 fails | No | Only if bins are interpreted | No | FPY ignores `sbin` when `pass_fail` is set | Leave the data. Do not regenerate |
| 10. Spatial radius from (0, 0) | No | Interpreting CENTER/EDGE | No | ML “center” is the (1, 1) corner, not the middle of the grid | Train with the current features. Document the geometry |
| 11. `yi_ml_v1` still active | Do not retrain it | Do not present it as the V2 model | The ML card can show its old metrics | Readers may think 784-sample metrics describe these 2,500 dies | Leave the artifact. Train `yi_ml_v2` as a new version |

## 11. Recommended Execution Order

1. Train `yi_ml_v2` on the current V2 contract: 2,500 rows, target `first_pass_fail`, the 16 features above, leave-one-lot-out, no parametric join. Do not overwrite `yi_ml_v1`.
2. After that model exists, if a screen must show each die’s primary test, change the dictionary in `yield_analysis/fpy.py` to `(lot_id, wafer_id, die_id)` and re-check that the Pareto sum is still 251.
3. Do not add test-type names. If dashboard text is corrected, make it repeat the generator failure code, or leave T007–T010 unclassified and stop extending the overlay.
4. Taxonomy edits, if any, are an explicit `bin_map.yaml` policy change after ML. They must not be used to restate FPY. `VMAX` and `LEAKAGE` are the only near-copies of existing maps. `CONTACT`, `OPENS`, and `SHORTS` stay unmapped until a taxonomy detail is actually chosen.

## 12. Risks

| Risk | If we train now | If we clean up first |
| --- | --- | --- |
| Wrong ML sample count | Low. 2,500 physical dies are already the sample list | Delay, with no change to X or y |
| Learning the label from bins or failure codes | Low. Those columns are denied | Unchanged |
| Learning from hidden scenario fields | Low. They are not on the agent-visible tables | Unchanged |
| Misreading the Pareto as root cause | Present today, with or without training. Test-id bars are fine; taxonomy and overlay names are not | Fixing names does not make the bar a root cause |
| Acting on per-die primary fields | High if a new UI reads `DieOutcome.primary_failure_*` before the key is fixed | Required before that UI, not before ML |
| Parametric leakage | Avoided if the eight measurements stay out of the first model | Joining `pass_fail` would be the leak. Raw limit values are still close to the synthetic label |
| Overwriting `yi_ml_v1` | Avoided if `yi_ml_v2` is a new version | Same constraint |
| Treating 784-sample metrics as V2 quality | High if the dashboard keeps showing only `yi_ml_v1` after a V2 model exists | Lifecycle switch is a later step, not this audit |

Other facts that do not block training:

- 20 failing attempts have an `sbin` that does not match the earliest failure code.
- Retest measurements, temperature, and voltage are copies of attempt 1.
- `wafers.csv`, `parts.csv`, and `equipment.csv` are not loaded by FPY, detectors, ML, or report assembly. Equipment on the attempt row is what the model sees.
- `process_chamber_id` and `parent_equipment_id` are blank.

## Final Decision

**Can we proceed directly to `yi_ml_v2`, or should we perform cleanup first?**

Proceed directly to `yi_ml_v2`.

Cleanup of `die_id` primary copy, test-type names, and `UNKNOWN.UNMAPPED_CODE` does not change the eligible population, the 251 failures, the 89.96% FPY, the test-id Pareto total, or the 2,500-row ML identity. Those cleanups are analytics and display work. Doing them first does not make the training set more correct. Extending the current test-name overlay would make the dashboard less faithful to the generator.

The first V2 model should use the current 16-feature contract, leave the parametric file to the detectors, and leave `yi_ml_v1` on disk as a historical model.
