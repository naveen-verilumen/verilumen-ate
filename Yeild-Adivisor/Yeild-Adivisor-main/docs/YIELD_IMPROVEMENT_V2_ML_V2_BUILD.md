# Yield Improvement V2 ML Build

yi_ml_v2 is trained on the Yield Improvement V2 dataset and is separate from the historical yi_ml_v1 artifact.

Training date: 2026-09-29T06:04:32Z. Random seed: 7. Python 3.13.7. scikit-learn 1.8.0. Git revision was not available in this workspace. Lifecycle state: CANDIDATE. Production activation: no.

## 1. Dataset

| Item | Value |
| --- | --- |
| Dataset ID | `yi_synthetic_v2` |
| Display name | Yield Improvement V2 |
| Path | `data/synthetic/agent_visible/yi_synthetic_v2/` |
| File used for rows | `die_attempts.csv` |
| Eligible physical dies | 2,500 |
| First-pass PASS | 2,249 |
| First-pass FAIL | 251 |
| FPY | 0.8996 (89.96%) |
| FPY loss | 0.1004 (10.04%) |
| Lots | L001, L002, L003, L004, L005 |

The existing loader also opens `parametric_measurements.csv` and `test_results.csv`. Neither file contributes a column to the feature matrix. Hidden ground truth was not read and is not stored in the training manifest.

## 2. ML Grain

One ML row is one eligible physical die. The identity is `(lot_id, wafer_id, die_id)`. `die_id` alone is not unique: the same die id repeats across wafers and lots. The join to the outcome uses the globally unique first-pass `attempt_id`. Identity columns are kept for grouping and are not model features.

The built matrix has 2,500 rows, 2,500 unique physical keys, and 2,500 unique `attempt_id` values.

## 3. Target

`first_pass_fail` comes from the existing FPY outcome, not from a second implementation.

- 1 = first-pass FAIL
- 0 = first-pass PASS

Counts match the FPY result: 251 positives and 2,249 negatives. A later retest PASS does not change the label. Every die whose first attempt failed and whose final disposition is PASS still has `first_pass_fail = 1`, and the ML row stays joined to attempt 1.

## 4. Feature Contract

Sixteen features, in this order:

1. `die_x`
2. `die_y`
3. `normalized_x`
4. `normalized_y`
5. `radial_distance`
6. `edge_distance`
7. `spatial_region`
8. `timestamp_epoch`
9. `temperature_c`
10. `voltage_v`
11. `site`
12. `tester_id`
13. `probe_card_id`
14. `prober_id`
15. `tester_fail_rate`
16. `probe_fail_rate`

Numeric columns use median imputation and `StandardScaler`. Categorical columns (`spatial_region`, `tester_id`, `probe_card_id`, `prober_id`) use most-frequent imputation and `OneHotEncoder(handle_unknown="ignore")`. Each leave-one-lot-out fold fits that preprocessing on its training lots only. The saved artifact fits the same preprocessing on all 2,500 rows for inference. The V2 matrix has no missing values in these 16 columns. Preprocessing version: `yi_ml_features_v1`.

## 5. Leakage Prevention

These outcome and evaluation fields are excluded from the feature list:

`pass_fail`, `failure_code`, `disposition`, `abort_flag`, `is_retest`, `attempt_number`, `is_first_attempt`, `sequence_index`, `primary_failure_key`, `primary_failure_code`, `sbin`, `hbin`, `test_pass_fail`, `is_first_fail`, `scenario_id`, `true_cause`, `injected_effect`, `generator_seed`, `ground_truth`, `recoverable_fraction`.

`lot_id` is the split group only. It is not a predictive feature. The allowlist check in the existing feature builder rejects any derived column outside the contract.

## 6. Parametric Data Decision

Parametric measurements stay out of yi_ml_v2. The feature matrix contains zero parametric columns. These names are absent from the model:

`VMIN`, `VMAX`, `IDDQ`, `VDD`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE`.

The historical names `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, and `TEST_TIME_MS` are also absent. The parametric file was not modified. Detector behavior was not changed.

## 7. LOLO Split

Leave-one-lot-out, five folds. Each lot is the test lot once. Every fold has 2,000 training rows and 500 test rows. Train lots and the test lot are disjoint in every fold.

| Fold | Test lot | Train lots | Train + / − | Test + / − |
| --- | --- | --- | --- | --- |
| 1 | L001 | L002, L003, L004, L005 | 218 / 1,782 | 33 / 467 |
| 2 | L002 | L001, L003, L004, L005 | 202 / 1,798 | 49 / 451 |
| 3 | L003 | L001, L002, L004, L005 | 213 / 1,787 | 38 / 462 |
| 4 | L004 | L001, L002, L003, L005 | 154 / 1,846 | 97 / 403 |
| 5 | L005 | L001, L002, L003, L004 | 217 / 1,783 | 34 / 466 |

Overall training exposure across the five folds is 2,000 rows per fold. Overall test exposure is 500 rows per fold, and each die is tested exactly once.

## 8. Models Evaluated

The existing candidate family was scored on the same folds:

| Model | Raw PR-AUC | Raw ROC-AUC | Raw recall | Raw F1 | Raw Brier | Top-10 capture | Top-20 capture |
| --- | --- | --- | --- | --- | --- | --- | --- |
| logistic | 0.1012 | 0.4964 | 0.4701 | 0.1670 | 0.2731 | 0.0797 | 0.1713 |
| random_forest | 0.0923 | 0.4750 | 0.2032 | 0.1176 | 0.1993 | 0.0637 | 0.1594 |
| hist_gbm | 0.0910 | 0.4664 | 0.2590 | 0.1268 | 0.2524 | 0.0518 | 0.1434 |
| xgboost | 0.0912 | 0.4729 | 0.2510 | 0.1265 | 0.2530 | 0.0598 | 0.1394 |
| lightgbm | 0.0909 | 0.4723 | 0.2191 | 0.1146 | 0.2473 | 0.0677 | 0.1355 |

CatBoost did not import in this environment (`ModuleNotFoundError`). It was not installed for this run.

The positive rate is 0.1004, so a PR-AUC near 0.10 is the base-rate reference for this label.

## 9. Fold Results

Class metrics use the existing threshold of 0.5. That threshold was not tuned on the test fold. The tables below are the selected logistic model after fold-local isotonic calibration.

| Test lot | ROC-AUC | PR-AUC | Precision | Recall | F1 | Balanced accuracy | Brier | Log loss | Top-10 | Top-20 | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L001 | 0.4718 | 0.0711 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0629 | 0.2497 | 0.0606 | 0.1212 | 0.0334 |
| L002 | 0.5566 | 0.1256 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0885 | 0.3462 | 0.2041 | 0.3061 | 0.0145 |
| L003 | 0.5820 | 0.1055 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0703 | 0.2696 | 0.0789 | 0.2368 | 0.0307 |
| L004 | 0.5161 | 0.2022 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.1713 | 0.6200 | 0.0825 | 0.1856 | 0.1199 |
| L005 | 0.5124 | 0.0750 | 0.1053 | 0.1765 | 0.1319 | 0.5335 | 0.1099 | 0.3866 | 0.1471 | 0.1765 | 0.1902 |

Confusion at threshold 0.5, calibrated probabilities:

| Test lot | TP | TN | FP | FN |
| --- | --- | --- | --- | --- |
| L001 | 0 | 467 | 0 | 33 |
| L002 | 0 | 451 | 0 | 49 |
| L003 | 0 | 462 | 0 | 38 |
| L004 | 0 | 403 | 0 | 97 |
| L005 | 6 | 415 | 51 | 28 |

Raw (pre-calibration) fold scores for the same model are higher on recall because the uncalibrated scores sit closer to 0.5. Mean and standard deviation of those raw fold scores: ROC-AUC 0.5333 ± 0.0408, PR-AUC 0.1379 ± 0.0507, recall 0.5000 ± 0.3181, F1 0.1667 ± 0.0730, Brier 0.2731 ± 0.1031, top-10 capture 0.1476 ± 0.0566, top-20 capture 0.2328 ± 0.1041.

## 10. Aggregate Results

Pooled calibrated out-of-fold scores, which are the scores the saved calibrator is built to emit:

| Metric | Value |
| --- | --- |
| ROC-AUC | 0.4592 |
| PR-AUC | 0.0909 |
| Precision | 0.1053 |
| Recall | 0.0239 |
| F1 | 0.0390 |
| Balanced accuracy | 0.5006 |
| Brier | 0.1006 |
| Log loss | 0.3744 |
| ECE | 0.0673 |
| Top-10 failure capture | 0.0757 |
| Top-20 failure capture | 0.1474 |

Calibrated fold mean ± sample standard deviation: ROC-AUC 0.5278 ± 0.0426, PR-AUC 0.1159 ± 0.0532, recall 0.0353 ± 0.0789, F1 0.0264 ± 0.0590, balanced accuracy 0.5067 ± 0.0150, Brier 0.1006 ± 0.0435, log loss 0.3744 ± 0.1481, top-10 capture 0.1146 ± 0.0597, top-20 capture 0.2052 ± 0.0697.

Aggregate confusion at threshold 0.5: TP 6, TN 2,198, FP 51, FN 245.

Pooled raw scores for the selected model, used only for model selection: ROC-AUC 0.4964, PR-AUC 0.1012, recall 0.4701, F1 0.1670, Brier 0.2731, top-10 capture 0.0797, top-20 capture 0.1713.

## 11. Calibration

Method: isotonic (`yi_ml_cal_v1`).

Inside each fold, the calibrator is fit on that fold's training-lot raw probabilities and applied to the held-out lot. The held-out lot is not used to fit that fold's calibrator. The deployed calibrator is then fit on the pooled out-of-fold raw probabilities, matching the existing training design. It is not fit on in-sample training probabilities.

Isotonic mapping pulls most scores below 0.5. That lowers Brier relative to the raw scores and also drops threshold-0.5 recall to 0.0239. Only the L005 test fold produces any positive class calls after calibration.

## 12. Feature Importance

Permutation importance on the deployed logistic model (160 rows, 2 repeats, ROC-AUC scoring). This is model feature importance: a predictive association. It is not a root cause and it is not a causal effect.

| Feature | Importance |
| --- | --- |
| radial_distance | 0.0500 |
| edge_distance | 0.0500 |
| spatial_region | 0.0478 |
| timestamp_epoch | 0.0267 |
| die_y | 0.0246 |
| normalized_y | 0.0246 |
| die_x, normalized_x, temperature_c, voltage_v, site, tester_id, probe_card_id, prober_id, tester_fail_rate, probe_fail_rate | 0.0000 |

`radial_distance` and `edge_distance` move together because edge distance is the complement of radial distance on this wafer grid. A shared permutation score is a predictive association between those constructed coordinates and the model score.

## 13. Selected Model

Selected family: logistic regression (`logistic`).

Selection follows `configs/ml.yaml`: highest pooled raw PR-AUC, then lower Brier, then the simpler model when PR-AUC is within 0.02 of the best. Logistic has the highest raw PR-AUC (0.1012). Every other trained family is also within 0.02 of that value, so the simplicity rule selects logistic as well. Accuracy was not the selection metric.

The saved operating metrics are the calibrated out-of-fold metrics in section 10. Those scores do not separate first-pass failures from the 10.04% base rate in a useful way. The model remains supporting predictive evidence only.

## 14. Artifact

Directory: `artifacts/ml/yi_ml_v2/`

| File | Role |
| --- | --- |
| `model.pkl` | Preprocessing, logistic pipeline, deployed isotonic calibrator |
| `metadata.json` | `model_id=yi_ml_v2`, dataset, counts, seed, state |
| `feature_list.json` | The 16 feature names |
| `metrics.json` | Calibrated aggregate metrics and the raw comparison |
| `preprocessing.json` | Imputer, scaler, encoder |
| `calibration.json` | Fold-local and deployed isotonic description |
| `evaluation.json` | Fold metrics, confusion matrices, importance |
| `training_manifest.json` | Reproducibility manifest |
| `hashes.json` | Hashes of the four champion-shaped files |

Registry record `yi_ml_v2` is CANDIDATE. `active_version` remains `yi_ml_v1`. `validate_candidate` accepts only ids of the form `yi_ml_vN_candidate_NNN`. The required directory is `artifacts/ml/yi_ml_v2/`, which is not that id, so the validation gate was not applied and the record was not moved to VALIDATED or REJECTED.

## 15. Validation Tests

`tests/unit/test_yi_ml_v2.py` checks the row count, the 251/2,249 label split, physical-die uniqueness, duplicate rows, the 16-feature list, parametric and leakage exclusions, five disjoint LOLO folds, the retest label, preservation of yi_ml_v1, the V2 artifact and CANDIDATE registry state, inference probability plus class, and the absence of a root-cause field. The manifest records `hidden_ground_truth_stored: false`.

## 16. yi_ml_v1 Preservation

`artifacts/ml/yi_ml_v1/` was not rewritten. Its champion file hashes still match the registry record. Its state is still ACTIVE. Its metadata still describes the historical 784-sample model. Those historical scores are not V2 scores.

yi_ml_v1 is the historical model trained on 784 samples. yi_ml_v2 is the new model trained on the V2 2,500-die dataset.

Live analysis still loads the active model. ML evidence, when attached, stays `SECONDARY_SUPPORT` with `not_a_root_cause` set. This build does not create a root cause, change detector scores, change safety state, change FPY, change the failure Pareto, change opportunities, or authorize production.

## 17. Limitations

- Ranking is close to the 10.04% base rate. Calibrated PR-AUC is 0.0909 and calibrated ROC-AUC is 0.4592.
- After isotonic calibration, threshold 0.5 recalls almost none of the 251 first-pass failures (6 true positives, 245 false negatives).
- L004 holds 97 of the 251 failures, so fold metrics move with that lot.
- Permutation importance is an in-sample association on the deployed fit. It does not identify a cause.
- The eight parametric measurements remain available to the existing statistical detectors and are outside this model.
- CatBoost was not evaluated because the package is not installed.
- Physical-die primary-failure attribution now uses `(lot_id, wafer_id, die_id)`. That change does not alter this ML table.
- `yi_ml_v2` was not retrained after the grid-border correction. Its `spatial_region` feature is still the radius-quantile category (`EDGE` / `CENTER` / `OTHER`) from training. A future experiment may evaluate the diagnostic `BORDER` / `INNER` representation.
- Test catalog labels and bin-map semantics were left unchanged.

## 18. Next Step

Review yi_ml_v2 as a CANDIDATE. Do not activate it and do not replace yi_ml_v1. A promotion would need an explicit approval path. Until that happens, yield investigation should continue to use the statistical detectors and hypothesis composition. ML output from this artifact is a failure-probability ranking and a feature-importance list, and both are secondary predictive evidence.
