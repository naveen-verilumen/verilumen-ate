# Yield Improvement V3 Spatial Experiment

Experimental comparison only. `yi_ml_v3_spatial` is a CANDIDATE. It is not approved, not active, and not a production authorization. `yi_ml_v1` remains the active model. `yi_ml_v2` remains an unchanged CANDIDATE.

Predictive metrics are associations with first-pass failure. They are not a root cause, not a causal effect, and not a predicted yield gain.

## 1. Why this experiment exists

`yi_ml_v2` was trained with `spatial_region` defined by distance from the coordinate origin: EDGE above the training 80th percentile of radius, CENTER below the 20th percentile, otherwise OTHER. On the V2 10×10 grid that label does not match the outer row and column.

The diagnostic layer now classifies a die as BORDER when it lies on the outermost observed X or Y, and INNER otherwise. On this dataset that is `x` or `y` equal to 1 or 10. This experiment asks whether putting that same label into the existing 16-column logistic model changes held-out first-pass-failure ranking.

The model was not selected for promotion.

## 2. Baseline

Baseline scores are the saved calibrated out-of-fold results in `artifacts/ml/yi_ml_v2/`. That artifact was not retrained and its files were not rewritten.

- Model family: logistic regression
- State: CANDIDATE
- Features: the existing 16-column contract
- `spatial_region`: EDGE / CENTER / OTHER from training radius quantiles

## 3. Experiment

`artifacts/ml/yi_ml_v3_spatial/`

- Model family: logistic regression, same training seed and preprocessing as the V2 pipeline
- State: CANDIDATE
- The only intended representation change is the value of `spatial_region`
- Those values are BORDER and INNER
- The label is produced by `yield_improvement.yield_analysis.grid_region` (`grid_bounds` and `is_grid_border`) fit on each fold's training rows
- The ML code does not keep a second copy of the border rule
- The default feature builder used by `yi_ml_v2` still emits the radius categories

No parametric measurements, timestamps beyond the existing `timestamp_epoch` column, failure codes, test results, primary-failure fields, sequence fields, retest fields, or hidden ground truth were added.

## 4. Dataset and target

Source: `data/synthetic/agent_visible/yi_synthetic_v2/`. The CSV files were not regenerated.

| Quantity | Value |
| --- | --- |
| Lots | 5 (L001–L005) |
| Wafers | 25 |
| Eligible dies | 2,500 |
| First-pass passes | 2,249 |
| First-pass failures | 251 |
| FPY | 0.8996 (89.96%) |
| FPY loss | 0.1004 (10.04%) |
| Primary-failure Pareto total | 251 |

Target: `first_pass_fail`, 1 for a first-pass FAIL and 0 for a first-pass PASS. A later retest PASS does not change a first-pass FAIL.

Physical identity is `(lot_id, wafer_id, die_id)`. `die_id` is not unique. The same `die_id` on another wafer or lot is a different row.

## 5. Split and calibration

Leave-one-lot-out, five folds. Each fold trains on 2,000 dies from four lots and tests on 500 dies from the remaining lot. No lot is in both sides of a fold.

Isotonic calibration is fit on the training lots of that fold only. The held-out lot's labels are not used to fit the calibrator. The decision threshold is 0.5 and was not tuned on the test lot.

Reported numbers below are calibrated out-of-fold scores. A pooled ROC-AUC below 0.5 can occur when scores from different folds are concatenated. Per-lot ROC-AUC is the fairer ranking view. PR-AUC should be read against the failure rate, not against 0.5.

## 6. Constant-rate reference

The pooled first-pass failure rate is 0.1004. A score that does not rank dies has PR-AUC equal to that rate. Its Brier score is `0.1004 * 0.8996 = 0.0903`.

Both models have pooled PR-AUC below 0.1004 and pooled Brier above 0.0903. Neither improves on a constant probability at the pooled level.

## 7. Pooled comparison

| Metric | yi_ml_v2 | yi_ml_v3_spatial |
| --- | ---: | ---: |
| Features | 16 | 16 |
| Spatial representation | radius EDGE / CENTER / OTHER | grid BORDER / INNER |
| ROC-AUC | 0.4592 | 0.4666 |
| PR-AUC | 0.0909 | 0.0939 |
| Recall at 0.5 | 0.0239 | 0.0000 |
| Precision at 0.5 | 0.1053 | 0.0000 |
| F1 at 0.5 | 0.0390 | 0.0000 |
| Balanced accuracy | 0.5006 | 0.5000 |
| Brier | 0.1006 | 0.0970 |
| Log loss | 0.3744 | 0.3602 |
| ECE | 0.0673 | 0.0638 |
| Top-10% failure capture | 0.0757 | 0.0797 |
| Top-20% failure capture | 0.1474 | 0.1434 |

The constant-rate PR-AUC is 0.1004 and the constant-rate Brier is 0.0903.

## 8. Per-lot comparison

PR-AUC on the held-out lot. The lot's own failure rate is the constant-score PR-AUC for that lot.

| Held-out lot | Failures / 500 | Lot failure rate | yi_ml_v2 PR-AUC | yi_ml_v3_spatial PR-AUC |
| --- | ---: | ---: | ---: | ---: |
| L001 | 33 | 0.066 | 0.0711 | 0.0735 |
| L002 | 49 | 0.098 | 0.1256 | 0.1587 |
| L003 | 38 | 0.076 | 0.1055 | 0.0926 |
| L004 | 97 | 0.194 | 0.2022 | 0.2002 |
| L005 | 34 | 0.068 | 0.0750 | 0.0919 |

ROC-AUC on the same held-out lots:

| Held-out lot | yi_ml_v2 ROC-AUC | yi_ml_v3_spatial ROC-AUC |
| --- | ---: | ---: |
| L001 | 0.4718 | 0.5176 |
| L002 | 0.5566 | 0.5952 |
| L003 | 0.5820 | 0.5758 |
| L004 | 0.5161 | 0.5238 |
| L005 | 0.5124 | 0.5996 |

## 9. Leakage checks

The feature matrix keeps the 16 contract names. It does not contain `first_pass_fail`, `pass_fail`, `failure_code`, primary-failure fields, `test_id`, `sequence_index`, `is_first_fail`, retest fields, `attempt_id`, `scenario_id`, `true_cause`, ground truth, injected effects, `generator_seed`, or `recoverable_fraction`.

The eight V2 parametric measurements are not joined. `tester_fail_rate` and `probe_fail_rate` are means of the training-fold labels only, as in `yi_ml_v2`.

## 10. Interpretation

The corrected border label does not provide a generalizable ranking gain that would justify replacing `yi_ml_v2`.

- Pooled PR-AUC rises from 0.0909 to 0.0939 and stays below the 0.1004 base rate.
- Pooled ROC-AUC rises from 0.4592 to 0.4666 and stays below 0.5.
- Brier and ECE move slightly toward the constant-rate reference and do not beat it.
- Top-10% capture is slightly higher. Top-20% capture is slightly lower.
- At threshold 0.5 the new model recalls none of the 251 failures. The baseline recalled about 2.4%.
- L002, the lot with the border failure-rate gap, is where PR-AUC moves the most (0.1256 to 0.1587). That is one held-out lot, not a cross-lot result.
- L005 PR-AUC and ROC-AUC also rise. L001 moves only slightly, and its baseline ROC-AUC was below 0.5.
- L003 PR-AUC falls. L004 PR-AUC is essentially unchanged and remains close to L004's 19.4% failure rate, with ROC-AUC still near 0.52. The border label does not capture L004's wafer gradient.
- The change is therefore mixed: visible on L002, smaller on L005, absent on L004, and not a pooled improvement over the base rate.

`yi_ml_v3_spatial` stays a CANDIDATE. It does not replace `yi_ml_v1` or `yi_ml_v2`.

## 11. Limitations

- One categorical column changed. Coordinates, radius, and edge distance are still in the matrix, so the border label is not the only spatial information.
- Leave-one-lot-out has five test lots. A gain on one or two lots is not a stable cross-lot result.
- Threshold 0.5 was not tuned. Ranking metrics are the relevant comparison.
- Calibration is isotonic and fold-local. Small probability shifts can zero out recall at 0.5 without a meaningful ranking change.
- No production, ATE, limit, or recipe setting was changed.
