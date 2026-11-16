# V2 ML Measurement Enhancement — Implementation

This document records the implementation of the approved pre-sort oxide measurement.
It does not train a model and it does not activate a model.

## 1. Source V2 dataset

Source path:

`data/synthetic/agent_visible/yi_synthetic_v2/`

That directory is the production V2 dataset: 5 lots, 25 wafers, 2500 physical dies.
Physical identity is `(lot_id, wafer_id, die_id)`.

SHA-256 of the outcome files after this implementation, unchanged from the locked V2 hashes:

| File | SHA-256 |
| --- | --- |
| die_attempts.csv | `3aebf4b320ea086d8b4a86fd38a55cc7b362651fbb760dc8b83aff243f5fad4e` |
| test_results.csv | `843f6c38c20aa5744bd9380c2f341706a124aa33552a3b1020d62341e6ed0e9b` |
| parametric_measurements.csv | `ae99fe60313374b94a86fd5b1116f5ba9dead3cc1afa0b58d45a769035edb678` |

## 2. New measurement

Column: `pre_sort_oxide_thickness_nm`

Meaning: pre-sort inline gate-oxide thickness.

Unit: nm, carried by the column name and by `enhancement.json` (`"unit": "nm"`).

The value is numeric. Stored values are the formula result rounded to 6 decimal places, the same storage precision already used for parametric measurements. Rounding is storage precision. The coefficients were not adjusted after seeing the distribution.

## 3. Formula

```
pre_sort_oxide_thickness_nm
    = 3.20
    + 8.0 * lot_eff
    + 8.0 * wafer_eff
    + side_stream_normal(0, 0.05)
```

`lot_eff` and `wafer_eff` are the process offsets already drawn for that lot and wafer while `fail_p` is computed. The normal draw comes from the side stream in section 5. The formula does not take fail probability, the fail bit, a limit result, a test result, a failure code, or a label.

## 4. Generation point

The draw happens in `build_population`, after `fail_p` is computed for that die and before `realize`.

```
lot/wafer process state
        |
        +--> fail probability --> existing first-pass fail decision
        |                         --> existing parameter limit logic
        |                         --> final disposition
        |
        +--> pre_sort_oxide_thickness_nm --> stored measurement
                                              --> ML feature candidate
```

`realize` does not read the column. Parameter limit checks do not read the column. Retest attempt rows copy the first-pass value. There is no second draw on a retest.

The production writer used by `generate_v2(write=True)` omits this column when it writes `yi_synthetic_v2`. This implementation did not call that writer. The enhanced copy is produced by `write_enhanced_dataset`.

## 5. Random-stream separation

Oxide noise uses its own `random.Random`, initialized from the constant `OXIDE_SIDE_STREAM_SEED` (`17611001`).

The main generator stream is a different `random.Random`. The side stream is created beside it and is never passed into `fail_p`, `realize`, or the limit checks. Drawing oxide noise does not advance the main stream.

The side-stream constant is not written into the enhanced tables or `enhancement.json`.

A regeneration with a different side-stream seed changes thickness and leaves `fail_p`, `die.failed`, parametric measurements, failure codes, and fail-test ids the same. The main generator's RNG state after `build_population` is the same in both runs.

## 6. Data lineage

```
yi_synthetic_v2
        +
pre_sort_oxide_thickness_nm
        =
enhanced ML candidate dataset
```

Enhanced path:

`data/synthetic/ml_enhanced/yi_synthetic_v2_ml_enhanced/`

This is the same V2 scenario with one stored measurement appended. It is not a second manufacturing world.

`data/synthetic/agent_visible/` is the production dataset selector. Every subdirectory there that contains `die_attempts.csv` is listed as a production dataset. The enhanced copy is stored outside that folder so the selector, and the dashboard that reads it, still shows only `yi_synthetic_v2`.

`enhancement.json` in the enhanced directory records the source path, the added column, the unit, the outcome counts, and the distribution summary. It does not contain scenario, cause, ground-truth, injection, or seed fields.

Unchanged V2 files are byte copies. `die_attempts.csv` in the enhanced directory keeps every original field and appends `pre_sort_oxide_thickness_nm`.

## 7. Outcome preservation

Regenerated rows were compared value-for-value with the stored V2 files on every existing column of:

- die_attempts
- test_results
- parametric_measurements

The comparison matched. The writer stops if any existing cell differs. The original files were hashed before the copy and hashed again after it. The hashes matched the locked values in section 1.

| Quantity | Value |
| --- | --- |
| Eligible first-pass dies | 2500 |
| First-pass failures | 251 |
| First-pass passes | 2249 |
| FPY | 0.8996 |
| FPY loss | 0.1004 |

Lot ids, wafer ids, die ids, and attempt ids match the source file. First-pass dispositions match. Primary failure counts on first-pass fails match:

| Primary failure code | Dies |
| --- | --- |
| CONTACT | 92 |
| VMIN | 39 |
| IDDQ | 38 |
| CONTINUITY | 17 |
| OPENS | 13 |
| VMAX | 12 |
| FUNCTIONAL | 12 |
| SHORTS | 10 |
| LEAKAGE | 9 |
| SCAN | 9 |

Test rows and existing parametric rows match the source files byte-for-byte, because those files are copies.

## 8. Coverage

2500 of 2500 first-pass eligible dies have a numeric `pre_sort_oxide_thickness_nm`.

Missing count: 0.

Retest rows, 60 of them, carry the same value as the first-pass row of the same `(lot_id, wafer_id, die_id)`. They are not additional physical dies and they are not additional ML samples. The attempt count in the file is 2560 because the original retest attempts are still present.

## 9. Leakage validation

Automated checks in `leakage_report` all passed:

1. `pre_sort_oxide_thickness_nm` is not read when calculating `fail_p`.
2. It is not read when calculating `die.failed`.
3. It is not read by existing parameter limit checks, and it is not a parametric limit name.
4. The thickness function is not derived from `first_pass_fail`.
5. It is not derived from failure code.
6. It is not derived from test outcome.
7. It is not derived from primary failure.
8. The enhanced tables and lineage file do not contain `scenario_id`.
9. They do not contain `true_cause`.
10. They do not contain `ground_truth`.
11. They do not contain `injected_effect`.
12. They do not contain `generator_seed`.
13. The thickness values are not a copy of fail probability. Every die differs from its `fail_p` by more than 1.

Behavioral checks agree with those source checks. Thickness is assigned before `realize`. Flipping `die.failed` and `failure_code` after generation leaves thickness unchanged. A different side-stream seed leaves the fail bit and the parametric measurements unchanged.

## 10. Distribution statistics

First-pass dies only. Unit: nm. Missing: 0.

| Statistic | Value |
| --- | --- |
| n | 2500 |
| min | 2.852666 |
| max | 3.492546 |
| mean | 3.157660 |
| median | 3.166210 |
| standard deviation | 0.114017 |

The values sit in a narrow band around the 3.20 nm baseline. Within-wafer standard deviations are about 0.041 to 0.057 nm, in line with the 0.05 nm metrology noise. Lot means differ by a few tenths of a nanometer, in line with `8.0 * lot_eff` at the existing lot-offset scale. No value is missing, non-numeric, or far from that band. The coefficients were not changed after these numbers were computed.

## 11. PASS/FAIL descriptive comparison

These are descriptive summaries of the stored column split by the existing first-pass disposition. A difference between the two means does not establish a root cause, and it does not establish that the measurement causes the disposition.

| First-pass disposition | n | Mean (nm) | Std (nm) |
| --- | --- | --- | --- |
| PASS | 2249 | 3.155508 | 0.113913 |
| FAIL | 251 | 3.176940 | 0.113353 |

The two groups overlap. Both standard deviations are about 0.114 nm. The mean difference is about 0.021 nm.

## 12. Lot and wafer variation

Lot-level mean and standard deviation, 500 dies each:

| Lot | Mean (nm) | Std (nm) |
| --- | --- | --- |
| L001 | 3.275076 | 0.073271 |
| L002 | 3.226306 | 0.059142 |
| L003 | 3.001192 | 0.058832 |
| L004 | 3.170117 | 0.070598 |
| L005 | 3.115609 | 0.052885 |

Wafer-level mean and standard deviation, 100 dies each:

| Wafer | Mean (nm) | Std (nm) |
| --- | --- | --- |
| L001/W01 | 3.299761 | 0.048612 |
| L001/W02 | 3.210412 | 0.050821 |
| L001/W03 | 3.237873 | 0.052548 |
| L001/W04 | 3.363927 | 0.047244 |
| L001/W05 | 3.263407 | 0.052649 |
| L002/W01 | 3.174428 | 0.047610 |
| L002/W02 | 3.266796 | 0.050421 |
| L002/W03 | 3.224182 | 0.049960 |
| L002/W04 | 3.237984 | 0.050996 |
| L002/W05 | 3.228142 | 0.056605 |
| L003/W01 | 3.014588 | 0.050969 |
| L003/W02 | 2.966429 | 0.047681 |
| L003/W03 | 2.984596 | 0.047370 |
| L003/W04 | 3.060615 | 0.053724 |
| L003/W05 | 2.979733 | 0.041623 |
| L004/W01 | 3.179360 | 0.052141 |
| L004/W02 | 3.155630 | 0.046139 |
| L004/W03 | 3.085410 | 0.046647 |
| L004/W04 | 3.184117 | 0.048495 |
| L004/W05 | 3.246065 | 0.046652 |
| L005/W01 | 3.077793 | 0.050817 |
| L005/W02 | 3.137675 | 0.053534 |
| L005/W03 | 3.125922 | 0.041360 |
| L005/W04 | 3.127714 | 0.048382 |
| L005/W05 | 3.108940 | 0.048585 |

Lot means differ. Wafers inside a lot also differ. Within a wafer, the spread is close to the metrology noise. These patterns describe the generated column. They were not used to change the generator.

## 13. Original vs enhanced dataset relationship

```
data/synthetic/agent_visible/yi_synthetic_v2/
        +
pre_sort_oxide_thickness_nm
        =
data/synthetic/ml_enhanced/yi_synthetic_v2_ml_enhanced/
```

The enhanced directory is a candidate ML view of the same scenario. The production path remains the original directory. `yi_ml_v1` still trains and scores from its existing artifact. This implementation does not point the active model, the feature allowlist, or the dashboard at the enhanced directory.

## 14. What remains unchanged

- Original V2 file bytes and the locked SHA-256 hashes
- First-pass failure count, pass count, and FPY
- Lot, wafer, die, and attempt identifiers
- First-pass dispositions and the primary failure distribution
- Test rows and existing parametric rows
- Failure probability, fail threshold, parametric limits, and failure taxonomy
- `yi_ml_v1` artifact and its ACTIVE registry state
- Registry contents, including the absence of `yi_ml_v5`
- Dashboard dataset selector, which still lists only `yi_synthetic_v2`
- Production authorization, which stays false

## 15. What is now possible

A later controlled experiment can read `pre_sort_oxide_thickness_nm` from the enhanced dataset as a candidate feature for first-pass dies, joined on `(lot_id, wafer_id, die_id)` and restricted to attempt 1.

The column is present as stored measurement data. It is not in the active feature contract. No model has been fit to it.

## 16. Why yi_ml_v5 has not yet been trained

This step adds and validates the measurement. Training `yi_ml_v5` was outside the implementation task. No training run was started, no candidate artifact was written, and no model was activated.

`yi_ml_v1` remains the active model.
