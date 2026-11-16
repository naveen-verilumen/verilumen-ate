# Recommendation Quality and Evidence Traceability (Option 1)

## Executive Summary
This document establishes the architecture, evidence provenance, classification taxonomy, fail-closed validation rules, and dashboard presentation implemented for **Option 1: Recommendation Quality and Evidence Traceability** in the Yield Advisor / Yield Improvement Agent.

Every engineering recommendation explains:
1. **What was observed** directly from physical first-pass records.
2. **Which data and statistical detectors support it**, with explicit numerators, denominators, and reference baselines.
3. **How strong the evidence is**, using transparent qualitative classifications (`STRONG`, `MODERATE`, `WEAK`, `INSUFFICIENT`) rather than fabricated probabilities.
4. **What remains uncertain** (distinguishing correlation from causation, noting unjoined MES/equipment tracking and metrology logs).
5. **What the engineer should investigate next**, with advisory investigation actions clearly distinguished from approved corrective actions.

---

## 1. Existing Recommendation Flow
Prior to this enhancement:
1. Detectors (`lot`, `wafer`, `spatial`, `parametric`, `near_limit`, etc.) analyzed canonical test records and generated `ReportEvidenceFinding` items.
2. The hypothesis engine synthesized findings into `ReportHypothesis` objects containing statistical metrics (`statistical_evidence`, `affected_population`, `data_gaps`, `limitations`).
3. The recommendation generator (`generator.py`) transformed hypotheses into `EngineeringRecommendation` records, but key traceability details (exact comparison populations, detector method details, p-values, effect size metrics, explicit baseline denominators, and qualitative strength) were lost or compressed into unstructured strings.
4. The dashboard presented high-level priority and confidence badges, but lacked an expandable evidence ledger showing provenance and what data remains uncertain.

---

## 2. Backend Schema & Service Changes

### Contracts Extended (`src/yield_improvement/recommendations/contracts.py`)
- **`EvidenceClassification`**:
  `Literal["OBSERVED_FACT", "STATISTICAL_ASSOCIATION", "UNCONFIRMED_HYPOTHESIS", "INSUFFICIENT_EVIDENCE"]`
- **`EvidenceStrength`**:
  `Literal["STRONG", "MODERATE", "WEAK", "INSUFFICIENT"]`
- **`SupportingEvidenceItem`**:
  ```python
  class SupportingEvidenceItem(BaseModel):
      evidence_type: str
      evidence_classification: EvidenceClassification
      source_dataset: str
      source_artifact: str
      entity_scope: str
      numerator: int | None = None
      denominator: int | None = None
      observed_value: float | int | str | None = None
      baseline_value: float | int | str | None = None
      comparison_baseline: str | None = None
      unit: str | None = None
      time_scope: str = "FIRST_PASS"
      validation_state: str = "NOT_EVALUATED"  # Mandatory fail-closed default
      limitations: list[str] = Field(default_factory=list)
  ```
- **`EngineeringRecommendation`**:
  Added the following backwards-compatible fields:
  - `summary: str = ""` (plain-language explanation)
  - `observed_facts: list[str] = Field(default_factory=list)` (verifiable facts from physical attempts)
  - `supporting_evidence: list[SupportingEvidenceItem] = Field(default_factory=list)` (structured evidence ledger)
  - `evidence_strength: EvidenceStrength = "INSUFFICIENT"` (mandatory fail-closed default)
  - `uncertainties: list[str] = Field(default_factory=list)` (what data does not establish)
  - `data_gaps: list[str] = Field(default_factory=list)` (missing/unjoined tracking records)
  - `recommended_next_steps: list[str] = Field(default_factory=list)` (concrete engineering checks)
  - `validation_status: str = "NOT_EVALUATED"` (mandatory fail-closed default)
  - `safety_status: str = "ADVISORY_ONLY: Production action is FORBIDDEN. Production authorized: False."`

### Recommendation Generation (`src/yield_improvement/recommendations/generator.py`)
- Added `_build_evidence_traceability(...)`:
  - Dynamically calculates exact first-pass subgroup numerators (`affected_count`) and denominators (`pop_dies`).
  - Dynamically calculates comparison baseline numerators (`base_fails`) and denominators (`base_dies`) from actual canonical first-pass records:
    - Lot excursions: compared against all other lots in dataset (`LOT_EXCLUDED`).
    - Wafer excursions: compared against remaining wafers in the device run (`SUBGROUP_EXCLUDED`).
    - Spatial border excursions: compared against inner core dies (`SUBGROUP_EXCLUDED`).
    - Global populations: compared against dataset-wide baseline (`DATASET_WIDE`).
  - Translates detector test results (`method`, `effect_size`, `p_value`, `adjusted_p_value`) into structured `SupportingEvidenceItem` records classified as `STATISTICAL_ASSOCIATION`.
  - Captures ML model status honestly as `INSUFFICIENT_EVIDENCE` for V2 without inflating recommendation strength.

---

## 3. Evidence Provenance & Classification Taxonomy

| Classification | Meaning & Verification Rule | Example |
| :--- | :--- | :--- |
| **Observed Fact** | Directly measured from canonical first-pass attempts `(lot_id, wafer_id, die_id)`. Zero inference. | `97 of 500 first-pass dies failed in PROCESS L004 (19.4% failure rate).` |
| **Statistical Association** | Statistically validated relationship between candidate subgroup and test fallout. Does not establish causation. | `Lot vs rest two-proportion Fisher test: effect = +11.70%, p = 6.88e-15, adj_p = 1.39e-13.` |
| **Unconfirmed Hypothesis** | Domain-informed engineering hypothesis regarding potential upstream processing anomalies. Requires verification. | `Yield loss is associated with lot identity (L004).` |
| **Insufficient Evidence** | Signal is weak, unverified on independent holdouts, or fails validation gates. | `Champion ML model ROC-AUC < 0.50 on holdout lots; exploratory only.` |

---

## 4. Handling of Missing, Weak, and Contradictory Evidence (Fail-Closed Rules)

1. **Default State**:
   - `evidence_strength` defaults to `INSUFFICIENT`.
   - `validation_status` defaults to `NOT_EVALUATED`.
   - `validation_state` in `SupportingEvidenceItem` defaults to `NOT_EVALUATED`.
2. **Sample-Size Gate**:
   - If subgroup eligible dies < 30 or observed failures < 10, `evidence_strength` is assigned `INSUFFICIENT` (`validation_status = "INSUFFICIENT_SAMPLE_SIZE"`).
3. **Statistical Significance Gate**:
   - If detectors evaluate to `p_value >= 0.05` or `adjusted_p_value >= 0.05`, evidence fails closed to `INSUFFICIENT` (`validation_status = "NO_STATISTICAL_SIGNIFICANCE"`).
4. **Data-Gap Penalty**:
   - If > 2 data gaps exist or signal effect size is marginal, strength is capped at `WEAK` (`validation_status = "WEAK_STATISTICAL_SIGNAL"`).
5. **No ML Inflation**:
   - Model predictions with pooled LOLO ROC-AUC < 0.50 are reported as `NEEDS_MORE_DATA` / `INSUFFICIENT_EVIDENCE` and cannot override or inflate statistical validation.

---

## 5. Dashboard Implementation (`frontend/src/components/RankedRecommendations.tsx`)

Each recommendation card renders four concise, non-overlapping sections:
- **A. Finding**: Rank badge (`#1`), Priority badge, Evidence Strength badge (`STRONG`, `MODERATE`, `WEAK`, `INSUFFICIENT`), Scope badge (`Global` vs `Lot-Level`), Target population badge, title, and concise plain-language summary.
- **B. Why This Recommendation Exists**:
  - Key metrics grid: `Affected Dies (Overall)` with exact numerator/denominator `(X / Y dies)` alongside `Subgroup Failure Rate` `(X / Y dies)`.
  - Bulleted list of Key Observed Facts with exact counts and baseline comparisons.
  - Drill-down button: "View failing dies" opening the modal dialog.
- **C. Evidence Quality & Traceability (Expandable Section)**:
  - Collapsible `<details>` element preserving compact layout and preventing vertical clutter.
  - Header displays current `Validation: STATISTICAL_SIGNAL_VALIDATED`.
  - Detailed ledger showing individual evidence items with source artifact, test method, rate, and classification badges.
  - Separate callout boxes for Uncertainties and Data Gaps.
- **D. What to Investigate Next**:
  - Highlights `Recommended Next Action`.
  - Explicit advisory banner: `Advisory suggestion — production action forbidden`.

---

## 6. Test Execution and Results

### Backend Test Suite (`pytest`)
- `tests/unit/test_recommendation_traceability.py`: 6 passed
  - `test_recommendation_traceability_schema_and_defaults`: verified mandatory `INSUFFICIENT` and `NOT_EVALUATED` defaults.
  - `test_insufficient_evidence_fail_closed_cannot_be_upgraded`: verified small sample sizes and insignificant p-values fail closed to `INSUFFICIENT`.
  - `test_v2_canonical_traceability_and_provenance`: verified all V2 recommendations expose structured evidence items with valid provenance.
  - `test_first_pass_filtering_and_baseline_calculation`: verified exact mathematical counts (e.g. 97/500 vs 154/2000, 118/900 vs 133/1600).
  - `test_evidence_classification_distinction`: verified separation of observed facts from statistical associations.
  - `test_lot_scoped_bundle_traceability`: verified lot-scoped recommendations calculate denominators matching selected lot.
- `tests/unit/test_recommendation_engine.py`: 3 passed.
- `tests/unit/test_api_recommendations.py`: 4 passed.
- `tests/unit/test_failing_dies.py`: 8 passed.
- `tests/unit/test_api_dashboard.py`: 18 passed.
- **Total Backend Result**: **39 passed in 99.48s (100% pass rate)**.

### Frontend Test Suite (`vitest`)
- `frontend/src/test/rankedRecommendations.test.tsx`: 6 passed.
  - Scope selector tabs (All, Global, Lot-Level).
  - Scope filtering logic.
  - Rendering recommendation cards with title, priority, metrics, and next action.
  - Rendering 4 card sections (Finding summary, Observed facts, Expandable evidence quality, Advisory next steps).
  - Graceful handling of missing optional traceability fields without crashing.
- `frontend/src/test/dashboard.test.tsx`: 34 passed.
- `frontend/src/test/waferMap.test.tsx`: 10 passed.
- `frontend/src/test/failingDiesModal.test.tsx`: 4 passed.
- `frontend/src/test/parametricAnalysis.test.tsx`: 13 passed.
- Other unit tests: 26 passed.
- **Total Frontend Result**: **93 passed in 3.90s (100% pass rate)**.

### Frontend Production Build (`npm run build`)
- `tsc --noEmit && vite build`: **Completed in 4.83s with 0 errors**.

---

## 7. Files Changed

1. `src/yield_improvement/recommendations/contracts.py`:
   - Added `EvidenceClassification`, `EvidenceStrength`, `SupportingEvidenceItem`.
   - Extended `EngineeringRecommendation` with `summary`, `observed_facts`, `supporting_evidence`, `evidence_strength`, `uncertainties`, `data_gaps`, `recommended_next_steps`, `validation_status`, and `safety_status`.
2. `src/yield_improvement/recommendations/generator.py`:
   - Implemented `_build_evidence_traceability(...)`.
   - Connected structured evidence assembly, fail-closed classification, and dynamic baseline calculations into recommendation generation.
3. `frontend/src/types/api.ts`:
   - Added TypeScript types: `EvidenceClassification`, `EvidenceStrength`, `SupportingEvidenceItem`.
   - Extended `EngineeringRecommendation` interface with optional traceability fields.
4. `frontend/src/components/RankedRecommendations.tsx`:
   - Updated recommendation card UI to display Sections A, B, C, and D.
   - Implemented compact expandable `<details>` section for evidence ledger, data gaps, and uncertainties.
5. `tests/unit/test_recommendation_traceability.py`:
   - Comprehensive backend tests verifying traceability, fail-closed strength assignment, baseline calculation, and safety invariants.
6. `frontend/src/test/rankedRecommendations.test.tsx`:
   - Comprehensive frontend tests verifying card section rendering and graceful degradation.
7. `docs/RECOMMENDATION_EVIDENCE_TRACEABILITY.md`:
   - Architecture, design, test results, and compliance documentation.

---

## 8. Protected Scope & Safety Invariant Confirmation

- **VMAX and SUPPLY_CURRENT Investigations**: Remained strictly on hold. No failure code mappings modified; no new candidate boundaries forced.
- **Datasets & Ground Truth**: Canonical V2 dataset files and synthetic generators were untouched.
- **ML Artifacts**: Historical `yi_ml_v1` model and V2 champion artifacts remain untouched.
- **Safety Invariants**:
  - `production_action: "FORBIDDEN"`
  - `production_authorized: false`
  - `safety_eligible_production_rate: 0.0`
  - `safety_eligible_production_count: 0`
  - `not_a_root_cause: true`
- **Git State**: Zero commits and zero pushes were performed.
