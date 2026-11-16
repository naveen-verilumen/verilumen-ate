# Model versioning policy

This policy is the long-term naming and reuse contract for Yield Improvement Agent model artifacts.

## Format

| Kind | Pattern | Example |
|---|---|---|
| Champion / activated lineage | `yi_ml_vN` | `yi_ml_v1` |
| Candidate | `yi_ml_v{N+1}_candidate_NNN` | `yi_ml_v2_candidate_001` |

`N` is a positive integer. Candidate sequence `NNN` is a zero-padded three-digit counter starting at `001` for that major line.

Versions are **never reused** for a different artifact. A rejected or retired id stays in the registry.

## Current champion

`yi_ml_v1` is Logistic Regression, Phase 7 artifact, Phase 8B decision `KEEP_LOGISTIC`. It is ACTIVE until an explicit `model activate` or `model rollback` changes the registry pointer.

## New candidates

1. Do not create a candidate unless a human runs `retrain prepare`.
2. The next id is computed from the current champion major version and existing candidate numbers. If `yi_ml_v1` is champion, the first slot is `yi_ml_v2_candidate_001`.
3. Training uses the **approved** architecture (logistic) and feature-contract version `yi_ml_features_v1` unless a future phase introduces a **new explicit** feature-contract version. Silent feature expansion is forbidden.
4. A candidate keeps its id after validation, approval, activation, retirement, or rejection.

## Activation

Activation is a registry pointer (`active_version`). It does not rewrite `artifacts/ml/yi_ml_v1/`. Previous ACTIVE models are `RETIRED` and kept for rollback.

If a `yi_ml_v2_candidate_001` is ever activated in a later phase, it remains that version string. A future policy may add an alias `yi_ml_v2`; that alias would be an explicit additional event, not a silent rename.

## Feature-contract versions

`yi_ml_features_v1` is the frozen 16-feature Phase 7/8 contract. Changing allowed derived features requires a new `feature_set_version` (for example `yi_ml_features_v2`) recorded on the candidate. Mixing contracts at activation fails closed.

## Identities

`approved_by` / `activated_by` / `rolled_back_by` are human identifiers supplied on the CLI. If missing, store `unavailable`. Do not infer a person from CI, metrics, or test success.
