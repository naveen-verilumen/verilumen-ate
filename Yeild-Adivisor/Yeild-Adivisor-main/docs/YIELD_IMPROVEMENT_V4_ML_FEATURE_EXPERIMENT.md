# Yield Improvement V4 Feature Experiment

`yi_ml_v4` is a CANDIDATE. It is not approved, not active, and not a production authorization. `yi_ml_v1` remains the active model. `yi_ml_v2` and `yi_ml_v3_spatial` were not retrained.

Predictive scores are associations with first-pass failure. They are not a root cause and not a promised yield recovery. Production authorization remains false. ML cannot change ATE limits, recipes, equipment settings, or test programs.

## 1. Why ML is required, and why it can fail closed

The investigation flow is:

dataset, feature validation, ML prediction, failure-risk ranking, statistical evidence, investigation finding, opportunity, next investigation.

ML is a required evidence layer. It does not outrank safety. A finding may be called ML-supported only when the model beats a constant-rate reference on ranking and calibration across held-out lots. Otherwise the ML status is `NEEDS_MORE_DATA`. Statistical evidence can still be reported. It must not be labeled as ML support.

The reference for this dataset is a first-pass failure rate of 0.1004. Constant PR-AUC is 0.1004. Constant Brier is 0.0903. ROC-AUC is compared with 0.5, not with 10.04%.

## 2. Existing models

| Model | State | Role in this experiment |
| --- | --- | --- |
| `yi_ml_v1` | ACTIVE | Historical model. Not modified |
| `yi_ml_v2` | CANDIDATE | Baseline 16-column contract. Not retrained |
| `yi_ml_v3_spatial` | CANDIDATE | BORDER/INNER spatial experiment. Not retrained |
| `yi_ml_v4` | CANDIDATE | This feature experiment. Not activated |

`yi_ml_v3_spatial` was not promoted. Replacing radius categories with BORDER/INNER did not produce generalizable ranking.

## 3. Dataset and target

`data/synthetic/agent_visible/yi_synthetic_v2/` was not regenerated.

2,500 eligible dies, 251 first-pass failures, 2,249 first-pass passes, FPY 0.8996, FPY loss 0.1004, primary-failure Pareto total 251.

Target: `first_pass_fail`. Physical identity is `(lot_id, wafer_id, die_id)`.

Split: leave-one-lot-out, five folds, 2,000 train and 500 test, no shared lot. Calibration is isotonic and fit on the training lots of that fold only. The model family is logistic regression. Threshold 0.5 was not tuned on the test lot.

## 4. Leakage audit for parametric measurements

Each of the eight measurements has 2,500 first-pass rows and 60 retest rows. Retest rows were excluded. The parametric `pass_fail` column is the limit result and was rejected for every parameter.

The numeric value is written on the first-pass attempt. The generator sets that attempt to FAIL when the value is outside its limit, so the measurement is an in-test result rather than an input available before the outcome. A hidden shift that correlates a measurement with failure is not the reason for rejection.

| Parameter | Limit fails on first pass | Decision |
| --- | ---: | --- |
| VMIN | 28 | REJECTED |
| VMAX | 1 | REJECTED |
| IDDQ | 29 | REJECTED |
| SUPPLY_CURRENT | 0 | REJECTED |
| CONTACT_RESISTANCE | 0 | REJECTED |
| INTERCONNECT_RESISTANCE | 0 | REJECTED |
| ON_RESISTANCE | 0 | REJECTED |
| VDD | 0 | REJECTED |

No parametric column entered the matrix. Combinations that add those columns were not trained.

## 5. Experiments that were scored

| Experiment | What changed | Trained now |
| --- | --- | --- |
| Baseline | Existing `yi_ml_v2` | No |
| Baseline + spatial | Existing `yi_ml_v3_spatial` BORDER/INNER | No |
| Baseline + temporal | Added `relative_position_within_lot` | Yes, saved as `yi_ml_v4` |
| Baseline + spatial + temporal | BORDER/INNER plus lot-relative time | Yes, metrics only |
| Any row that adds the eight measurements | Blocked by the audit | No |

`relative_position_within_lot` uses timestamps only. Within each lot, the earliest timestamp is 0 and the latest is 1. Failure labels are not used. A die's position uses its own lot's timestamps, not another lot's. `timestamp_epoch` remains in the matrix, so raw epoch is not the only temporal column.

## 6. Pooled calibrated results

| Metric | Baseline | + Spatial | + Temporal (`yi_ml_v4`) | + Spatial + temporal |
| --- | ---: | ---: | ---: | ---: |
| ROC-AUC | 0.4592 | 0.4666 | 0.4499 | 0.4509 |
| PR-AUC | 0.0909 | 0.0939 | 0.0894 | 0.0917 |
| Recall at 0.5 | 0.0239 | 0.0000 | 0.0239 | 0.0199 |
| Precision at 0.5 | 0.1053 | 0.0000 | 0.0750 | 0.1020 |
| F1 at 0.5 | 0.0390 | 0.0000 | 0.0363 | 0.0333 |
| Balanced accuracy | 0.5006 | 0.5000 | 0.4955 | 0.5002 |
| Brier | 0.1006 | 0.0970 | 0.1035 | 0.1018 |
| Log loss | 0.3744 | 0.3602 | 0.3829 | 0.3797 |
| ECE | 0.0673 | 0.0638 | 0.0736 | 0.0684 |
| Top-10% capture | 0.0757 | 0.0797 | 0.0797 | 0.0637 |
| Top-20% capture | 0.1474 | 0.1434 | 0.1434 | 0.1793 |

Constant PR-AUC is 0.1004. Constant Brier is 0.0903. Every pooled PR-AUC is below 0.1004. Every pooled Brier is above 0.0903. Every pooled ROC-AUC is below 0.5.

## 7. Per-lot PR-AUC

| Held-out lot | Failure rate | Baseline | + Spatial | + Temporal | + Spatial + temporal |
| --- | ---: | ---: | ---: | ---: | ---: |
| L001 | 0.066 | 0.0711 | 0.0735 | 0.0691 | 0.0703 |
| L002 | 0.098 | 0.1256 | 0.1587 | 0.1089 | 0.1192 |
| L003 | 0.076 | 0.1055 | 0.0926 | 0.0906 | 0.0897 |
| L004 | 0.194 | 0.2022 | 0.2002 | 0.1849 | 0.1864 |
| L005 | 0.068 | 0.0750 | 0.0919 | 0.0733 | 0.0865 |

Per-lot ROC-AUC:

| Held-out lot | Baseline | + Spatial | + Temporal | + Spatial + temporal |
| --- | ---: | ---: | ---: | ---: |
| L001 | 0.4718 | 0.5176 | 0.5100 | 0.5164 |
| L002 | 0.5566 | 0.5952 | 0.5089 | 0.5183 |
| L003 | 0.5820 | 0.5758 | 0.5611 | 0.5535 |
| L004 | 0.5161 | 0.5238 | 0.4691 | 0.4854 |
| L005 | 0.5124 | 0.5996 | 0.5170 | 0.5653 |

## 8. Interpretation

None of the feature groups produced generalizable predictive value.

Lot-relative time did not carry the L004 wafer gradient into held-out ranking. On L004, PR-AUC fell below the lot's 0.194 failure rate and ROC-AUC fell below 0.5. L002 also got worse than the baseline when the temporal column was added. The spatial-only candidate still has the strongest L002 PR-AUC, and that gain does not hold on L003 or L004.

`yi_ml_v4` stores the baseline-plus-temporal logistic model because no leakage-valid spec beat the baseline on three or more lots while also clearing the constant-rate checks. Its ML support status is `NEEDS_MORE_DATA`. It is not suitable for a later validation or activation step on these results.

An investigation finding that would depend on this model must stay `NEEDS_MORE_DATA` and must not be presented as ML-supported.

## 9. Limitations

- Parametric combinations were not scored because the audit rejected the measurements.
- Five held-out lots is a small comparison.
- Within-lot timestamp scaling uses the earliest and latest timestamps in that lot. It does not use labels or another lot.
- The active model is still the historical `yi_ml_v1` artifact. These V2 candidates do not replace it.
