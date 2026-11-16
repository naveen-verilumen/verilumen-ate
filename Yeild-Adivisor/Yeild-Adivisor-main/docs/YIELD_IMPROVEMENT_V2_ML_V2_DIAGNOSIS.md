# Yield Improvement V2 ML Diagnosis

The saved `yi_ml_v2` logistic candidate does not rank first-pass failures better than the 10.04% base rate. Pooled calibrated out-of-fold ROC-AUC is 0.4592, below 0.5. Pooled PR-AUC is 0.0909, below the positive rate 0.1004. Pooled Brier score is 0.1006, which is worse than predicting 0.1004 for every die (that constant score has Brier 0.0903). Top-10% failure capture is 0.0757 and top-20% capture is 0.1474, both below the random-ranking values 0.10 and 0.20.

This is a property of the current 16-feature leave-one-lot-out scores. It is not a root cause, and it is not a reason to activate the candidate. `yi_ml_v1` remains the active model. No artifact was retrained or rewritten for this diagnosis.

## 1. Contract check

Checked against `data/synthetic/agent_visible/yi_synthetic_v2/`, `artifacts/ml/yi_ml_v2/metadata.json`, `feature_list.json`, and `training_manifest.json`.

| Check | Result |
| --- | --- |
| ML rows | 2,500 |
| `first_pass_fail = 1` | 251 |
| `first_pass_fail = 0` | 2,249 |
| Features | 16, equal to the saved feature list |
| Parametric columns in that list | 0 |
| Leakage columns in that list | 0 |
| LOLO folds | 5, test lots L001, L002, L003, L004, L005 |
| Train / test rows per fold | 2,000 / 500 |
| Physical key | `(lot_id, wafer_id, die_id)` unique on the 2,500 rows |

The eight parametric names (`VMIN`, `VMAX`, `IDDQ`, `VDD`, `SUPPLY_CURRENT`, `CONTACT_RESISTANCE`, `INTERCONNECT_RESISTANCE`, `ON_RESISTANCE`) are absent. So are `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, and `TEST_TIME_MS`.

## 2. Per-lot results

Prevalence below is the first-pass failure rate in that lot. ROC-AUC, PR-AUC, precision, recall, F1, Brier, ECE, and failure capture are calibrated out-of-fold scores for the logistic model at the existing threshold 0.5. The threshold was not fit on the test fold.

| Lot | Dies | Failures | Prevalence | ROC-AUC | PR-AUC | Precision | Recall | F1 | Brier | ECE | Top-10 | Top-20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L001 | 500 | 33 | 0.066 | 0.4718 | 0.0711 | 0.000 | 0.000 | 0.000 | 0.0629 | 0.0334 | 0.0606 | 0.1212 |
| L002 | 500 | 49 | 0.098 | 0.5566 | 0.1256 | 0.000 | 0.000 | 0.000 | 0.0885 | 0.0145 | 0.2041 | 0.3061 |
| L003 | 500 | 38 | 0.076 | 0.5820 | 0.1055 | 0.000 | 0.000 | 0.000 | 0.0703 | 0.0307 | 0.0789 | 0.2368 |
| L004 | 500 | 97 | 0.194 | 0.5161 | 0.2022 | 0.000 | 0.000 | 0.000 | 0.1713 | 0.1199 | 0.0825 | 0.1856 |
| L005 | 500 | 34 | 0.068 | 0.5124 | 0.0750 | 0.1053 | 0.1765 | 0.1319 | 0.1099 | 0.1902 | 0.1471 | 0.1765 |

### Pooled scores are not the average of the folds

| Metric | Pooled out-of-fold | Unweighted mean of the five folds | Sample std of the five folds |
| --- | --- | --- | --- |
| ROC-AUC | 0.4592 | 0.5278 | 0.0426 |
| PR-AUC | 0.0909 | 0.1159 | 0.0532 |
| Recall | 0.0239 | 0.0353 | 0.0789 |
| F1 | 0.0390 | 0.0264 | 0.0590 |
| Brier | 0.1006 | 0.1006 | 0.0435 |
| Top-10 capture | 0.0757 | 0.1146 | 0.0597 |
| Top-20 capture | 0.1474 | 0.2052 | 0.0697 |

The mean of the fold ROC-AUCs is 0.5278. The pooled ROC-AUC is 0.4592. Both numbers are in `artifacts/ml/yi_ml_v2/evaluation.json` (`per_lot_calibrated` and `aggregate_calibrated`). The mean treats each lot as one unit. The pooled score stacks the five held-out score vectors and ranks all 2,500 dies together. L004 holds 97 of the 251 failures, and its calibrated scores sit in the same 0.06–0.12 band as the low-prevalence lots, so those failures are not placed above the other lots' passing dies. Averaging the fold AUCs hides that.

## 3. Scores, calibration, and baselines

Out-of-fold probability vectors were not written into the artifact. `evaluation.json` keeps reliability bins, confusion counts, and the metrics above. A continuous threshold sweep would require those vectors or a new fit. This phase did not refit the classifier.

Random and base-rate references:

| Reference | Value | Pooled calibrated model |
| --- | --- | --- |
| ROC-AUC of an uninformative rank | 0.50 | 0.4592 |
| PR-AUC of a constant score | 0.1004 | 0.0909 |
| Brier of predicting 0.1004 for every die | 0.0903 | 0.1006 |
| Top-10% capture of a random rank | 0.10 | 0.0757 |
| Top-20% capture of a random rank | 0.20 | 0.1474 |

Raw out-of-fold scores, before isotonic calibration, have ECE 0.4098. Their mass sits in the 0.3–0.8 bins while the observed failure rate stays near 0.10. That gap matches `class_weight: balanced` in `configs/ml.yaml`: the raw logistic score is pulled toward a balanced decision, not toward the 10% event rate. Fold-local isotonic regression then compresses those scores using each training fold's labels.

Calibrated bin counts:

| Lot | Where the calibrated scores sit | Observed failure rate inside those bins |
| --- | --- | --- |
| L001 | 265 in 0.0–0.1, 230 in 0.1–0.2 | 0.075 and 0.052 |
| L002 | 326 in 0.0–0.1, 174 in 0.1–0.2 | 0.086 and 0.121 |
| L003 | 222 in 0.0–0.1, 276 in 0.1–0.2 | 0.054 and 0.091 |
| L004 | 384 in 0.0–0.1, 116 in 0.1–0.2 | 0.195 and 0.190 |
| L005 | spread from 0.1–0.2 through 0.5–0.6 (57 dies) | 0.071, 0.063, 0.052, 0.105; not increasing |

L001–L004 have no populated bin at or above 0.5. At the policy threshold 0.5 their confusion counts are TP 0, FP 0, and FN equal to the lot's failure count. L005 is the only fold with positive calls: TP 6, FP 51, TN 415, FN 28. Aggregate calibrated confusion is TP 6, TN 2,198, FP 51, FN 245.

Moving the threshold does not repair the pooled ranking. L004's two populated bins have observed rates 0.195 and 0.190, so a lower threshold changes how many L004 dies are flagged and does not concentrate the failures. L002 is the only lot whose top-20% capture (0.306) is clearly above the random value 0.20. L003's ROC-AUC is 0.582, but its top-10% capture is 0.079, below 0.10.

## 4. Preprocessing and feature behavior

Source: `src/yield_improvement/ml/features.py`, the saved `model.pkl` pipeline, and a read-only pass of `fit_feature_builder` on the V2 rows. The classifier was not refit.

### Confirmed: three feature pairs are the same measurement

On the 2,500-row matrix the correlations are exact:

| Pair | Correlation |
| --- | --- |
| `die_x`, `normalized_x` | +1 |
| `die_y`, `normalized_y` | +1 |
| `radial_distance`, `edge_distance` | −1 |

Every lot uses the same 1–10 grid, so min-max normalization is an affine copy of the raw coordinate. `edge_distance` is `radius_max - radial_distance`. The saved in-sample coefficients mirror that: `edge_distance` −0.235 and `radial_distance` +0.235, `die_y` and `normalized_y` both −0.231, `die_x` and `normalized_x` both −0.200. Permutation importance in `evaluation.json` ties `radial_distance` and `edge_distance`. This is a feature-construction defect. It does not, by itself, explain an AUC near 0.5; a later paired run has to measure how much AUC moves after the copies are removed.

### Confirmed: spatial region is distance from the origin, not the wafer border

`spatial_region` labels a die EDGE when `hypot(x, y)` is at or above the training 80th percentile and CENTER when it is at or below the 20th percentile. On this grid those cutpoints are 10.77 and 5.80. The generator's border is `x` in {1, 10} or `y` in {1, 10}, and its center is the middle block of the 10×10 grid.

| Geometry | Dies | Overlap with the feature of the same name |
| --- | --- | --- |
| Generator border | 900 | 325 also labeled ML EDGE (36%) |
| Generator center | 400 | 25 also labeled ML CENTER (6%) |

Coordinate (1, 1) is on the generator border and is ML CENTER, because its radius is 1.41. Coordinate (5, 5) is in the generator center and is ML OTHER, because its radius is 7.07. The quantiles do not change across LOLO folds: every training set of four lots still contains the full grid. Unknown-category handling is not the spatial failure. The region definition is.

Inside L002, generator-border dies fail at 0.1667 (180 dies) and interior dies fail at 0.0594 (320 dies). Dies the model calls EDGE fail at 0.1238. The label association follows the border. The feature the model receives is a different partition.

### Confirmed: lot timestamps do not overlap, so LOLO extrapolates time

With the clock zeroed at the first L001 die, the lot ranges are disjoint:

| Lot | `timestamp_epoch` minimum | `timestamp_epoch` maximum | Correlation with the label |
| --- | --- | --- | --- |
| L001 | 0 | 47,655 | 0.004 |
| L002 | 172,800 | 220,455 | −0.044 |
| L003 | 345,600 | 393,255 | −0.005 |
| L004 | 518,400 | 566,055 | 0.341 |
| L005 | 691,200 | 738,855 | −0.011 |

`timestamp_epoch` subtracts the minimum timestamp of the rows used to fit the builder. Holding out L001 makes every L001 score negative. Holding out L005 leaves L005 more than 100,000 seconds after the training clock. A linear coefficient fit on the other lots is then applied outside the training range.

L004 is the only lot whose label moves with time. Its wafer failure rates are W01 0.06, W02 0.09, W03 0.11, W04 0.26, W05 0.45. The other four lots have correlations near zero, so the slope is not available when L004 is the test lot. The saved model, which was fit on all five lots, has an in-sample `timestamp_epoch` coefficient of +0.192. That coefficient has seen L004. The held-out L004 scores have not.

### Equipment identifiers do transfer as categories

T01, T02, and T03 occur in every lot (109 to 235 dies each). PC01–PC03 and PR01–PR02 also occur in every lot. `OneHotEncoder(handle_unknown="ignore")` is not dropping a held-out lot's equipment level. `tester_fail_rate` and `probe_fail_rate` are training-fold means of the label. They are legal under the current feature contract and they are fold-local. They cannot carry an excess that exists only in the held-out lot.

Agent-visible failure rates by tester:

| Lot | T01 | T02 | T03 |
| --- | --- | --- | --- |
| L001 | 0.083 | 0.068 | 0.038 |
| L002 | 0.120 | 0.087 | 0.077 |
| L003 | 0.114 | 0.036 | 0.061 |
| L004 | 0.183 | 0.212 | 0.193 |
| L005 | 0.061 | 0.054 | 0.103 |

L003 is the lot where one tester sits above the other two. L004 is high on all three testers. The in-sample one-hot coefficient on T01 is +0.058, smaller than the spatial and time terms. Those coefficients are predictive associations from the all-data fit, not causal effects and not out-of-fold importances.

`site` correlates with `die_x` at 0.174. It is not a duplicate of `die_x`. Its in-sample coefficient is −0.029.

## 5. Where the ranking is weak

The miss is pooled, and it is also visible inside the lot that contains the most failures.

- L002 and L003 are the only folds with ROC-AUC clearly above 0.55 (0.557 and 0.582). Their threshold-0.5 recall is still zero because every calibrated score is below 0.2.
- L004 has 97 failures and a within-lot wafer gradient from 0.06 to 0.45. Its calibrated ROC-AUC is 0.516 and its top-10 capture is 0.082. The two score bins have the same observed rate. The failures are present; the score does not order them.
- L001 and L005 stay next to chance on ROC-AUC. L005 is the only fold that crosses 0.5, and its bin rates do not rise with the score. Its Brier score, 0.1099, is far above the constant-rate Brier for a 0.068 event rate (0.0634). That pattern matches time extrapolation onto the latest lot, which is a hypothesis tied to the disjoint clocks in section 4, not a demonstrated recovery of a weak spatial pattern.

Feature importance in the artifact is permutation importance on the deployed fit. The largest values are the collinear radius pair, `spatial_region`, `timestamp_epoch`, and the Y coordinates. Equipment, temperature, voltage, and site are at zero in that sample. Read those values as predictive association only.

## 6. Offline comparison with the V2 scenario file

The comparison reads `evaluation/ground_truth/synthetic_v2/yi_synthetic_v2.json` inside `tests/evaluation/`. The ML package does not import that file. Injection magnitudes and the generator seed are not copied here. The file's signal family for each lot is the comparison key.

| Lot | Offline signal family | What the held-out scores do |
| --- | --- | --- |
| L001 | NONE | ROC-AUC 0.472. No ranking to recover. |
| L002 | SPATIAL.EDGE | Border dies fail at 0.167 and interior dies at 0.059, but the model region is not that border. ROC-AUC 0.557 and top-20 capture 0.306 are a partial lift, not a recovered edge screen. |
| L003 | EQUIPMENT.DEGRADATION | T01 fails at 0.114 against 0.036 and 0.061. ROC-AUC 0.582, top-10 capture 0.079. A mild rank shift does not collect the failures at the top of the list. |
| L004 | PROCESS.DRIFT | Wafer rates rise from 0.06 to 0.45. Held-out ROC-AUC 0.516 and top-10 capture 0.082. The lot that contains the drift is the test lot, and the other lots do not have that time-label slope. |
| L005 | WEAK | Prevalence 0.068, ROC-AUC 0.512. Near-chance is the expected scale. The scores that cross 0.5 are not ordered with the outcome. |

The generator writes the L002, L003, and L004 mechanisms into parametric shifts (`CONTACT_RESISTANCE`, `IDDQ`, `VMIN`) as well as into coordinates, tester id, and wafer time. Those measurements were kept out of this feature matrix by the pre-ML decision. The weak pooled AUC is what that contract produces under leave-one-lot-out. It is not evidence that the statistical detectors failed, and it is not a root cause.

## 7. Confirmed issues and open hypotheses

Confirmed from code, the saved metrics, and the agent-visible tables:

1. Pooled calibrated ranking is below the base-rate baselines in section 3. Fold-average ROC-AUC must not be quoted as the operating result.
2. After isotonic calibration, threshold 0.5 predicts failures only on L005.
3. `normalized_x`, `normalized_y`, and `edge_distance` duplicate `die_x`, `die_y`, and `radial_distance`.
4. `spatial_region` is radius from (0, 0). It does not implement the wafer border or the grid center. L002's failure rate follows the border.
5. Lot clocks are disjoint, so the held-out lot's `timestamp_epoch` is outside the training range. Only L004's labels move with time, and that lot is unseen when it is the test fold.
6. Tester, probe-card, and prober levels occur in every lot. Unseen one-hot categories are not the equipment failure.
7. The out-of-fold probability vector was not stored. Bin counts are the available score distribution.

Hypotheses that need a new run before they can be treated as defects or as fixes:

1. Dropping the three duplicate columns will change coefficients and will move pooled PR-AUC only slightly. Not yet measured.
2. Replacing the radius region with the border indicator will raise L002's held-out capture. Supported by the 0.167 versus 0.059 label gap, not yet measured as a model delta.
3. L005's scores above 0.2 are the extrapolated time coefficient. The bins are consistent with that and do not prove it against every other feature.
4. Adding the eight parametric measurements would expose the shifts the generator uses. That is a new feature contract, not a bug fix inside the current sixteen, and it was deliberately excluded from this candidate.
5. A wafer-index feature will not create L004 held-out skill if the other lots have no matching slope. That negative result is expected and still unmeasured.

No confirmed defect was found in the row count, the first-pass label, the retest rule, the five-fold lot separation, or the decision to leave parametric columns out of this artifact.

## 8. Experiments to run later

Do not activate `yi_ml_v2`. Do not replace `yi_ml_v1`. Each experiment is a new candidate run with the same seed, the same five lot folds, and a one-change difference from this artifact. Compare pooled calibrated PR-AUC, Brier, and top-20 capture, plus the L002 and L004 fold rows. Keep the 0.5 threshold fixed.

1. Spatial control. Define the region from the wafer border and the grid center, remove the radius-quantile labels, and rerun leave-one-lot-out. This is the first experiment because L002's labels already separate on the border and the current feature does not encode it.
2. Collinearity control. Drop `normalized_x`, `normalized_y`, and `edge_distance`. Expect a small metric change. A large change would mean the current logistic fit is unstable.
3. Persist the out-of-fold probabilities on the next training run so a threshold curve can be drawn without another fit.
4. Parametric contrast, as a separate candidate only. Add the eight measurements the current contract excludes and rerun the same folds. Use it to measure the cost of the exclusion. Do not merge it into `yi_ml_v2` and do not mark it active.
5. Drift negative control. Fit a model whose only extra feature is wafer order. Expect L004's held-out ROC-AUC to stay near 0.5, because the slope is not present in the other lots.

## 9. Lifecycle

Checked on `artifacts/ml/registry/registry.json` and the champion hashes.

| Item | State |
| --- | --- |
| Active version | `yi_ml_v1` |
| `yi_ml_v1` artifact hashes | equal to the registry record |
| `yi_ml_v2` state | CANDIDATE |
| `production_authorized` | false on the registry and on the V2 record |
| Production activation in this phase | none |

## Reproducible check

From the repository root:

```
python -m pytest tests/evaluation/test_yi_ml_v2_diagnosis.py tests/unit/test_yi_ml_v2.py -q
```

The diagnosis test reads the saved artifact, refits only the existing feature builder to inspect coordinates and timestamps, and reads the offline scenario file from the evaluation test. It does not write `artifacts/ml/yi_ml_v2/` or `artifacts/ml/yi_ml_v1/`.

Artifact references: `artifacts/ml/yi_ml_v2/evaluation.json`, `metadata.json`, `feature_list.json`, `training_manifest.json`, `calibration.json`, `preprocessing.json`, and `model.pkl`. Pipeline references: `src/yield_improvement/ml/features.py`, `src/yield_improvement/ml/benchmark.py`, `configs/ml.yaml`.
