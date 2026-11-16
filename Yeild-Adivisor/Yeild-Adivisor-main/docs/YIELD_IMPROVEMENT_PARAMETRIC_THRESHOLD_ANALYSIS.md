# Yield Improvement: Generalized Parametric Analysis & Candidate Threshold Engine (Stage 1.3)

## 1. Overview & Objective
This document provides the authoritative, reconciled technical specification, data extraction rules, empirical results, confusion matrices, and validation assessments for **Stage 1.3: Independent Metric Reconciliation and Validation Sign-off**.

**Scope & Governance:** Diagnostic and exploratory analysis only (`INVESTIGATION_CANDIDATE_ONLY`). All production modifications, ATE setpoint updates, and recipe alterations are strictly `FORBIDDEN`.

---

## 2. Physical Die Identity, Extraction Rules & Strict Population Denominators

### Physical Identity Rule
Physical dies are uniquely identified by the triplet:
```python
die_key = (lot_id, wafer_id, die_id)
```

### First-Pass Isolation Rules
Inspection of the canonical dataset `yi_synthetic_v2` confirmed:
- 2,500 physical dies across 5 lots (L001-L005) and 25 wafers (W01-W05).
- 2,560 total test attempts recorded in `die_attempts.csv`.
- 20,480 raw parametric measurement records (8 parameters x 2,560 attempts) in `parametric_measurements.csv`.
- 60 retest attempts on 57 distinct dies (accounting for 480 duplicate parametric rows).

Analytical Isolation Rules:
1. All queries strictly filter for `is_first_attempt == True` and `attempt_number == 1`. Conflicting attempts are quarantined.
2. Duplicate physical dies with first-pass attempts are quarantined and excluded.
3. Retest measurements (480 rows) are completely excluded from first-pass baseline distributions.
4. Measurements are joined strictly via foreign key `attempt_id`.
5. Exactly 2,500 eligible physical dies are evaluated (2,249 PASS, 251 FAIL).

### Reconciled Population Denominators
- **`eligible_physical_dies`**: Total eligible physical dies identified during first-pass extraction (2,500).
- **`valid_first_pass_measurements`**: Number of eligible dies with a valid, finite measurement for the specific parameter (2,500 for all 8 parameters in `yi_synthetic_v2`).
- **`missing_measurements`**: `eligible_physical_dies - valid_first_pass_measurements` (0 in complete canonical V2 data).
- **`flagged_share_of_measured`**: `n_dies_flagged / valid_first_pass_measurements`.
- **`flagged_share_of_all_eligible`**: `n_dies_flagged / eligible_physical_dies`.
- **Confusion Matrix Population**: Evaluated strictly on the measured population with explicit descriptions. `TP + FP + FN + TN == total_evaluated_count == valid_first_pass_measurements`.

---

## 3. Parameter Registry & Specification Provenance

| Parameter | Field | Unit | Semantics | Direction | Spec Provenance | Analysis Eligibility |
|---|---|---|---|---|---|---|
| IDDQ | measurement | uA | Quiescent leakage current | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Eligible |
| VMIN | measurement | V | Minimum functional voltage | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Eligible |
| VMAX | measurement | V | Maximum breakdown/timing voltage | LOWER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Eligible (Small sample) |
| VDD | measurement | V | Core supply rail voltage | BAND | SYNTHETIC_GENERATOR_REFERENCE | Ineligible (Nominal rail, 0 fails) |
| SUPPLY_CURRENT | measurement | mA | Active operating dynamic current | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Ineligible (Heavy overlap) |
| CONTACT_RESISTANCE | measurement | ohm | Probe-to-pad contact resistance | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Eligible |
| INTERCONNECT_RESISTANCE | measurement | ohm | Metal line / via resistance | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Ineligible (Identical pass/fail) |
| ON_RESISTANCE | measurement | ohm | Transistor Rds_on resistance | UPPER_BOUND | SYNTHETIC_GENERATOR_REFERENCE | Ineligible (Identical pass/fail) |

### Specification Provenance Disclaimer
No authoritative production specifications exist in the repository. Limit values (`lower_limit`, `upper_limit`) originate solely from synthetic generation parameters (`configs/synthetic_v2.yaml`) and are explicitly labeled as `SYNTHETIC_GENERATOR_REFERENCE`. They must not be treated as factory production specifications.

---

## 4. Reconciled Empirical Results & Confusion Matrices (Canonical V2)

All metrics below are generated directly from the execution of the current engine on canonical `yi_synthetic_v2`:

| Parameter | Target Code | Target Fails | Non-Targets | Candidate Boundary | TP | FP | FN | TN | Total Evaluated | In-Sample Sens | In-Sample Spec | Flagged Dies (% Measured / % Eligible) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IDDQ | IDDQ | 38 | 2462 | 48.6116 uA (UPPER_BOUND) | 27 | 23 | 11 | 2439 | 2500 | 71.1% (27/38) | 99.1% (2439/2462) | 50 (2.0% / 2.0%) |
| VMIN | VMIN | 39 | 2461 | 0.7839 V (UPPER_BOUND) | 29 | 121 | 10 | 2340 | 2500 | 74.4% (29/39) | 95.1% (2340/2461) | 150 (6.0% / 6.0%) |
| VMAX | VMAX | 12 | 2488 | None (INSUFFICIENT_EVIDENCE) | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | 0 | N/A | N/A | 0 (0.0% / 0.0%) |
| VDD | N/A | 0 | 2500 | None (INSUFFICIENT_EVIDENCE) | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | 0 | N/A | N/A | 0 (0.0% / 0.0%) |
| SUPPLY_CURRENT | LEAKAGE | 9 | 2491 | None (INSUFFICIENT_EVIDENCE) | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | 0 | N/A | N/A | 0 (0.0% / 0.0%) |
| CONTACT_RESISTANCE | CONTACT | 92 | 2408 | 1.3170 ohm (UPPER_BOUND) | 52 | 648 | 40 | 1760 | 2500 | 56.5% (52/92) | 73.1% (1760/2408) | 700 (28.0% / 28.0%) |
| INTERCONNECT_RESISTANCE | N/A | 0 | 2500 | None (INSUFFICIENT_EVIDENCE) | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | 0 | N/A | N/A | 0 (0.0% / 0.0%) |
| ON_RESISTANCE | N/A | 0 | 2500 | None (INSUFFICIENT_EVIDENCE) | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | 0 | N/A | N/A | 0 (0.0% / 0.0%) |

### Reconciled Denominator Breakdown
- **IDDQ**: Target failure code is `IDDQ` (38 dies). Non-target dies total 2,462 (2,249 first-pass PASS + 213 other failure codes). In-sample cutpoint of 48.6116 uA flags 50 dies: 27 TP, 23 FP (19 PASS, 4 other fail), 11 FN, 2,439 TN. True Specificity across all non-targets is 2439 / 2462 = 99.07%; specificity evaluated against pure PASS dies alone is 2230 / 2249 = 99.16%. Total evaluated count: 27 + 23 + 11 + 2439 = 2,500.
- **VMIN**: Target failure code is `VMIN` (39 dies). Non-target dies total 2,461 (2,249 first-pass PASS + 212 other failure codes). In-sample cutpoint of 0.7839 V flags 150 dies: 29 TP, 121 FP (109 PASS, 12 other fail), 10 FN, 2,340 TN. Total evaluated count: 29 + 121 + 10 + 2340 = 2,500.
- **CONTACT_RESISTANCE**: Target failure code is `CONTACT` (92 dies). Non-target dies total 2,408 (2,249 first-pass PASS + 159 other failure codes). In-sample cutpoint of 1.3170 ohm flags 700 dies: 52 TP, 648 FP, 40 FN, 1,760 TN. Total evaluated count: 52 + 648 + 40 + 1760 = 2,500.

---

## 5. Reconciled Leave-One-Out (LOO) Lot Cross-Validation

### Validation Principles Enforced
1. **Sample Floor**: A candidate boundary is established on training lots if and only if training material contains >= 15 target failures and >= 30 non-targets. Folds with < 15 target failures receive `INSUFFICIENT_TRAIN_DATA` without evaluating threshold performance on held-out material.
2. **Zero Held-Out Fails**: Folds with zero held-out target failures receive `held_out_sensitivity = None` and status `NO_HELD_OUT_TARGET_FAILURES`. Zero-fail folds are never treated as evidence of sensitivity.
3. **Honest Generalization Assessment**: Generalization across lots is never asserted based on specificity alone when excursion fail counts are near zero.

### Parameter-by-Parameter Fold Summary
#### IDDQ LOO Cross-Validation
**Assessment**: Fold(s) holding out ['L004'] had insufficient target failures in training material (<15) to establish a candidate threshold (INSUFFICIENT_TRAIN_DATA). While held-out baseline lots maintain high specificity, cross-lot sensitivity cannot be confirmed due to zero or near-zero held-out target failures in baseline lots.

| Held-Out Lot | Train Established | Train Candidate Value | Train Targets | Train Non-Targets | Fold Status | Held-Out Dies | Target Fails | Non-Targets | TP | FP | FN | TN | Held-Out Sens | Held-Out Spec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L001 | True | 49.0583 uA | 33 | 1967 | EVALUATED | 500 | 5 | 495 | 1 | 0 | 4 | 495 | 20.0% | 100.0% |
| L002 | True | 48.8767 uA | 36 | 1964 | EVALUATED | 500 | 2 | 498 | 2 | 5 | 0 | 493 | 100.0% | 99.0% |
| L003 | True | 49.0907 uA | 38 | 1962 | NO_HELD_OUT_TARGET_FAILURES | 500 | 0 | 500 | 0 | 0 | 0 | 500 | None | 100.0% |
| L004 | False | None | 11 | 1989 | INSUFFICIENT_TRAIN_DATA | 500 | 27 | 473 | 0 | 0 | 0 | 0 | None | None |
| L005 | True | 49.0276 uA | 34 | 1966 | EVALUATED | 500 | 4 | 496 | 1 | 1 | 3 | 495 | 25.0% | 99.8% |

#### VMIN LOO Cross-Validation
**Assessment**: Fold(s) holding out ['L004'] had insufficient target failures in training material (<15) to establish a candidate threshold (INSUFFICIENT_TRAIN_DATA). While held-out baseline lots maintain high specificity, cross-lot sensitivity cannot be confirmed due to zero or near-zero held-out target failures in baseline lots.

| Held-Out Lot | Train Established | Train Candidate Value | Train Targets | Train Non-Targets | Fold Status | Held-Out Dies | Target Fails | Non-Targets | TP | FP | FN | TN | Held-Out Sens | Held-Out Spec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L001 | True | 0.8104 V | 35 | 1965 | EVALUATED | 500 | 4 | 496 | 0 | 5 | 4 | 491 | 0.0% | 99.0% |
| L002 | True | 0.8134 V | 39 | 1961 | NO_HELD_OUT_TARGET_FAILURES | 500 | 0 | 500 | 0 | 2 | 0 | 498 | None | 99.6% |
| L003 | True | 0.8120 V | 37 | 1963 | EVALUATED | 500 | 2 | 498 | 2 | 2 | 0 | 496 | 100.0% | 99.6% |
| L004 | False | None | 10 | 1990 | INSUFFICIENT_TRAIN_DATA | 500 | 29 | 471 | 0 | 0 | 0 | 0 | None | None |
| L005 | True | 0.8132 V | 35 | 1965 | EVALUATED | 500 | 4 | 496 | 1 | 2 | 3 | 494 | 25.0% | 99.6% |

#### CONTACT_RESISTANCE LOO Cross-Validation
**Assessment**: Cross-lot performance warnings observed on held-out lot(s) ['L002', 'L003', 'L004']. Candidate thresholds are investigation-only boundaries and must not be considered generally validated across shifted lots.

| Held-Out Lot | Train Established | Train Candidate Value | Train Targets | Train Non-Targets | Fold Status | Held-Out Dies | Target Fails | Non-Targets | TP | FP | FN | TN | Held-Out Sens | Held-Out Spec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L001 | True | 1.3130 ohm | 90 | 1910 | EVALUATED | 500 | 2 | 498 | 0 | 91 | 2 | 407 | 0.0% | 81.7% |
| L002 | True | 1.3181 ohm | 47 | 1953 | EVALUATED | 500 | 45 | 455 | 27 | 189 | 18 | 266 | 60.0% | 58.5% |
| L003 | True | 1.2909 ohm | 58 | 1942 | EVALUATED | 500 | 34 | 466 | 23 | 194 | 11 | 272 | 67.6% | 58.4% |
| L004 | True | 1.3156 ohm | 85 | 1915 | EVALUATED | 500 | 7 | 493 | 1 | 104 | 6 | 389 | 14.3% | 78.9% |
| L005 | True | 1.3110 ohm | 88 | 1912 | EVALUATED | 500 | 4 | 496 | 1 | 96 | 3 | 400 | 25.0% | 80.6% |

---

## 6. Mandatory Safety Controls & Architectural Invariants

All recommendation contracts and engine responses enforce the following immutable invariants:
- `production_action: "FORBIDDEN"`
- `production_authorized: False`
- `safety_eligible_production_rate: 0.0`
- `safety_eligible_production_count: 0`
- `status: "INVESTIGATION_CANDIDATE_ONLY"`
- `spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE"`
- `not_a_root_cause: True`
- `supporting_detectors: ["parametric"]` (No false attribution to `near_limit` detector)

---

## 7. Verification & Sign-off Summary

All automated test suites pass without error:
1. `tests/unit/test_parametric_analysis.py`: 13 passed in 4.94s.
2. `tests/unit/test_api_recommendations.py` & `test_recommendation_engine.py`: 10 passed in 81.18s.
3. `tests/unit/test_api_dashboard.py` & `test_fpy_golden.py`: 58 passed in 78.88s.
4. Verified that `TP + FP + FN + TN == total_evaluated_count` holds across all in-sample and evaluated cross-validation folds.
5. SHA-256 hashes of canonical V2 dataset and `yi_ml_v1` artifacts verified unchanged.

**Sign-off Status**: **STAGE 1.3 SIGN-OFF COMPLETE**.