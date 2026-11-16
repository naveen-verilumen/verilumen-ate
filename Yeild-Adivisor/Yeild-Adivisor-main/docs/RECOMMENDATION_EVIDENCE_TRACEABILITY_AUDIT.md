# Recommendation Quality and Evidence Traceability — Focused Post-Implementation Audit

## Audit Overview
A focused post-implementation audit of **Option 1: Recommendation Quality and Evidence Traceability** in the Yield Advisor / Yield Improvement Agent project was conducted on October 14, 2026.

The audit verified the backend recommendation contracts, recommendation generator, API response payloads, React dashboard cards, and associated unit and integration tests across 8 key areas.

---

## 1. Audit Findings by Area

### Area 1: Fail-Closed Evidence Strength and Validation Status
- **Audit Target**: Missing or unevaluated evidence must not become `MODERATE`, `STRONG`, or `STATISTICAL_SIGNAL_VALIDATED` by default.
- **Verification Evidence**:
  - In `src/yield_improvement/recommendations/contracts.py`:
    - `EngineeringRecommendation.evidence_strength` defaults to `"INSUFFICIENT"`.
    - `EngineeringRecommendation.validation_status` defaults to `"NOT_EVALUATED"`.
    - `SupportingEvidenceItem.validation_state` defaults to `"NOT_EVALUATED"`.
  - In `src/yield_improvement/recommendations/generator.py`:
    - The classification logic previously had an edge case: if `hypothesis.statistical_evidence` was an empty list (`[]`), `has_sig_detector` was `False`, but the clause `elif not has_sig_detector and len(hypothesis.statistical_evidence) > 0:` skipped fail-closed handling, allowing an empty-evidence hypothesis to fall through to `MODERATE_EVIDENCE`.
    - **Fix Applied**: Updated the condition to `elif not has_sig_detector:`, ensuring that hypotheses with empty or non-significant detector records fail closed to `INSUFFICIENT` (`validation_status = "NOT_EVALUATED"` when empty; `"NO_STATISTICAL_SIGNIFICANCE"` when tested but p >= 0.05).
    - Furthermore, `STRONG` evidence classification was strengthened to require multi-domain detector independence (`len(distinct_families) >= 2`) alongside `pop_dies >= 100`, `affected_count >= 20`, and `len(data_gaps) == 0`. Single-domain evidence is strictly capped at `MODERATE`.
  - Added regression test `test_insufficient_evidence_fail_closed_cannot_be_upgraded` asserting that empty statistical evidence records and non-significant signals fail closed.

### Area 2: Statistical Significance vs Physical Causation
- **Audit Target**: Statistical significance must not be presented as proof of physical causation.
- **Verification Evidence**:
  - `contracts.py`: `not_a_root_cause: Literal[True] = True` is enforced with a Pydantic validator. `RECOMMENDATION_DISCLAIMER` states: *"This is not a confirmed root cause and not a promised yield gain."* `_validate_no_forbidden_phrases` prevents phrases claiming authorized production or root cause.
  - `generator.py`: `uncertainties` explicitly includes:
    1. *"Observed statistical association does not establish physical causation."*
    2. *"Upstream equipment, chamber, and tool maintenance lineage are not linked in the current test records."*
    3. *"Physical failure mechanisms have not been confirmed via SEM/TEM or inline defect inspection."*
    4. *"Replication across independent production batches is required before corrective actions can be formulated."*
  - All `SupportingEvidenceItem` instances of type `STATISTICAL_ASSOCIATION` carry the explicit limitation: *"Statistical association does not establish physical causation."*
  - Dashboard cards in `RankedRecommendations.tsx` clearly display the distinction in an advisory banner: *"Advisory suggestion — production action forbidden"* and surface uncertainties in an expandable ledger.

### Area 3: Numerator, Denominator, Rate, and Baseline Consistency
- **Audit Target**: Every displayed numerator, denominator, rate, baseline, and comparison scope is derived from actual first-pass records and is internally consistent.
- **Verification Evidence**:
  - In `generator.py` (`_build_evidence_traceability`), every value is dynamically computed from canonical first-pass records:
    - Subgroup failures: `affected_count = round(pop_dies * pop_rate)`
    - Subgroup rate: `pop_rate`
    - Subgroup denominator: `pop_dies`
    - Comparison baseline denominator: `base_dies = eligible_dies - pop_dies`
    - Comparison baseline failures: `base_fails = max(0, total_fails - affected_count)`
    - Comparison baseline rate: `base_rate = base_fails / max(1, base_dies)`
  - Mathematical integrity verified on canonical V2 dataset:
    - Lot L004: Subgroup 97 / 500 (19.4%) vs Lot-Excluded Baseline 154 / 2,000 (7.7%). Sum: 97 + 154 = 251 failures; 500 + 2,000 = 2,500 dies.
    - Spatial Border: Subgroup 118 / 900 (13.1%) vs Core Baseline 133 / 1,600 (8.3%). Sum: 118 + 133 = 251 failures; 900 + 1,600 = 2,500 dies.
    - Wafer L004/W05: Subgroup 45 / 100 (45.0%) vs Remaining Wafers Baseline 206 / 2,400 (8.58%). Sum: 45 + 206 = 251 failures; 100 + 2,400 = 2,500 dies.
  - Zero hardcoding detected. Scope types are explicitly labeled (`LOT_EXCLUDED`, `SUBGROUP_EXCLUDED`, `DATASET_WIDE`).

### Area 4: Physical Die Identity and Retest Exclusion
- **Audit Target**: Physical die identity uses `(lot_id, wafer_id, die_id)` where appropriate. Retests and duplicate attempts cannot inflate first-pass counts.
- **Verification Evidence**:
  - In `src/yield_improvement/recommendations/failing_dies.py`:
    - Filtering strictly enforces `is_first_attempt == True` or `attempt_number == 1`.
    - Dies are uniquely identified and deduplicated by the physical 3-tuple `(lot_id, wafer_id, die_id)`.
    - Retest-only failures (attempts where attempt > 1 failed after first pass passed) are excluded.
  - In `tests/unit/test_failing_dies.py`:
    - `test_unique_die_counting_and_physical_identity` and `test_first_pass_filtering_and_retest_exclusion` pass with zero failures.

### Area 5: Missing, Contradictory, or Unjoined Evidence & ML Results
- **Audit Target**: Missing, contradictory, or unjoined evidence is explicitly surfaced. Weak ML results cannot inflate recommendation strength or override analytical validation.
- **Verification Evidence**:
  - For dataset `yi_synthetic_v2`, `ml_status` is hard-pinned to `"NEEDS_MORE_DATA"`.
  - An explicit `SupportingEvidenceItem` of type `ML_MODEL_EVALUATION` is attached with classification `INSUFFICIENT_EVIDENCE` noting that pooled leave-one-lot-out ROC-AUC is < 0.50.
  - ML metrics are completely decoupled from `evidence_strength` calculation in `_build_evidence_traceability`; ML cannot inflate evidence strength under any circumstance.
  - Missing MES equipment records and missing Klarf metrology defect scans are explicitly surfaced on every recommendation under `data_gaps` and `uncertainties`.

### Area 6: Preservation of Existing Rankings, Priority, API Compatibility, and Drilldown
- **Audit Target**: Existing recommendation rankings, priority logic, investigation actions, API compatibility, and failing-die drilldown remain intact.
- **Verification Evidence**:
  - `compute_recommendation_score` and `rank_recommendations` in `ranking.py` were not altered. Deterministic ranking order matches baseline.
  - Existing API endpoints (`GET /api/datasets/{dataset_id}/recommendations`, `GET /api/datasets/{dataset_id}/recommendations/{recommendation_id}`, and `GET /api/datasets/{dataset_id}/recommendations/{recommendation_id}/failing-dies`) return identical primary contracts with extended optional fields.
  - Failing-die drilldown modal functions identically and is accessible via "View failing dies" on each card.

### Area 7: Enforcement of Safety Invariants
- **Audit Target**: `production_action = FORBIDDEN`, `production_authorized = false`, `safety_eligible_production_count/rate = zero`, and `not_a_root_cause = true`.
- **Verification Evidence**:
  - Pydantic validators in `EngineeringRecommendation` strictly reject any mutation of these values:
    - `production_action == "FORBIDDEN"` (validator `_action_forbidden`)
    - `production_authorized is False` (validator `_not_authorized`)
    - `safety_eligible_production_rate == 0.0` (validator `_rate_zero`)
    - `safety_eligible_production_count == 0` (validator `_count_zero`)
    - `not_a_root_cause is True` (validator `_root_cause_flag`)
  - Verified across all 5 generated recommendations in `yi_synthetic_v2`.

### Area 8: Scope Protection for VMAX and SUPPLY_CURRENT Investigations
- **Audit Target**: VMAX and SUPPLY_CURRENT-to-LEAKAGE investigations remain on hold. Do not change their mappings, candidate boundaries, datasets, or reports.
- **Verification Evidence**:
  - No files in `src/yield_improvement/parametric_analysis/` were modified.
  - No test limit configs or failure-code mappings in `configs/` or `test_catalog.py` were modified.
  - In `GET /api/datasets/yi_synthetic_v2/parametric-analysis`, both `VMAX` and `SUPPLY_CURRENT` remain reporting:
    - `threshold_status: "NO_THRESHOLD_ESTABLISHED"`
    - `candidate_threshold: null`
  - Zero candidate boundaries were created or forced.

---

## 2. Fixes Applied During Audit

| File | Change Description | Rationale |
| :--- | :--- | :--- |
| [`src/yield_improvement/recommendations/generator.py`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/src/yield_improvement/recommendations/generator.py) | In `_build_evidence_traceability`, updated fail-closed branch from `elif not has_sig_detector and len(hypothesis.statistical_evidence) > 0:` to `elif not has_sig_detector:` | Prevented hypotheses with missing/empty detector evidence from bypassing fail-closed checks and being assigned `MODERATE_EVIDENCE`. |
| [`src/yield_improvement/recommendations/generator.py`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/src/yield_improvement/recommendations/generator.py) | Added multi-domain independence check (`len(distinct_families) >= 2`) to `STRONG_EVIDENCE` branch | Ensured that `STRONG` classification requires multi-domain independent confirmation; single-domain findings are capped at `MODERATE`. |
| [`tests/unit/test_recommendation_traceability.py`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/tests/unit/test_recommendation_traceability.py) | Added regression assertions in `test_insufficient_evidence_fail_closed_cannot_be_upgraded` for empty statistical evidence and single-domain evidence | Proves that empty detector evidence fails closed to `INSUFFICIENT` and `NOT_EVALUATED`, and single-domain evidence is capped at `MODERATE`. |

---

## 3. Test Execution and Verification Results

### Backend Tests (`pytest`)
- `tests/unit/test_recommendation_traceability.py`: **6 passed**
- `tests/unit/test_recommendation_engine.py`: **3 passed**
- `tests/unit/test_api_recommendations.py`: **4 passed**
- `tests/unit/test_failing_dies.py`: **8 passed**
- `tests/unit/test_api_dashboard.py`: **18 passed**
- **Total Backend Result**: **39 passed in 120.10s (100% pass rate)**.

### Frontend Tests (`vitest run --run`)
- `src/test/rankedRecommendations.test.tsx`: **6 passed**
- `src/test/dashboard.test.tsx`: **34 passed**
- `src/test/waferMap.test.tsx`: **10 passed**
- `src/test/failingDiesModal.test.tsx`: **4 passed**
- `src/test/parametricAnalysis.test.tsx`: **13 passed**
- Other unit tests: **26 passed**
- **Total Frontend Result**: **93 passed in 3.99s across 10 test files (100% pass rate)**.

### Frontend Production Build (`npm run build`)
- `tsc --noEmit && vite build`: **Completed in 4.91s with 0 errors**.

---

## 4. Exact Files Changed

1. [`src/yield_improvement/recommendations/generator.py`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/src/yield_improvement/recommendations/generator.py) (Refined fail-closed condition for empty statistical evidence; required multi-domain independence for `STRONG` evidence)
2. [`tests/unit/test_recommendation_traceability.py`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/tests/unit/test_recommendation_traceability.py) (Added regression assertions for empty detector evidence and single-domain caps)
3. [`docs/RECOMMENDATION_EVIDENCE_TRACEABILITY_AUDIT.md`](file:///c:/Users/Keerthan/OneDrive/Desktop/yeild%20agent/docs/RECOMMENDATION_EVIDENCE_TRACEABILITY_AUDIT.md) (This audit report)

---

## 5. Remaining Limitations

1. **Unjoined Upstream Manufacturing Logs**: MES tool run histories and thermal chamber logs are not joined in the current synthetic data model. Recommendations explicitly document this under `data_gaps` and `uncertainties` rather than inferring tool lineage.
2. **Missing Inline Metrology**: Inline defect inspection (Klarf) and physical failure analysis (cross-sectional SEM/TEM) remain unjoined; recommendations specify these as required next investigation steps rather than confirmed physical defect causes.
3. **ML Signal on V2 Material**: Due to leave-one-lot-out ROC-AUC < 0.50 on V2, ML predictions remain strictly classified as `INSUFFICIENT_EVIDENCE` and do not contribute to recommendation strength or ranking.

---

## 6. Git Invariant Confirmation
- **Zero commits** and **zero pushes** were performed during this audit.
