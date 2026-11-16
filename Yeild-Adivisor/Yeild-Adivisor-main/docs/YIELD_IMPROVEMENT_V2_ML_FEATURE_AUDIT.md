# V2 ML Feature Audit

Audit only. No model was trained. `yi_ml_v5` was not created. `yi_ml_v1` stays ACTIVE. Production authorization stays false.

The question is whether the saved V2 tables contain a leakage-free representation that could support a later supervised model of `first_pass_fail`. Correlation with failure is not treated as leakage. A value is target-derived only when it is assigned from the fail bit. A value is not a legitimate model input when the fail bit is assigned from that value.

## 1. Current ML feature contract

The live contract is the 16 columns emitted by `FeatureBuilder`. The V2 parametric names are not among them. `load_ml_dataset` reads `parametric_measurements.csv`, then `_parametric_map` keeps only the V1 names `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, and `TEST_TIME_MS`. None of those names are in the V2 file, so the ML frame has no parametric columns.

Source of the 2,500 ML rows: first-pass eligible dies from `die_attempts.csv`. Target: `first_pass_fail`, 1 when `calculate_fpy` marks the first attempt FAIL. Identity on the frame is `(lot_id, wafer_id, die_id)` plus `attempt_id`. `die_id` alone is not unique.

| Feature | Source | Meaning |
| --- | --- | --- |
| `die_x`, `die_y` | `die_attempts.csv` `x`, `y` | Integer grid position, 1 through 10 |
| `normalized_x`, `normalized_y` | Derived in the training fold | `(x - train min) / train span` |
| `radial_distance` | Derived | Distance from the origin |
| `edge_distance` | Derived | Training-fold max radius minus radial distance |
| `spatial_region` | Derived | `EDGE` if radius ≥ train 80th percentile, `CENTER` if radius ≤ train 20th, else `OTHER` |
| `timestamp_epoch` | `timestamp` | Seconds after the earliest timestamp in the training fold |
| `temperature_c`, `voltage_v`, `site` | `die_attempts.csv` | Condition and site copied from the attempt |
| `tester_id`, `probe_card_id`, `prober_id` | `die_attempts.csv` | Equipment ids |
| `tester_fail_rate`, `probe_fail_rate` | Derived from the training labels | Mean of `first_pass_fail` by tester or probe card inside the training fold |

On this grid every leave-one-lot fit produces the same bounds: x and y span 1 to 10, radius edge quantile 10.770, center quantile 5.796, and the same 525 / 500 / 1,475 EDGE / CENTER / OTHER counts. The coordinate encoding does not move between folds. `tester_fail_rate` and `probe_fail_rate` do move, because they are means of the training labels.

## 2. Feature-by-feature leakage audit

`build_population` writes coordinates, equipment, temperature, voltage, site, and timestamp before `die.failed` exists. Site is `(x - 1) % 2`. None of those fields are assigned from the fail bit.

`tester_fail_rate` and `probe_fail_rate` are the exception. They are functions of `first_pass_fail` on the rows used to fit the builder. In leave-one-lot-out that is the other four lots, not the held-out die. They are still target-derived aggregates, not pre-disposition measurements.

Descriptive separation uses the raw columns, not a fitted model. Cohen's d is fail mean minus pass mean, divided by the pooled standard deviation. "Overlap" is the fraction of failing dies inside the pass 10th–90th percentile. Single-feature ROC is a ranking of that column, not a trained model. For the two fail-rate features, the numbers below are in-sample encodings fit on all 2,500 labels, so they are not held-out evidence.

| Feature | Before disposition | Target leakage | Stable across lots | Keep |
| --- | --- | --- | --- | --- |
| `die_x`, `normalized_x` | Yes | No | No. d = 0.059, ROC 0.517. Lot ROC for high values: 0.466, 0.515, 0.548, 0.498, 0.585 | Yes, as position. Not sufficient |
| `die_y`, `normalized_y` | Yes | No | No. d = −0.024, ROC 0.493. Lot signs flip | Yes, as position. Not sufficient |
| `radial_distance`, `edge_distance` | Yes | No | No. d = 0.037. Lot ROC around 0.5 except L005 0.579 | Yes. Not sufficient |
| `spatial_region` | Yes | No | Encoding is fold-stable. Fail rates are not: EDGE 0.124, CENTER 0.102, OTHER 0.092. L001 EDGE is not higher than CENTER | Yes, as the current encoding. Not sufficient |
| `timestamp_epoch` | Yes | No | No. Pooled ROC 0.559 is L004 (within-lot ROC 0.748, d = 0.917). L001–L003 and L005 are 0.457–0.502 | Yes. The L004 pattern does not transfer |
| `temperature_c` | Yes | No | No. d = 0.053. Lot d ranges from −0.262 to 0.231 | Yes. Not sufficient |
| `voltage_v` | Yes | No | No. d = 0.033. Pass mean 0.8004, fail mean 0.8007 | Yes. Not sufficient |
| `site` | Yes | No | No. d = 0.004. Overlap 1.0 | Yes. Not sufficient |
| Equipment ids | Yes | No | No. T01 fail rate 0.115, T02 0.089, T03 0.092. L003 T02 is 0.036 while L004 T02 is 0.212 | Yes. Not sufficient |
| `tester_fail_rate`, `probe_fail_rate` | No | Yes, from training labels | Not a physical measurement | Keep only as a fold-local aggregate. Do not treat it as a pre-outcome feature |

Missingness is 0 for every contract column on the 2,500 first-pass rows.

Grid border, which is not the ML contract but is the observable edge of the same coordinates: border fail rate 0.131 (118 / 900) and inner 0.083 (133 / 1,600). By lot, border minus inner is −0.008, +0.107, +0.029, +0.035, +0.076. L001 goes the other way. That matches the earlier spatial model: a real L002 gap, not a five-lot rule.

## 3. Parametric measurement audit

Storage: `parametric_measurements.csv`. One row per parameter per attempt. Join keys are `attempt_id`, `lot_id`, `wafer_id`, and `die_id`. The numeric column is `measurement` (copied to `value`). `pass_fail` on that row is the limit check, not a separate sensor.

Generation order inside `realize`:

1. A role-based mean shift may be added for `CONTACT_RESISTANCE`, `IDDQ`, or `VMIN`. The shift does not read `die.failed`.
2. Each parameter is drawn from its pass distribution plus that shift.
3. `die.failed` is set from `fail_p`.
4. If the draw is still a pass and any parameter is outside its limit, `die.failed` is set to True.

The draw does not use the fail bit. The fail bit does use the draw when the limit is missed. That second direction is leakage of the label rule, not a correlation. The parametric `pass_fail` column is that rule and is denied.

Observed first-pass limit misses, all of which are also attempt failures:

| Parameter | Limit misses | Miss and attempt FAIL | Miss and attempt PASS | Force rule in code | Legitimate model input |
| --- | ---: | ---: | ---: | --- | --- |
| VMIN | 28 | 28 | 0 | Yes. Upper limit assigns FAIL | No |
| VMAX | 1 | 1 | 0 | Yes. Lower limit assigns FAIL | No |
| IDDQ | 29 | 29 | 0 | Yes. Upper limit assigns FAIL | No |
| SUPPLY_CURRENT | 0 | 0 | 0 | Yes, if a value exceeded the upper limit. None does | No. Separation is null |
| CONTACT_RESISTANCE | 0 | 0 | 0 | Yes, if a value exceeded the upper limit. None does | No. Lot ROC is not consistent |
| INTERCONNECT_RESISTANCE | 0 | 0 | 0 | Yes, if a value exceeded the upper limit. None does | No. Separation is null |
| ON_RESISTANCE | 0 | 0 | 0 | Yes, if a value exceeded the upper limit. None does | No. Separation is null |
| VDD | 0 | 0 | 0 | Yes, if a value left the limit window. None does | No. Separation is null |

56 distinct first-pass attempts have at least one limit miss. All 56 are first-pass failures. No first-pass pass has a limit miss. The other 195 failures have no limit miss.

Removing each parameter's own limit-miss rows does not create a clean feature. VMIN's remaining fail-versus-pass d is 0.330, and IDDQ's is 0.181. Those leftovers are still the same column the force rule reads, and section 8 shows they concentrate in L004. CONTACT_RESISTANCE has no limit miss, d = 0.152, pooled ROC 0.538. Its lot ROC values are 0.479, 0.608, 0.638, 0.507, 0.534. L001 is below 0.50.

## 4. Test-slot audit

`test_results.csv` columns are `attempt_id`, `lot_id`, `wafer_id`, `die_id`, `test_id`, `sequence_index`, `test_pass_fail`, `pass_fail`, `failure_code`, `is_first_fail`, and `timestamp`.

There is no measurement column. First-pass rows are exactly T001 through T010 in that order for every one of the 2,500 attempts (25,000 rows). The timestamp is the attempt timestamp, repeated on every slot. `test_pass_fail` is written in `_test_rows` from `die.failed` and `fail_test_ids` after the fail bit already exists. On all 2,500 first-pass dies, "any slot is FAIL" matches the attempt FAIL flag.

`GRU = BLOCKED_LEAKAGE_RISK`. No sequence input was created.

## 5. Join audit

First-pass attempts: 2,500. Retest attempts: 60. First-pass failures: 251. First-pass passes: 2,249.

Physical key `(lot_id, wafer_id, die_id)` is unique on those 2,500 rows. `die_id` has 100 values and 25 first-pass rows each, so a `die_id`-only join crosses lots and wafers.

For each of the eight parameters, first-pass rows are 2,500, unique `(lot_id, wafer_id, die_id, attempt_id)` keys are 2,500, duplicate keys are 0, and missing joins onto the 2,500 first-pass dies are 0. The same `die_id`-only group has 25 rows for every parameter.

Retest parametric rows: 480, which is 60 attempts times 8 parameters. They reuse `die.measurements` from the first pass; they are not new draws. A join that ignores `attempt_number` would mix those 480 rows into the first-pass matrix. The ML loader's first-pass die loop does not do that, and it also does not attach the V2 parameter names.

Retest test rows: 600.

## 6. Data-generation ordering

The code order is not "measure, then execute tests, then discover the disposition."

```text
build_population
    coordinates, equipment, temperature, voltage, site, timestamp, fail_p
        ↓
realize
    optional mean shift, then parameter draw
        ↓
    fail bit from fail_p
        ↓
    if the draw was a pass and a parameter is outside its limit, force the fail bit
        ↓
build_tables
    disposition, failure code, and T001–T010 outcomes are written from that bit
        ↓
first_pass_fail
    first-attempt disposition from calculate_fpy
```

Legitimate pre-disposition fields are the population context and the parameter draw. The parameter draw is not target-derived. It becomes unusable for this target when the next step defines the target from the limit check. Test-slot outcomes and the parametric `pass_fail` column are written from the fail bit. They are target-derived.

## 7. PASS versus FAIL descriptive analysis

Contract numerics, except the in-sample fail rates and the timestamp, have |d| ≤ 0.059 and overlap of 0.69–1.0. Timestamp overlap is 0.892; its pooled gap is the L004 wafer gradient, not a five-lot shift.

Among parameters, only VMIN (d = 0.611, ROC 0.632, PR-AUC 0.296) and IDDQ (d = 0.501, ROC 0.606, PR-AUC 0.257) clear the 0.1004 prevalence by a wide margin. Both include limit misses that force FAIL. The other six parameters have pooled ROC between 0.478 and 0.538 and PR-AUC between 0.101 and 0.121.

## 8. Cross-lot stability

Within-lot ROC for a high parameter value:

| Parameter | L001 | L002 | L003 | L004 | L005 |
| --- | ---: | ---: | ---: | ---: | ---: |
| VMIN | 0.555 | 0.556 | 0.532 | 0.728 | 0.513 |
| IDDQ | 0.400 | 0.582 | 0.494 | 0.671 | 0.560 |
| CONTACT_RESISTANCE | 0.479 | 0.608 | 0.638 | 0.507 | 0.534 |
| VMAX | 0.450 | 0.468 | 0.529 | 0.452 | 0.519 |
| SUPPLY_CURRENT | 0.418 | 0.516 | 0.478 | 0.464 | 0.519 |
| INTERCONNECT_RESISTANCE | 0.546 | 0.481 | 0.554 | 0.431 | 0.508 |
| ON_RESISTANCE | 0.472 | 0.537 | 0.548 | 0.514 | 0.560 |
| VDD | 0.516 | 0.455 | 0.564 | 0.570 | 0.460 |

VMIN and IDDQ peak on L004. IDDQ reverses on L001. CONTACT is above 0.60 on L002 and L003 only. No leakage-free column keeps the same direction on all five lots at a level that beats a constant ranker.

## 9. GRU feasibility

`GRU = BLOCKED_LEAKAGE_RISK`.

The ten slots exist, in order, on the first-pass attempt. The slot record adds no measurement beyond the id, the sequence index, the repeated timestamp, and the outcome fields. Using those outcome fields predicts `first_pass_fail` because the outcome was written from the fail bit.

## 10. Final representation verdict

**B. Insufficient representation.**

The ordering is not ambiguous, so C does not apply. The current contract is leakage-controlled apart from the two training-label rates, and the architecture benchmark already showed that contract does not beat prevalence. The two parameters that do separate PASS from FAIL are inputs to the fail assignment. The parameters that are not observed to force a fail do not separate the classes in a way that holds across lots. There is no defensible leakage-free set on these tables that justifies another trained model.

## 11. Recommended next experiment

Do not train `yi_ml_v5`. Do not add the eight parametric measurements. Do not unblock the GRU on the current test table.

A later dataset, if one is authorized, needs a measurement that is recorded before disposition and is not read back to set the fail bit, the test outcome, or the failure code. Until that exists, ML support on V2 stays `NEEDS_MORE_DATA`. `yi_ml_v1` remains the active model.
