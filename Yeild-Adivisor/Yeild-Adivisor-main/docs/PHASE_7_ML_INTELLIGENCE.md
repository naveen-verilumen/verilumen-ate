# Phase 7 — ML intelligence layer

**Status:** Implemented. First-pass-failure **prediction** only. Not causal. Not a root cause. Not a production authorization.

Companion: `docs/PHASE_6_VALIDATION_ENGINE.md`. Config: `configs/ml.yaml`, `configs/ml_feature_allowlist.yaml`.

ML is an additional evidence source. It does not replace Phase 1 FPY, Phase 3 detectors, Phase 4 ranking, Phase 5 opportunity, or Phase 6 safety.

```text
canonical data → Phase 1 FPY target
        → feature builder (train-fit only)
        → group-aware CV (leave-one-lot-out)
        → model comparison (logistic / RF / HistGBM)
        → OOF P(first-pass fail)
        → permutation importance
        → ML evidence (SECONDARY_SUPPORT)
        → existing hypothesis composer (attach only; no rescore)
        → opportunity / validation / reporting unchanged
```

CLI:

```text
python -m yield_improvement ml train    <agent_visible_dir>
python -m yield_improvement ml predict  <agent_visible_dir>
python -m yield_improvement ml evaluate <agent_visible_dir>
python -m yield_improvement ml run      <agent_visible_dir>
```

`ml run` trains, writes `artifacts/ml/yi_ml_v1/`, and composes hypotheses with ML packets attached when a matching statistical hypothesis already exists.

---

## 1. Objective

Learn `P(first-pass failure | allowed pre-outcome features)` on Phase 1 eligible dies. Rank high-risk populations and name which **predictive** features matter. Those findings become `ML_PREDICTIVE_ASSOCIATION` evidence.

## 2. Target

`first_pass_fail` = 1 iff Phase 1 `first_pass_disposition == FAIL`. Retest recovery, final disposition, and hidden scenario labels are not targets and not features.

## 3. Features

Allowed source fields and derived names live in `configs/ml_feature_allowlist.yaml`. Derived groups:

- Spatial: `die_x/y`, normalized coordinates, radius, edge distance, `spatial_region` (train-only radius quantiles). Missing X/Y stay missing.
- Equipment/contact: `tester_id`, `probe_card_id`, `prober_id` as **categories** (one-hot, unknown ignored). Train-only group fail rates for tester/probe; a held-out lot’s unseen id gets the **training global mean**.
- Environment: temperature, voltage.
- Time: `timestamp_epoch` relative to the training minimum (drift proxy).
- Parametric: raw `IR_DROP_MV`, `THERMAL_C`, `SETUP_SLACK_PS`, `HOLD_SLACK_PS`, `TEST_TIME_MS` when present. No over-limit bit (that would copy the fail rule).

`lot_id` / `wafer_id` / `die_id` are grouping/identity keys, not model features (memorization).

## 4. Leakage prevention

Fail closed on hidden columns (`scenario_id`, `true_cause`, `injected_effect`, …). Outcome columns may exist on `die_attempts.csv` for FPY but are stripped before `FeatureBuilder`. Sequence indices and later-test results are not used (stop-on-fail censoring).

The `yield_improvement.ml` package does not import `evaluation/` and does not read `evaluation/ground_truth/`.

## 5. Split

Primary: **leave-one-lot-out** when lot count ≤ 12 (synthetic small profile = 8 lots). Otherwise `GroupKFold` by `lot_id`. A lot never appears in both train and test. Preprocessing and group rates are fit on the training lots of that fold only.

## 6–8. Models and selection

Candidates (sklearn): Logistic Regression (balanced), Random Forest (balanced), `HistGradientBoostingClassifier` (balanced sample weights). Categoricals are one-hot with `handle_unknown=ignore` — not ordinal integer codes.

Selection: highest OOF **PR-AUC**, then lower **Brier**, then simpler model if PR-AUC is within 0.02. Accuracy is not a selection metric.

## 9. Training

`select_and_train` runs OOF for every candidate, picks one, fits the selected pipeline on all lots for the artifact, and fits isotonic calibration on OOF raw probabilities (documented: not a second hidden test). Reported metrics use OOF predictions.

## 10. Metrics

ROC-AUC, PR-AUC, precision, recall, F1, balanced accuracy, Brier, log loss, `failure_capture_at_top_10_percent`, `failure_capture_at_top_20_percent`. The capture metrics are **diagnostic concentration**, not recovered yield.

## 11. Calibration

Isotonic regression. For reported OOF metrics, each held-out lot is calibrated using a calibrator fitted only on the other lots. The deployed artifact calibrator is then fit on all OOF scores for scoring new lots. `raw_probability` and `calibrated_probability` are both stored. If a fold calibrator cannot be fit, that fold uses raw probability.

## 12. Explainability

Permutation importance on the trained pipeline. SHAP is not required. Importance text is “predictive,” never “causes failure.”

## 13. ML evidence and hypothesis integration

`build_ml_evidence` maps top-importance features to taxonomy families and requires a fail-rate delta in the top 20% predicted-risk slice (`min_rate_delta` in `ml.yaml`). Role is always `SECONDARY_SUPPORT`. `independence=false` versus a statistical detector on the same family.

`compose(..., ml_evidence=...)` **attaches** matching packets onto existing hypotheses. It does **not**:

- add ML into `evidence_score`
- re-rank hypotheses
- create a hypothesis when no statistical SIGNAL exists

That last rule is how S16 stays “no confident hypothesis” even if the model outputs probabilities.

## 14–19. Scenario holdout (agent-visible data; hidden GT joined after prediction)

OOF leave-one-lot-out on 784 eligible dies per scenario (8 lots). Reported metrics use nested-calibrated OOF probabilities (each held-out lot is calibrated on the other lots). Accuracy is not a success metric. Status is **SUPPORTIVE / DIVERGENT / ABSENT / NO_FORCED_HYPOTHESIS**, never “root cause detected.”

Full machine-readable rows: `evaluation/results/ml_phase7.json`.

| Scenario | Expected | Status | Selected | ROC-AUC | PR-AUC | Top-10% capture | Top-20% capture | ML→hyp |
|---|---|---|---|---|---|---|---|---|
| S01 RANDOM | none | NO_FORCED_HYPOTHESIS | logistic | 0.483 | 0.141 | 0.093 | 0.252 | no |
| S02 EDGE | EDGE | SUPPORTIVE | logistic | 0.715 | 0.438 | 0.198 | 0.372 | yes |
| S03 CENTER | CENTER | SUPPORTIVE | random_forest | 0.781 | 0.511 | 0.220 | 0.407 | yes |
| S04 RING | RING | DIVERGENT | logistic | 0.715 | 0.404 | 0.203 | 0.471 | no |
| S05 EQUIPMENT | EQUIPMENT | SUPPORTIVE | logistic | 0.671 | 0.274 | 0.169 | 0.454 | yes |
| S06 DRIFT | DRIFT | SUPPORTIVE | logistic | 0.607 | 0.307 | 0.135 | 0.266 | yes |
| S07 TEMPERATURE | TEMPERATURE | SUPPORTIVE | random_forest | 0.709 | 0.358 | 0.122 | 0.306 | yes |
| S08 PARAMETRIC | PARAMETRIC | ABSENT | random_forest | 0.160 | 0.177 | 0.000 | 0.000 | no |
| S09 NEAR-LIMIT | LIMIT_SENSITIVITY | ABSENT | logistic | 0.450 | 0.504 | 0.080 | 0.181 | no |
| S10 CONTACT | CONTACT | SUPPORTIVE | logistic | 0.712 | 0.380 | 0.196 | 0.312 | yes |
| S11 SEQUENCE | SEQUENCE | DIVERGENT | logistic | 0.534 | 0.099 | 0.134 | 0.313 | no |
| S12 LOT | LOT_VARIATION | ABSENT | logistic | 0.429 | 0.138 | 0.041 | 0.090 | no |
| S13 WAFER | WAFER_VARIATION | ABSENT | logistic | 0.374 | 0.103 | 0.049 | 0.078 | no |
| S14 CORRELATED | CORRELATED | ABSENT | hist_gbm | 0.521 | 0.331 | 0.083 | 0.202 | no |
| S15 EDGE+DRIFT | EDGE (+ DRIFT) | SUPPORTIVE | hist_gbm | 0.713 | 0.500 | 0.153 | 0.349 | yes |
| S16 NO-SIGNAL | none | NO_FORCED_HYPOTHESIS | logistic | 0.400 | 0.073 | 0.056 | 0.127 | no |

**S09:** ML did not recommend limit changes. Phase 6 remains the safety gate.

**S11:** No sequence or later-test features. Stop-on-fail censoring is documented; later tests are not inferred.

**S15:** EDGE and DRIFT hypotheses remain separate. No `EDGE_AND_DRIFT` collapse.

**S16:** Predictions exist; no confident hypothesis was forced.

**False negatives / weak signal:** S08 parametric shift was not recovered (nested-calibrated ROC-AUC 0.16, worse than chance — a real limitation, not hidden). S04 RING was not mapped to RING. S12/S13 lot/wafer IDs are intentionally not features, so lot-level memorization is unavailable. Nested isotonic calibration is fold-local; concatenating lot-specific calibrated scores can degrade pooled ranking on weak-signal scenarios. Model *selection* uses raw OOF PR-AUC, not these calibrated pooled numbers.

**S02 reference metrics after nested calibration (persisted artifact):** n=784, n_positives=207, positive_rate=0.264, ROC-AUC=0.715, PR-AUC=0.438, precision=0.490, recall=0.362, F1=0.417, Brier=0.170, log_loss=0.528, balanced_accuracy=0.614, top-10% capture=0.198, top-20% capture=0.372. Top predictive features on the uncalibrated comparison still rank spatial radius/edge. Split: leave-one-lot-out. Feature count: 16. Average n_train≈686, n_test≈98.

S02 model comparison (raw OOF, selection metric = PR-AUC, prefer simpler if within 0.02):

| Model | ROC-AUC | PR-AUC | F1 | Recall | Brier | Top-10% | Top-20% |
|---|---|---|---|---|---|---|---|
| logistic (selected) | 0.733 | 0.456 | 0.526 | 0.643 | 0.205 | 0.193 | 0.382 |
| random_forest | 0.764 | 0.446 | 0.630 | 0.797 | 0.176 | 0.174 | 0.333 |
| hist_gbm | 0.751 | 0.462 | 0.603 | 0.768 | 0.194 | 0.184 | 0.357 |

HistGBM had a slightly higher PR-AUC; logistic was selected because it is within 0.02 and simpler. Nested-calibrated logistic OOF is what the artifact metrics.json reports.

## 20. Safety

MLResult and validation still have `production_action=FORBIDDEN`, `production_authorized=false`, `safety_eligible_production=0`. A large ML score cannot pass a failed Phase 6 data-quality/safety gate.

## 21. Artifacts

`artifacts/ml/yi_ml_v1/model.pkl`, `metadata.json`, `feature_list.json`, `metrics.json`. No scenario ids or hidden labels.

## 22. Reproducibility

`seed: 7` in `ml.yaml`. Same config + data → same OOF metrics within sklearn numerical tolerance.

## 23. Real-data readiness

The allowlist is agent-visible production fields only. Unknown/hidden columns fail closed. The pipeline does not require synthetic-only columns.

## 24. Next phase

Phase 8 (if any): operator monitoring of ML calibration drift on new lots, still without production writes. Do not turn predicted risk into ATE or limit actions.
