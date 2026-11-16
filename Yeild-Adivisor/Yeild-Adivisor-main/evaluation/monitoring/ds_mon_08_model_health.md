# Model health — ds_mon_08

Model health is advisory. It is not a production authorization, not a root cause, not a causal effect, and not an instruction to retrain or replace the model automatically.

- overall_status: **REVIEW**
- label_mode: LABELED
- model_version: yi_ml_v1
- feature_version: yi_ml_features_v1
- calibration_version: yi_ml_cal_v1
- reference_version: yi_ml_ref_v1
- reference_dataset_id: ds_0b5542c71e1a13e0
- lots/wafers/dies: 8 / 2 / 783
- recommendations: REVIEW_MODEL
- triggers: critical_data_quality
- production_authorized: False
- retrained: False

## Dimensions

| Dimension | Status | Availability |
|---|---|---|
| feature_drift | INSUFFICIENT_DATA | INSUFFICIENT_DATA |
| prediction_drift | HEALTHY | AVAILABLE |
| target_drift | HEALTHY | AVAILABLE |
| calibration | HEALTHY | AVAILABLE |
| performance | HEALTHY | AVAILABLE |
| data_quality | REVIEW | AVAILABLE |

Prediction drift is not model failure. Feature importance is not causal.

## Limitations

- Thresholds are TO_BE_CALIBRATED and are not universally valid.
- Prediction drift is not model failure and is not a root cause.
- Feature importance remains predictive, not causal.
- Monitoring never retrains, never replaces the model, and never authorizes production.
- Label-dependent metrics are UNAVAILABLE when first-pass outcomes are missing.
- Model health is advisory. It is not a production authorization, not a root cause, not a causal effect, and not an instruction to retrain or replace the model automatically.
