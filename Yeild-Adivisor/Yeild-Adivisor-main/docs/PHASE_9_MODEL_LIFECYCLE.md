# Phase 9 — Controlled model lifecycle

**Status:** Implemented. Manual, fail-closed, advisory. `yi_ml_v1` remains the ACTIVE champion. This is **not** automatic retraining, automatic selection, or automatic activation.

Companion: `docs/MODEL_VERSIONING_POLICY.md`, `docs/MODEL_ARCHITECTURE_REVIEW.md` (Phase 8B: `KEEP_LOGISTIC`).

```text
prepare → train → evaluate → validate → approve → activate
                                      ↘ reject
activate ⇄ rollback (retired champion kept)
```

Each arrow is a **separate command**. TRAIN ≠ VALIDATE ≠ APPROVE ≠ ACTIVATE.

## 1. Objective

Give the Yield Improvement Agent an auditable way to create candidates, compare them to the champion, and — only after explicit human approval — change which registered artifact is ACTIVE. Production action remains `FORBIDDEN`.

## 2. Champion

| Field | Value |
|---|---|
| model_version | `yi_ml_v1` |
| architecture | `logistic_regression` |
| state | `ACTIVE` |
| directory | `artifacts/ml/yi_ml_v1/` (immutable; never overwritten) |

Champion status is a **lifecycle pointer**, not “highest metric wins.” Phase 8B decided `KEEP_LOGISTIC`; candidate training uses that approved architecture only.

## 3. States and transitions

`CANDIDATE` → `VALIDATED` → `APPROVED` → `ACTIVE` → `RETIRED`

Rejection: `CANDIDATE|VALIDATED|APPROVED` → `REJECTED`.

`APPROVED` does **not** become `ACTIVE` automatically. Only `model activate` (or `model rollback`) may set `ACTIVE`.

Invalid transitions fail closed.

## 4. Layout

```text
artifacts/ml/
  yi_ml_v1/                 # champion files; never rewritten
  candidates/<version>/     # candidate artifacts
  registry/
    registry.json
    audit.jsonl             # append-only
    evaluations/            # sidecar eval for non-candidate versions
```

Activation changes `registry.json` `active_version`. It does **not** copy files into `yi_ml_v1/`.

## 5. Registry fields

`model_version`, `architecture`, `state`, `created_at`, `dataset_id`, `feature_contract_version`, `training_config_hash`, `artifact_hashes`, `evaluation_result`, `parent_model_version`, `approved_by`, `approved_at`, `activated_by`, `activated_at`, `retired_at`, `rollback_target`, `notes`.

If a human identity is absent, `approved_by = unavailable`. Identities are never inferred from metrics.

## 6. Workflows

**Prepare:** `python -m yield_improvement retrain prepare <dataset_dir>`  
Creates `yi_ml_v{N+1}_candidate_NNN`, state `CANDIDATE`. No fit.

**Train:** `python -m yield_improvement retrain train <candidate_version>`  
Fits logistic with train-fold feature builder, LOLO nested isotonic calibration, class weights. Writes candidate artifacts. Does not evaluate, approve, or activate. Refuses to overwrite `yi_ml_v1`.

**Evaluate:** `python -m yield_improvement retrain evaluate <candidate_version>`  
Phase 8B LOLO protocol: raw and nested-calibrated metrics, per-lot mean/sd/min/max, capture@5/10/20, permutation-importance stability. Does not activate.

**Compare:** `python -m yield_improvement retrain compare --candidate <v> --champion yi_ml_v1`  
Dimensions: PR-AUC, ROC-AUC, top-10/20 capture, Brier, ECE, lot stability, complexity, dependency burden. Status: `SUPERIOR | COMPARABLE | INFERIOR | INCONCLUSIVE`. Close-tolerance 0.02. No opaque score. Dataset mismatch → `INCONCLUSIVE`. Does not approve or activate.

**Validate:** `python -m yield_improvement model validate --candidate <v>`  
Mandatory: schema, hashes, feature contract, no leakage, LOLO complete, calibration/metrics present, safety, seed. Incomplete eval stays `CANDIDATE`. Hash/leakage/contract failure → `REJECTED`.

**Approve:** `python -m yield_improvement model approve --candidate <v> --approved-by "<human>"`  
Requires `VALIDATED` and a real identifier (not `unavailable`). Does not activate.

**Activate:** `python -m yield_improvement model activate --candidate <v> --activated-by "<human>"`  
Requires `APPROVED`, matching hashes, feature contract, safety. Previous ACTIVE → `RETIRED` (files kept).

**Rollback:** `python -m yield_improvement model rollback --target <v> --rolled-back-by "<human>"`  
Registered version only. Hash + contract checks. Arbitrary paths are rejected.

**Inspect:** `model list`, `model inspect --version <v>`, `model verify`  
Verify: exactly one ACTIVE, no duplicate versions, hashes, approval/activation metadata, audit consistency. Failures return `NEEDS_REVIEW` and are **not** auto-repaired.

## 7. Safety gates

Every command asserts:

- `production_action = FORBIDDEN`
- `production_authorized = false`
- `safety_eligible_production_count = 0`
- `safety_eligible_production_rate = 0.0`
- `invoked_agents = []`

Champion SHA-256 of `model.pkl`, `metadata.json`, `feature_list.json`, `metrics.json` is checked around mutating operations. Unexpected change → fail closed.

`ml train` refuses to overwrite an existing champion directory.

## 8. Monitoring and hypotheses

Monitoring may report `active_model_version` and `overall_status` (model health). `NEEDS_RETRAINING` / `CONSIDER_RETRAINING` are advisory. Monitoring never prepares, trains, approves, activates, or rolls back.

Hypothesis ranking (`evidence_score`, tier, rank) is unchanged. ML remains `SECONDARY_SUPPORT`, `not_a_root_cause = true`. Opportunity counts stay Phase 5 rules; a model prediction is not recovered yield.

## 9. Reproducibility

Same dataset + seed + `ml.yaml` + allowlist should reproduce metrics and feature lists. Metadata `trained_at` differs across runs, so pickle/metadata SHA-256 of two candidate versions need not match byte-for-byte. Tests check numerical PR-AUC/Brier equivalence.

## 10. Failure behavior

Unknown version, duplicate version, hash mismatch, feature-contract mismatch, activate without validate/approve, approve without validate, arbitrary path, and registry corruption all fail closed. The registry is not silently repaired.
