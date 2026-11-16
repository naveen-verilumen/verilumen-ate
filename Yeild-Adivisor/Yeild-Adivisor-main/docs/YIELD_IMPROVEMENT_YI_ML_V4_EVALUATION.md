# yi_ml_v4 Evaluation

Evaluation only. No model was trained or activated for this report. Scores are predictive associations with first-pass failure. They are not a root cause and not a promised yield recovery.

`yi_ml_v1` stays ACTIVE. `yi_ml_v4` stays CANDIDATE. Production authorization stays false.

## 1. Model definition

`yi_ml_v4` is logistic regression on `yi_synthetic_v2`, target `first_pass_fail` (1 = first-pass FAIL, 0 = first-pass PASS). It uses the 16-column V2 baseline contract plus `relative_position_within_lot`. Parametric measurements are not in the matrix. The decision threshold is 0.5 and was not tuned on the held-out lot. Calibration is isotonic and fold-local.

Persisted state: CANDIDATE. `ml_support_status` is `NEEDS_MORE_DATA`. `promoted` is false. `production_authorized` is false. `automatic_activation` is false.

## 2. Dataset

`data/synthetic/agent_visible/yi_synthetic_v2/` was not regenerated for this evaluation.

2,500 eligible dies. 251 first-pass failures. 2,249 first-pass passes. Pooled failure prevalence is 251 / 2500 = 0.1004. FPY is 0.8996.

## 3. Feature change

The only change from `yi_ml_v2` is `relative_position_within_lot`.

Within each lot, using timestamps only:

- earliest timestamp → 0.0
- latest timestamp → 1.0
- intermediate timestamps scaled between 0 and 1

Failure labels are not used. One lot’s timestamps do not scale another lot. `timestamp_epoch` remains in the matrix. Spatial categories stay the radius contract used by `yi_ml_v2`. BORDER/INNER is the separate `yi_ml_v3_spatial` candidate and is not part of `yi_ml_v4`.

## 4. Validation protocol

Leave-one-lot-out, five folds. Each fold trains on 2,000 dies from four lots and tests 500 dies from the held-out lot. No lot is in both sides of a fold.

| Held-out lot | Test dies | Failing dies | Prevalence |
| --- | ---: | ---: | ---: |
| L001 | 500 | 33 | 0.066 |
| L002 | 500 | 49 | 0.098 |
| L003 | 500 | 38 | 0.076 |
| L004 | 500 | 97 | 0.194 |
| L005 | 500 | 34 | 0.068 |

Isotonic calibration for each fold is fit on training-lot scores only.

Constant-rate references for the pooled set: PR-AUC 0.1004, Brier 0.0903 (`0.1004 * 0.8996`). ROC-AUC is compared with 0.50. A random ranking captures about 10% of failures in the top 10% of scores and about 20% in the top 20%.

`yi_ml_v2` and `yi_ml_v3_spatial` were not retrained. Their numbers below are the persisted calibrated out-of-fold results.

## 5. Pooled metrics

`yi_ml_v4` calibrated out-of-fold scores, 2,500 dies, 251 positives, prevalence 0.1004.

| Metric | yi_ml_v4 | Constant reference |
| --- | ---: | ---: |
| ROC-AUC | 0.4499 | 0.50 |
| PR-AUC | 0.0894 | 0.1004 |
| Precision at 0.5 | 0.0750 | — |
| Recall at 0.5 | 0.0239 | — |
| F1 at 0.5 | 0.0363 | — |
| Balanced accuracy | 0.4955 | 0.50 |
| Brier | 0.1035 | 0.0903 |
| Log loss | 0.3829 | — |
| ECE | 0.0736 | — |
| Top-10% failure capture | 0.0797 | ~0.10 |
| Top-20% failure capture | 0.1434 | ~0.20 |

PR-AUC 0.0894 is below the V2 positive-class prevalence of 0.1004. Brier 0.1035 is above the constant Brier of 0.0903. ROC-AUC 0.4499 is below 0.50.

## 6. Per-lot metrics

Every lot is shown, including the weak ones. Counts are the leave-one-lot-out test folds. Metrics are calibrated `yi_ml_v4` scores.

| Lot | Dies | Fails | Prevalence | ROC-AUC | PR-AUC | Precision | Recall | F1 | Brier | Top-10 | Top-20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| L001 | 500 | 33 | 0.066 | 0.5100 | 0.0691 | 0.0000 | 0.0000 | 0.0000 | 0.0656 | 0.1212 | 0.1818 |
| L002 | 500 | 49 | 0.098 | 0.5089 | 0.1089 | 0.0000 | 0.0000 | 0.0000 | 0.0901 | 0.1633 | 0.2041 |
| L003 | 500 | 38 | 0.076 | 0.5611 | 0.0906 | 0.0000 | 0.0000 | 0.0000 | 0.0726 | 0.1053 | 0.2105 |
| L004 | 500 | 97 | 0.194 | 0.4691 | 0.1849 | 0.0000 | 0.0000 | 0.0000 | 0.1728 | 0.0928 | 0.1443 |
| L005 | 500 | 34 | 0.068 | 0.5170 | 0.0733 | 0.0750 | 0.1765 | 0.1053 | 0.1163 | 0.0882 | 0.2059 |

On L004, PR-AUC 0.1849 is below that lot’s 0.194 failure rate, and ROC-AUC 0.4691 is below 0.50. Top-10 and top-20 capture on L004 are also below a random ranking. L001, L003, and L005 have ROC-AUC above 0.50, but their PR-AUC values sit close to each lot’s own failure rate, and precision, recall, and F1 at 0.5 are zero on L001–L004 because calibrated probabilities stay below 0.5.

## 7. Comparison with yi_ml_v2

`yi_ml_v2` is the V2 baseline: same logistic model, same 16 features, no lot-relative column.

| Model | Main change | ROC-AUC | PR-AUC | Recall | F1 | Brier | Top-10 | Top-20 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| yi_ml_v2 | V2 baseline | 0.4592 | 0.0909 | 0.0239 | 0.0390 | 0.1006 | 0.0757 | 0.1474 |
| yi_ml_v3_spatial | corrected spatial region | 0.4666 | 0.0939 | 0.0000 | 0.0000 | 0.0970 | 0.0797 | 0.1434 |
| yi_ml_v4 | + lot-relative temporal feature | 0.4499 | 0.0894 | 0.0239 | 0.0363 | 0.1035 | 0.0797 | 0.1434 |

`yi_ml_v2` pooled ECE is 0.0673. `yi_ml_v4` pooled ECE is 0.0736. `yi_ml_v2` log loss is 0.3744. `yi_ml_v4` log loss is 0.3829.

Per-lot PR-AUC:

| Lot | Prevalence | yi_ml_v2 | yi_ml_v4 | Change |
| --- | ---: | ---: | ---: | ---: |
| L001 | 0.066 | 0.0711 | 0.0691 | −0.0020 |
| L002 | 0.098 | 0.1256 | 0.1089 | −0.0167 |
| L003 | 0.076 | 0.1055 | 0.0906 | −0.0149 |
| L004 | 0.194 | 0.2022 | 0.1849 | −0.0173 |
| L005 | 0.068 | 0.0750 | 0.0733 | −0.0017 |

Per-lot ROC-AUC:

| Lot | yi_ml_v2 | yi_ml_v4 | Change |
| --- | ---: | ---: | ---: |
| L001 | 0.4718 | 0.5100 | +0.0382 |
| L002 | 0.5566 | 0.5089 | −0.0477 |
| L003 | 0.5820 | 0.5611 | −0.0208 |
| L004 | 0.5161 | 0.4691 | −0.0470 |
| L005 | 0.5124 | 0.5170 | +0.0046 |

PR-AUC falls on every held-out lot. ROC-AUC rises on L001 and L005 and falls on L002, L003, and L004. L004 falls through 0.50.

## 8. Comparison with yi_ml_v3_spatial

`yi_ml_v3_spatial` replaces radius categories with BORDER/INNER. It was not retrained here and is not promoted.

Pooled, `yi_ml_v3_spatial` has higher ROC-AUC (0.4666 vs 0.4499), higher PR-AUC (0.0939 vs 0.0894), lower Brier (0.0970 vs 0.1035), and lower ECE (0.0638 vs 0.0736). Top-10 capture is tied at 0.0797. Top-20 capture is tied at 0.1434. Both pooled PR-AUC values remain below 0.1004, and both ROC-AUC values remain below 0.50.

Per-lot PR-AUC:

| Lot | Prevalence | yi_ml_v3_spatial | yi_ml_v4 |
| --- | ---: | ---: | ---: |
| L001 | 0.066 | 0.0735 | 0.0691 |
| L002 | 0.098 | 0.1587 | 0.1089 |
| L003 | 0.076 | 0.0926 | 0.0906 |
| L004 | 0.194 | 0.2002 | 0.1849 |
| L005 | 0.068 | 0.0919 | 0.0733 |

Per-lot ROC-AUC:

| Lot | yi_ml_v3_spatial | yi_ml_v4 |
| --- | ---: | ---: |
| L001 | 0.5176 | 0.5100 |
| L002 | 0.5952 | 0.5089 |
| L003 | 0.5758 | 0.5611 |
| L004 | 0.5238 | 0.4691 |
| L005 | 0.5996 | 0.5170 |

`yi_ml_v3_spatial` ranks above `yi_ml_v4` on every lot’s ROC-AUC and on every lot’s PR-AUC. Its L002 PR-AUC of 0.1587 is the strongest single-lot ranking result among these three models. That gain is not matched on L003 or L004, so it does not justify promotion either.

## 9. Interpretation

1. Pooled ranking does not improve. ROC-AUC moves from 0.4592 to 0.4499, farther from 0.50. PR-AUC moves from 0.0909 to 0.0894, farther from the 0.1004 prevalence.
2. Held-out generalization does not improve. PR-AUC is lower than `yi_ml_v2` on L001, L002, L003, L004, and L005.
3. The feature does not capture L004. L004 is the lot where a within-lot time pattern would have to show up, and there ROC-AUC falls below 0.50 and PR-AUC falls below the lot failure rate.
4. Calibration does not improve. Brier rises from 0.1006 to 0.1035. ECE rises from 0.0673 to 0.0736. Both Brier scores are worse than the constant Brier of 0.0903.
5. Top-10 capture rises only from 0.0757 to 0.0797, still below a random 0.10. Top-20 capture falls from 0.1474 to 0.1434, still below a random 0.20.
6. The change is not a consistent gain and not a single-lot win. The small ROC gains are on L001 and L005. L002, L003, and L004 get worse ROC-AUC, and every lot gets worse PR-AUC.
7. `yi_ml_v4` is not better than the constant-prevalence baseline on PR-AUC, Brier, or ROC-AUC.

## 10. Support decision

`NEEDS_MORE_DATA`.

The fail-closed rule requires pooled PR-AUC above 0.1004, pooled ROC-AUC above 0.50, pooled Brier below 0.0903, and at least three held-out lots with PR-AUC above that lot’s failure rate and ROC-AUC above 0.55. `yi_ml_v4` misses the pooled checks. Findings that depend on this model must not be called ML-supported.

Lifecycle remains CANDIDATE. Do not validate or activate it. `yi_ml_v1` remains the active model.

## 11. Recommended next experiment

Do not add another transform of the same timestamp, and do not add the eight rejected parametric measurements. Do not switch model family to chase a higher score.

A later candidate, started only as a separate experiment, should stay logistic regression under the same leave-one-lot-out protocol and should be scored against the constant-rate references before any lifecycle step. It should be kept only if pooled PR-AUC, ROC-AUC, and Brier beat those references and the gain holds on at least three held-out lots, including a lot other than L002. Until that happens, ML support stays `NEEDS_MORE_DATA`.
