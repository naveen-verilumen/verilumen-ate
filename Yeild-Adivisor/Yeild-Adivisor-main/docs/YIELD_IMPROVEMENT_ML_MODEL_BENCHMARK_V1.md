# ML Model Benchmark v1

Experimental comparison of model families on the existing V2 dataset. No model is promoted. `yi_ml_v1` stays ACTIVE. Every benchmark model is a CANDIDATE stored only under `artifacts/ml/benchmark_v1/`.

Scores are predictive associations with first-pass failure. They are not a root cause and not a promised yield recovery. Production authorization remains false.

## 1. Objective

Determine whether a different model family, on the same validated feature contract and the same leave-one-lot-out folds, produces generalizable first-pass-failure evidence. This is an architecture comparison. It is not a feature search and not a hyperparameter search.

## 2. Dataset

`data/synthetic/agent_visible/yi_synthetic_v2/` was not regenerated.

5 lots, 25 wafers, 2,500 dies, 2,500 first-pass observations, 251 first-pass failures, 2,249 first-pass passes. Target `first_pass_fail`. Physical identity is `(lot_id, wafer_id, die_id)`.

Positive-class prevalence is 251 / 2500 = 0.1004. Constant PR-AUC is 0.1004. Constant Brier is 0.0903. ROC-AUC is compared with 0.50. A random ranking captures about 10% of failures in the top 10% of scores and about 20% in the top 20%.

## 3. Leakage controls

Tabular models use the 16-column V2 contract only. They do not use `first_pass_fail`, `pass_fail`, failure codes, primary failure, retest outcome, sequence outcome, `sbin`, scenario, or ground-truth fields. The eight parametric measurements are not included.

Preprocessing, scaling, one-hot encoding, training-fold fail rates, and isotonic calibration are fit inside each training fold. Held-out lot labels are not used to fit them.

The GRU audit is in section 10. It was not trained.

## 4. Validation design

Leave-one-lot-out. Same five folds for every model. No random split.

| Held-out lot | Train dies | Test dies | Test fails | Prevalence |
| --- | ---: | ---: | ---: | ---: |
| L001 | 2,000 | 500 | 33 | 0.066 |
| L002 | 2,000 | 500 | 49 | 0.098 |
| L003 | 2,000 | 500 | 38 | 0.076 |
| L004 | 2,000 | 500 | 97 | 0.194 |
| L005 | 2,000 | 500 | 34 | 0.068 |

Each test lot is absent from that fold's training lots. Seed is 7. Decision threshold 0.5 was not tuned on the test lot.

## 5. Model configurations

Modest fixed settings. No search after seeing scores.

| Model | Configuration |
| --- | --- |
| Logistic regression | `class_weight=balanced`, `max_iter=400`, solver `lbfgs` |
| Random forest | 40 trees, `max_depth=8`, `min_samples_leaf=8`, `class_weight=balanced` |
| Extra trees | Same size budget as random forest |
| HistGradientBoosting | `max_depth=4`, `learning_rate=0.08`, `max_iter=50`, `min_samples_leaf=12`, balanced sample weight |
| XGBoost | 50 trees, `max_depth=4`, `learning_rate=0.08`, subsample 0.9, training-fold `scale_pos_weight` |
| LightGBM | 50 trees, `max_depth=4`, `learning_rate=0.08`, training-fold `scale_pos_weight` |
| MLP | One hidden layer of 16 ReLU units, Adam, `max_iter=80`, L2 `1e-4`, batch 64, no early stopping, fold-local scaling, balanced sample weight |
| GRU | Not configured. See section 10 |

The MLP hit the 80-iteration cap on every fold. The cap was not raised.

## 6. Feature contract

`die_x`, `die_y`, `normalized_x`, `normalized_y`, `radial_distance`, `edge_distance`, `spatial_region`, `timestamp_epoch`, `temperature_c`, `voltage_v`, `site`, `tester_id`, `probe_card_id`, `prober_id`, `tester_fail_rate`, `probe_fail_rate`.

`spatial_region` remains the radius categories used by `yi_ml_v2`. `relative_position_within_lot` is not in this benchmark. Parametric columns are not in this benchmark.

## 7. Pooled results

Calibrated out-of-fold scores. Threshold metrics use 0.5.

| Model | ROC-AUC | PR-AUC | Precision | Recall | F1 | Balanced accuracy | Brier | Log loss | ECE | Top-10 | Top-20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic | 0.4592 | 0.0909 | 0.1053 | 0.0239 | 0.0390 | 0.5006 | 0.1006 | 0.3744 | 0.0673 | 0.0757 | 0.1474 |
| Random forest | 0.4751 | 0.0936 | 0.0860 | 0.0956 | 0.0906 | 0.4911 | 0.1637 | 1.1239 | 0.1890 | 0.0797 | 0.1673 |
| Extra trees | 0.4741 | 0.0965 | 0.0880 | 0.0876 | 0.0878 | 0.4931 | 0.1319 | 0.9619 | 0.1423 | 0.0876 | 0.1753 |
| HistGradientBoosting | 0.4550 | 0.0900 | 0.0735 | 0.0996 | 0.0846 | 0.4798 | 0.1533 | 0.9678 | 0.1758 | 0.0717 | 0.1554 |
| XGBoost | 0.4594 | 0.0898 | 0.0619 | 0.0717 | 0.0664 | 0.4752 | 0.1646 | 1.0452 | 0.1883 | 0.0598 | 0.1315 |
| LightGBM | 0.4677 | 0.0906 | 0.0616 | 0.0876 | 0.0724 | 0.4693 | 0.1662 | 0.9714 | 0.1998 | 0.0598 | 0.1275 |
| MLP | 0.4618 | 0.0916 | 0.0843 | 0.0837 | 0.0840 | 0.4911 | 0.1479 | 0.9950 | 0.1419 | 0.0837 | 0.1355 |
| Constant | 0.50 | 0.1004 | — | — | — | 0.50 | 0.0903 | — | — | ~0.10 | ~0.20 |

Every calibrated ROC-AUC is below 0.50. Every calibrated PR-AUC is below the 0.1004 prevalence. Every Brier score is above 0.0903. Every top-10 capture is below 0.10 and every top-20 capture is below 0.20.

Raw scores, before isotonic calibration:

| Model | ROC-AUC | PR-AUC | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| Logistic | 0.4964 | 0.1012 | 0.2731 | 0.4098 |
| Random forest | 0.4750 | 0.0923 | 0.1993 | 0.2781 |
| Extra trees | 0.4663 | 0.0967 | 0.2156 | 0.3276 |
| HistGradientBoosting | 0.4664 | 0.0910 | 0.2524 | 0.3435 |
| XGBoost | 0.4729 | 0.0912 | 0.2530 | 0.3367 |
| LightGBM | 0.4723 | 0.0909 | 0.2473 | 0.3183 |
| MLP | 0.4683 | 0.0967 | 0.2755 | 0.3770 |

Logistic raw PR-AUC is 0.1012, just above 0.1004, with raw ROC-AUC still below 0.50 and raw Brier 0.2731. After fold-local calibration its PR-AUC falls to 0.0909. That raw edge is not treated as evidence.

## 8. Per-lot results

Calibrated scores. Prevalence is the constant PR-AUC for that lot. Weak lots are included.

| Model | Lot | ROC-AUC | PR-AUC | Recall | Precision | F1 | Brier | Top-10 | Top-20 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic | L001 | 0.4718 | 0.0711 | 0.0000 | 0.0000 | 0.0000 | 0.0629 | 0.0606 | 0.1212 |
| Logistic | L002 | 0.5566 | 0.1256 | 0.0000 | 0.0000 | 0.0000 | 0.0885 | 0.2041 | 0.3061 |
| Logistic | L003 | 0.5820 | 0.1055 | 0.0000 | 0.0000 | 0.0000 | 0.0703 | 0.0789 | 0.2368 |
| Logistic | L004 | 0.5161 | 0.2022 | 0.0000 | 0.0000 | 0.0000 | 0.1713 | 0.0825 | 0.1856 |
| Logistic | L005 | 0.5124 | 0.0750 | 0.1765 | 0.1053 | 0.1319 | 0.1099 | 0.1471 | 0.1765 |
| Random forest | L001 | 0.4540 | 0.0628 | 0.0606 | 0.0870 | 0.0714 | 0.0895 | 0.0606 | 0.1515 |
| Random forest | L002 | 0.5371 | 0.1216 | 0.0612 | 0.3333 | 0.1034 | 0.0984 | 0.1429 | 0.2857 |
| Random forest | L003 | 0.4984 | 0.0944 | 0.0526 | 0.1111 | 0.0714 | 0.0884 | 0.2105 | 0.2368 |
| Random forest | L004 | 0.5158 | 0.2084 | 0.0412 | 0.1667 | 0.0661 | 0.1949 | 0.0928 | 0.2371 |
| Random forest | L005 | 0.4977 | 0.0652 | 0.3824 | 0.0634 | 0.1088 | 0.3474 | 0.0588 | 0.1471 |
| Extra trees | L001 | 0.4569 | 0.0608 | 0.0000 | 0.0000 | 0.0000 | 0.0865 | 0.0000 | 0.1212 |
| Extra trees | L002 | 0.5574 | 0.1177 | 0.0408 | 0.1538 | 0.0645 | 0.1026 | 0.1020 | 0.2653 |
| Extra trees | L003 | 0.4564 | 0.0736 | 0.0789 | 0.0714 | 0.0750 | 0.1021 | 0.0789 | 0.1579 |
| Extra trees | L004 | 0.5004 | 0.1880 | 0.0206 | 0.1429 | 0.0360 | 0.1929 | 0.0722 | 0.1959 |
| Extra trees | L005 | 0.5892 | 0.0942 | 0.4412 | 0.0962 | 0.1579 | 0.1753 | 0.2059 | 0.3235 |
| HistGradientBoosting | L001 | 0.4953 | 0.0820 | 0.0606 | 0.2222 | 0.0952 | 0.0778 | 0.1515 | 0.1515 |
| HistGradientBoosting | L002 | 0.5875 | 0.1272 | 0.0000 | 0.0000 | 0.0000 | 0.0953 | 0.1633 | 0.2653 |
| HistGradientBoosting | L003 | 0.5462 | 0.0966 | 0.0000 | 0.0000 | 0.0000 | 0.0763 | 0.1316 | 0.3158 |
| HistGradientBoosting | L004 | 0.4938 | 0.1879 | 0.0309 | 0.1579 | 0.0517 | 0.1964 | 0.0825 | 0.1753 |
| HistGradientBoosting | L005 | 0.4813 | 0.0690 | 0.5882 | 0.0645 | 0.1163 | 0.3206 | 0.1176 | 0.2647 |
| XGBoost | L001 | 0.4846 | 0.0711 | 0.0606 | 0.1250 | 0.0816 | 0.0783 | 0.0909 | 0.1515 |
| XGBoost | L002 | 0.6051 | 0.1307 | 0.0204 | 0.2000 | 0.0370 | 0.0960 | 0.1429 | 0.3265 |
| XGBoost | L003 | 0.5186 | 0.1008 | 0.0000 | 0.0000 | 0.0000 | 0.0771 | 0.1579 | 0.2632 |
| XGBoost | L004 | 0.4872 | 0.1875 | 0.0000 | 0.0000 | 0.0000 | 0.1988 | 0.0928 | 0.1959 |
| XGBoost | L005 | 0.4628 | 0.0652 | 0.4412 | 0.0591 | 0.1042 | 0.3730 | 0.0588 | 0.1471 |
| LightGBM | L001 | 0.4669 | 0.0910 | 0.0303 | 0.3333 | 0.0556 | 0.0783 | 0.0606 | 0.1818 |
| LightGBM | L002 | 0.6031 | 0.1241 | 0.0000 | 0.0000 | 0.0000 | 0.0973 | 0.1429 | 0.3061 |
| LightGBM | L003 | 0.5198 | 0.0949 | 0.0000 | 0.0000 | 0.0000 | 0.0755 | 0.1579 | 0.2368 |
| LightGBM | L004 | 0.4953 | 0.1878 | 0.0000 | 0.0000 | 0.0000 | 0.2014 | 0.0619 | 0.2268 |
| LightGBM | L005 | 0.4821 | 0.0692 | 0.6176 | 0.0633 | 0.1148 | 0.3785 | 0.1471 | 0.2059 |
| MLP | L001 | 0.5053 | 0.0766 | 0.0000 | 0.0000 | 0.0000 | 0.0641 | 0.1515 | 0.2727 |
| MLP | L002 | 0.5834 | 0.1418 | 0.0000 | 0.0000 | 0.0000 | 0.0883 | 0.2245 | 0.3469 |
| MLP | L003 | 0.4976 | 0.0880 | 0.0000 | 0.0000 | 0.0000 | 0.0798 | 0.1842 | 0.2105 |
| MLP | L004 | 0.4303 | 0.1718 | 0.0000 | 0.0000 | 0.0000 | 0.1813 | 0.0619 | 0.1340 |
| MLP | L005 | 0.5724 | 0.0793 | 0.6176 | 0.0857 | 0.1505 | 0.3259 | 0.0588 | 0.2353 |

L002 is where ROC-AUC most often exceeds 0.55. L004, the lot with 97 failures, stays near or below 0.50 for every model except logistic (0.5161) and random forest (0.5158). The MLP's L004 ROC-AUC is 0.4303 and its L004 PR-AUC 0.1718 is below that lot's 0.194 failure rate.

## 9. Calibration results

Isotonic regression is fit on each fold's training-lot raw scores only, then applied to that fold's held-out lot. Held-out labels are not used.

Calibration lowers Brier relative to the raw scores for every model. It does not bring any model below the constant Brier of 0.0903. Logistic remains the least poorly calibrated: calibrated Brier 0.1006 and ECE 0.0673. The other families land at calibrated Brier 0.1319–0.1662 and ECE 0.1419–0.1998.

Per-lot Brier shows the same split. On L005 the constant Brier is about 0.063. Logistic's calibrated Brier there is 0.1099. Random forest, boosting, and the MLP are between 0.1753 and 0.3785. A higher recall at 0.5 on L005 for those models comes with probabilities that are far too high.

## 10. Model availability

| Model | Status | Dependency change |
| --- | --- | --- |
| Logistic, random forest, extra trees, HistGradientBoosting, MLP | EVALUATED | None. scikit-learn already installed |
| XGBoost | EVALUATED | None. Import succeeded. No package was added |
| LightGBM | EVALUATED | None. Import succeeded. No package was added |
| GRU | BLOCKED_LEAKAGE_RISK | Not trained |

No model is UNAVAILABLE.

The GRU was not given artificial inputs. First-pass rows contain the ten slots in order:

T001 CONTINUITY, T002 OPENS, T003 SHORTS, T004 CONTACT, T005 IDDQ, T006 VMIN, T007 VMAX, T008 LEAKAGE, T009 FUNCTIONAL, T010 SCAN.

2,500 first-pass attempts match that order. Retest rows were excluded from the audit (more than zero retest rows exist). The step columns are identity, `test_id`, `sequence_index`, a timestamp repeated on every step, and the outcome fields `test_pass_fail`, `pass_fail`, `failure_code`, and `is_first_fail`. There is no per-step measurement column. On all 2,500 first-pass dies, "any test slot is FAIL" matches the attempt FAIL flag, so a sequence of those outcomes is the target. Parametric measurements were not substituted. Status is `BLOCKED_LEAKAGE_RISK`.

## 11. Interpretation

No family is selected.

- Ranking: no calibrated model beats ROC-AUC 0.50 or PR-AUC 0.1004 on the pooled out-of-fold scores.
- Generalization: the fail-closed rule needs pooled PR-AUC, ROC-AUC, and Brier to beat the constant references, and at least three held-out lots with PR-AUC above that lot's failure rate and ROC-AUC above 0.55. None do.
- L002 accounts for most of the ROC-AUC values above 0.55. That single-lot lift is not enough.
- L004 is not recovered by a more flexible model. The MLP is worse there than logistic regression.
- Calibration: logistic is the only model close to the constant Brier, and it is still worse than that constant. The other families are overconfident after calibration.
- Top-10 and top-20 capture stay below a random ranking on the pooled scores.
- Lot-to-lot ROC-AUC moves by more than 0.10 inside several families. XGBoost is 0.6051 on L002 and 0.4628 on L005.
- Leakage risk for the tabular contract is controlled. GRU could not be built without the label.
- Compute: logistic trained in 0.33s, LightGBM in 0.48s, XGBoost in 0.96s, extra trees in 1.10s, random forest in 1.65s, HistGradientBoosting in 3.52s, and the MLP in 12.03s without converging. Extra training time did not produce reliable evidence.

All seven evaluated models have `ml_support_status` `NEEDS_MORE_DATA`. None is a sufficient ML evidence layer.

The logistic numbers match the persisted `yi_ml_v2` calibrated baseline. This run did not overwrite that artifact.

## 12. Limitations

- Five held-out lots is a small comparison.
- Threshold 0.5 was not tuned. Precision, recall, and F1 describe that fixed cut only.
- The MLP stopped at 80 iterations. Raising that cap would be a new experiment.
- Tree and boosting settings are the existing modest budgets, not an optimized search.
- GRU has no leakage-free sequence in the current test table.
- This benchmark does not add spatial BORDER/INNER, lot-relative time, or parametric measurements. Those feature questions were already evaluated separately and are not reopened here.

## 13. Recommended next experiment

Do not promote any benchmark model. Do not replace `yi_ml_v1`. Do not train a larger network, and do not train a GRU until the test table contains a per-step measurement that is not the outcome.

The gap is generalizable signal under leave-one-lot-out, not the choice among these families. A later candidate should stay logistic regression on a leakage-audited feature, and it should be kept only if calibrated PR-AUC, ROC-AUC, and Brier beat the constant references on the pooled scores and the gain holds on at least three held-out lots, including a lot other than L002. Until then, ML support stays `NEEDS_MORE_DATA`.
