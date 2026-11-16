# Model architecture review (evaluation only)

**Active model unchanged:** Logistic Regression / `yi_ml_v1`.

**Decision:** `KEEP_LOGISTIC`

**Recommended architecture (not activated):** `logistic`

This document does not replace the active artifact, does not retrain `yi_ml_v1`, and does not authorize production.

## Dataset

- samples: 784
- positives: 207 (rate 0.264)
- lots: 8 (leave-one-lot-out; **n_lots = 8**)
- features: 16 (Phase 7 contract; no lot/wafer/die IDs, no hidden labels)
- same LOLO folds for every model: `True`

## Models

Evaluated: logistic, random_forest, hist_gbm, xgboost, lightgbm

Unavailable / NOT_EVALUATED:

```json
{
  "catboost": {
    "status": "NOT_EVALUATED",
    "reason": "unavailable_due_to_environment",
    "detail": "unavailable_due_to_environment:ModuleNotFoundError"
  }
}
```

Do not read unavailability as inferiority.

## Raw LOLO OOF (S02)

These columns are **raw**. Do not compare them to another model's calibrated scores.

| Model | ROC-AUC | PR-AUC | F1 | Recall | Brier | ECE | Top-10 | Top-20 | PR-AUC lot mean (SD) |
|---|---|---|---|---|---|---|---|---|---|
| logistic | 0.733 | 0.456 | 0.526 | 0.643 | 0.205 | 0.183 | 0.193 | 0.382 | 0.500 (0.066) |
| random_forest | 0.764 | 0.446 | 0.630 | 0.797 | 0.176 | 0.133 | 0.174 | 0.333 | 0.491 (0.089) |
| hist_gbm | 0.751 | 0.462 | 0.603 | 0.768 | 0.194 | 0.154 | 0.184 | 0.357 | 0.524 (0.074) |
| xgboost | 0.752 | 0.449 | 0.601 | 0.787 | 0.197 | 0.169 | 0.164 | 0.353 | 0.494 (0.079) |
| lightgbm | 0.752 | 0.447 | 0.608 | 0.783 | 0.195 | 0.169 | 0.184 | 0.348 | 0.493 (0.078) |

Calibrated Brier / log loss / ECE live in `evaluation/results/model_architecture_review.json` under `calibration_analysis`. Calibration quality is a separate dimension from discrimination.

## Lot stability and paired fold differences

Stability uses per-held-out-lot metrics (mean, SD, min, max). A single pooled metric is not the stability conclusion.

- logistic − random_forest PR-AUC: mean 0.009 (SD 0.062); 2 folds logistic better, 6 folds random_forest better (n_folds=8).
- logistic − hist_gbm PR-AUC: mean -0.024 (SD 0.047); 2 folds logistic better, 6 folds hist_gbm better (n_folds=8).
- logistic − xgboost PR-AUC: mean 0.006 (SD 0.042); 3 folds logistic better, 5 folds xgboost better (n_folds=8).
- logistic − lightgbm PR-AUC: mean 0.007 (SD 0.038); 4 folds logistic better, 4 folds lightgbm better (n_folds=8).

## Feature importance stability

Permutation importance is computed independently on each LOLO held-out lot. This is predictive association only — not a root cause and not causal evidence.

- `logistic`: radial_distance (rank mean 1.000, top-5 folds 8/8), edge_distance (rank mean 2.000, top-5 folds 8/8), spatial_region (rank mean 4.875, top-5 folds 6/8), site (rank mean 5.000, top-5 folds 6/8), die_x (rank mean 6.625, top-5 folds 3/8). Importance ranks move across lots. Predictive association only, not causal.
- `random_forest`: radial_distance (rank mean 2.625, top-5 folds 7/8), edge_distance (rank mean 4.125, top-5 folds 5/8), normalized_y (rank mean 4.875, top-5 folds 5/8), die_y (rank mean 6.000, top-5 folds 4/8), spatial_region (rank mean 6.500, top-5 folds 3/8). Importance ranks move across lots. Predictive association only, not causal.
- `hist_gbm`: radial_distance (rank mean 1.000, top-5 folds 8/8), die_y (rank mean 4.125, top-5 folds 5/8), tester_id (rank mean 5.625, top-5 folds 6/8), die_x (rank mean 6.125, top-5 folds 3/8), tester_fail_rate (rank mean 7.625, top-5 folds 4/8). Importance ranks move across lots. Predictive association only, not causal.
- `xgboost`: radial_distance (rank mean 1.000, top-5 folds 8/8), edge_distance (rank mean 3.875, top-5 folds 7/8), die_y (rank mean 4.375, top-5 folds 6/8), spatial_region (rank mean 6.500, top-5 folds 4/8), normalized_x (rank mean 7.625, top-5 folds 1/8). Importance ranks move across lots. Predictive association only, not causal.
- `lightgbm`: radial_distance (rank mean 1.000, top-5 folds 8/8), die_y (rank mean 3.250, top-5 folds 7/8), die_x (rank mean 5.375, top-5 folds 5/8), edge_distance (rank mean 5.875, top-5 folds 5/8), tester_id (rank mean 6.375, top-5 folds 5/8). Importance ranks move across lots. Predictive association only, not causal.

## Decision rationale

- n_lots = 8. Conclusions are preliminary; do not overclaim significance.
- Comparisons use raw LOLO OOF. Calibrated metrics are a separate probability-quality dimension and are never mixed with another model's raw scores.
- Selection is not based on a single metric (ROC-AUC, F1, recall, or PR-AUC alone).
- Libraries that were unavailable were not scored. Status is NOT_EVALUATED, not inferior.
- No alternative beat logistic PR-AUC by more than close_tolerance while also matching diagnostic capture and lot stability.
- Logistic PR-AUC=0.456, top-10 capture=0.193, top-20 capture=0.382.
- When differences are within close tolerance, prefer the simpler, better-calibrated, easier-to-explain architecture.

n_lots = 8. Do not overclaim significance.

## Scenario policies

- S01 no invented hypothesis: True
- S09 no limit verbs: True
- S11 no sequence / later-test features: True
- S12 no lot_id feature: True
- S13 no wafer_id feature: True
- S15 EDGE and DRIFT remain separate (no EDGE_AND_DRIFT): True
- S16 no forced hypothesis: True

S12/S13 remain weak: on this bakeoff, logistic PR-AUC was 0.164 (S12) and 0.128 (S13), with top-10% capture 0.016 and 0.049. That is a feature-contract limitation (no lot_id/wafer_id memorization), not something to fix by identity features.

## Safety

- production_authorized: false
- production_action: FORBIDDEN
- safety_eligible_production_count: 0
- safety_eligible_production_rate: 0.0
- active artifact SHA-256 unchanged: True
- invoked_agents: []
- retrained_active: false

## Limitations

- ML output is a predictive association for first-pass failure. It is not a confirmed root cause, not a causal effect, not a predicted FPY gain, and not a production authorization.
- n_lots=8. Paired differences are preliminary.
- CatBoost was not evaluated if unavailable; that is NOT_EVALUATED, not an inferiority claim.
- Permutation importance is predictive association only and is not a causal effect or root cause.
- Top-k capture is diagnostic concentration, not recovered yield.
- Calibrated metrics are never compared against another model's raw metrics.
- S12/S13 weakness, if present, is a feature-contract limitation (no lot_id/wafer_id memorization), not an architecture defect to 'fix'.
- S11 cannot use later-test or sequence indices; censoring limitations are preserved.
