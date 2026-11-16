# Phase 8 — ML monitoring, calibration drift, and model health

**Status:** Implemented. Advisory only. Never retrains. Never authorizes production.

Companion: `docs/PHASE_7_ML_INTELLIGENCE.md`. Config: `configs/monitoring.yaml` (`status: TO_BE_CALIBRATED`).

```text
persisted Phase 7 model + immutable reference snapshot
        → new lot features (allowlist validated)
        → score with persisted artifact (no fit)
        → feature / prediction / target / calibration / performance / data quality
        → deterministic health state
        → ModelHealthReport
        → optional ML evidence trust flag
```

Statistical detectors stay available when ML is flagged.

## 1. Objective

Decide whether the persisted first-pass-failure model still behaves reliably on new lots. Output is `ModelHealthReport`, not a new model.

## 2. Architecture

Independent dimensions, then a documented rule. There is no single `model_health_score`.

## 3. Reference population

Built once from the training/reference directory (S02 agent-visible data for the current artifact) by **scoring** the persisted model. Stored at `artifacts/ml/yi_ml_v1/reference.json` with `immutable: true`. Current lots never redefine that baseline.

Includes model/feature/calibration versions, lot ids, training period, feature statistics, prediction statistics, target rate, and reference metrics.

## 4–8. Dimensions

| Dimension | Unlabeled | Method |
|---|---|---|
| feature_drift | yes | PSI + KS (numeric); frequency L1 + unseen-category rate (categorical) |
| prediction_drift | yes | mean/median/quantiles, positive rate, PSI, KS |
| target_drift | labels required | absolute and relative first-pass fail-rate delta |
| calibration | labels required | Brier, ECE, reliability bins (`insufficient_sample_size` when n is small) |
| performance | labels required | ROC-AUC, PR-AUC, precision, recall, F1, Brier, top-10/20% capture vs reference |
| data_quality | yes | missing expected features, unexpected columns, duplicates, missingness, unseen categories |

PSI/KS cutoffs live in YAML and are **TO_BE_CALIBRATED**, not universal.

Prediction drift means “the model is seeing a different score distribution,” not failure and not root cause.

## 9. Health states

`HEALTHY`, `MONITOR`, `REVIEW`, `DEGRADED`, `NEEDS_RETRAINING`, `INSUFFICIENT_DATA`.

Policy (first match):

1. Critical data-quality → `REVIEW`
2. n < `min_current_samples` → `INSUFFICIENT_DATA`
3. Severe performance → `DEGRADED` (or `NEEDS_RETRAINING` if also multi-signal)
4. Severe calibration → `REVIEW`
5. ≥3 labeled drift dimensions → `NEEDS_RETRAINING` (advisory)
6. ≥3 features at REVIEW → `MONITOR`
7. Any REVIEW dimension → `REVIEW`
8. Any MONITOR dimension → `MONITOR`
9. Else `HEALTHY`

`NEEDS_RETRAINING` only recommends considering retraining. The code path never calls `select_and_train`.

## 10. Recommendations (advisory)

`CONTINUE_MONITORING`, `REVIEW_MODEL`, `COLLECT_MORE_DATA`, `INVESTIGATE_DRIFT`, `CONSIDER_RETRAINING`.

Forbidden: deploy/replace model automatically, change limits/recipes/ATE/equipment.

## 11. Unlabeled vs labeled

Unlabeled: target/calibration/performance = `UNAVAILABLE`. Labels are never fabricated.

## 12. Lot and time

Lot summaries (n, mean prediction, fail rate). Temporal series by lot timestamp when timestamps exist; otherwise `temporal_available=false`.

## 13. Synthetic monitoring scenarios

Separate from Phase 2 S01–S16. Agent-visible: `data/synthetic/monitoring/agent_visible/ds_mon_XX`. Hidden GT: `evaluation/ground_truth/monitoring/`.

| ID | Injection |
|---|---|
| M01 | no drift (copy of reference-like S02) |
| M02 | temperature/voltage shift; labels unchanged |
| M03 | expanded coordinates (prediction shift) |
| M04 | extra fails; features unchanged |
| M05 | extra fails on original spatial pattern (calibration vs ranking) |
| M06 | shuffled labels (performance collapse) |
| M07 | combined feature + spatial + target |
| M08 | missing feature, unexpected column, duplicates |
| M09 | 24 rows |
| M10 | outcome columns removed |

## 14. Holdout results

Binary alarm (non-HEALTHY / non-INSUFFICIENT_DATA, except M09): **TP=7, FP=0, TN=3, FN=0**.

| Scenario | Predicted | Feature | Pred. | Target | Cal | Perf | DQ |
|---|---|---|---|---|---|---|---|
| M01 no drift | HEALTHY | HEALTHY | HEALTHY | HEALTHY | HEALTHY | HEALTHY | HEALTHY |
| M02 feature | REVIEW | REVIEW | HEALTHY | HEALTHY | HEALTHY | HEALTHY | HEALTHY |
| M03 prediction | NEEDS_RETRAINING | REVIEW | REVIEW | HEALTHY | REVIEW | DEGRADED | HEALTHY |
| M04 target | DEGRADED | HEALTHY | HEALTHY | REVIEW | REVIEW | DEGRADED | HEALTHY |
| M05 calibration | DEGRADED | HEALTHY | HEALTHY | REVIEW | REVIEW | DEGRADED | HEALTHY |
| M06 performance | DEGRADED | HEALTHY | HEALTHY | HEALTHY | REVIEW | DEGRADED | HEALTHY |
| M07 multiple | NEEDS_RETRAINING | REVIEW | REVIEW | REVIEW | REVIEW | DEGRADED | HEALTHY |
| M08 schema | REVIEW | INSUFFICIENT_DATA | HEALTHY | HEALTHY | HEALTHY | HEALTHY | REVIEW |
| M09 small n | INSUFFICIENT_DATA | REVIEW | INSUFF. | INSUFF. | INSUFF. | INSUFF. | HEALTHY |
| M10 no labels | HEALTHY | HEALTHY | HEALTHY | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | HEALTHY |

M02 is the required counterexample: feature drift without treating the model as failed. M06 is the converse: performance collapse without feature drift. M10 does not fabricate labels. M09 is not HEALTHY and not NEEDS_RETRAINING.

## 15. ML evidence degradation

`compose(..., model_health_status=...)` sets `trust=REDUCED` and `ml=ML_FLAGGED` for `DEGRADED` / `NEEDS_RETRAINING` / `INSUFFICIENT_DATA`. Evidence is not deleted. Statistical hypotheses remain.

## 16. Safety

Every report: `production_action=FORBIDDEN`, `production_authorized=false`, production eligibility 0, `retrained=false`, `model_replaced=false`.

## 17. CLI

```text
python -m yield_improvement generate --monitoring
python -m yield_improvement monitor <current_dir> --reference <reference_dir>
python -m yield_improvement monitor-report <current_dir> --reference <reference_dir>
```

Outputs: `evaluation/monitoring/<dataset_id>_model_health.json` and `.md`.

## 18. Limitations

- YAML thresholds are initial and TO_BE_CALIBRATED.
- Nested lot-specific calibration of the Phase 7 model is out of scope; monitoring scores the deployed artifact.
- Concatenated lot summaries can still be dominated by a large lot; per-lot rows are reported to surface that.
- Holdout scenarios are controlled transforms of S02, not a second generator family.

## 19. Future (not implemented)

Phase 9 is not started. A later operator workflow could schedule **manual** retraining after `CONSIDER_RETRAINING`, with a new versioned artifact and a new frozen reference.
