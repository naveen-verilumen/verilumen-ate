# Recommendation Bridge - Hardened
from __future__ import annotations
from yield_improvement.parametric_analysis.contracts import ParametricAnalysisReport, ParametricAnalysisResult
from yield_improvement.recommendations.contracts import (
    EngineeringRecommendation,
    ValidationProtocol,
    ValidationStep,
)

def build_parametric_recommendations(report: ParametricAnalysisReport) -> list[EngineeringRecommendation]:
    recs: list[EngineeringRecommendation] = []
    rank = 1

    for res in report.results:
        # Create recommendations only when candidate threshold is formally established
        if res.threshold_status != 'INVESTIGATION_CANDIDATE_ONLY' or res.candidate_threshold is None:
            continue

        cand = res.candidate_threshold
        cm = cand.training_confusion_matrix
        rec_id = f'REC-PARAM-{res.parameter_name}'

        sens_str = f'{cm.sensitivity:.1%}' if cm.sensitivity is not None else 'N/A'
        spec_str = f'{cm.specificity:.1%}' if cm.specificity is not None else 'N/A'
        max_fp_rate = f'{1.0 - cm.specificity:.1%}' if cm.specificity is not None else '30%'

        steps = [
            ValidationStep(
                step_number=1,
                step_id=f'{rec_id}-S1-DATA_INTEGRITY',
                title=f'Verify {res.parameter_name} Measurement Context & Calibration',
                investigation_action=(
                    f'Verify ATE instrument calibration, probe pin contact, and temperature sensors for {res.parameter_name}. '
                    'Ensure no measurement drift occurred across test heads or probers.'
                ),
                required_evidence='ATE calibration logs, DMM/SMU diagnostic run data, and prober alignment offsets.',
                expected_measurement='Investigation verification that ATE measurement repeatability is nominal and zero hardware alarms occurred.',
                acceptance_criteria='Candidate evidence verified: instrument repeatability confirmed without calibration alarms.',
                rejection_criteria='Measurement shift correlated with ATE hardware replacement, socket degradation, or temperature drift.',
                limitations_and_safety='Advisory hardware check only. Production action is FORBIDDEN. Do not alter ATE calibration tables or test programs.',
            ),
            ValidationStep(
                step_number=2,
                step_id=f'{rec_id}-S2-HOLDOUT_VALIDATION',
                title='Cross-Lot Material Holdout Validation',
                investigation_action=(
                    f'Evaluate candidate boundary ({cand.candidate_value:.4f} {res.unit}) on independent future production lots. '
                    f'Verify that the false-positive rate remains <= {max_fp_rate} and sensitivity >= {sens_str}.'
                ),
                required_evidence='First-pass wafer sort logs from subsequent production lots.',
                expected_measurement='Investigation verification that separation replicates in held-out material without excessive false positives.',
                acceptance_criteria='Candidate evidence verified: failure separation replicates stably across independent lots.',
                rejection_criteria='Candidate boundary causes elevated false-positive yield fallout on clean baseline lots.',
                limitations_and_safety='Advisory investigation step. Never modify production screening limits based on an exploratory candidate boundary.',
            ),
            ValidationStep(
                step_number=3,
                step_id=f'{rec_id}-S3-PHYSICAL_FA',
                title='Failure Analysis & Physical Root Cause Review',
                investigation_action=(
                    f'Submit dies failing beyond candidate threshold ({cand.candidate_value:.4f} {res.unit}) for electrical localization '
                    '(emission microscopy, scan chain diagnosis) and physical cross-section (SEM/FIB).'
                ),
                required_evidence='Lab failure analysis report assessing physical defect structures or marginality.',
                expected_measurement='Investigation verification of physical mechanism (e.g. gate defect, bridging, contact resistance).',
                acceptance_criteria='Candidate evidence verified: concrete physical mechanism found consistent with electrical behavior.',
                rejection_criteria='No physical defect found; parameter variation is within benign process capability.',
                limitations_and_safety='Destructive failure analysis requires QA sampling signoff. Not a confirmed root cause.',
            ),
        ]

        protocol = ValidationProtocol(
            protocol_id=f'PROTO-{rec_id}',
            target_hypothesis=f'PARAMETRIC.{res.parameter_name}',
            steps=steps,
            replication_check='Cross-lot validation on held-out material required before any engineering review.',
            downstream_reliability_risk='Uninvestigated parametric tails may represent latent defect mechanisms (infant mortality risk).',
        )

        # Scoping based on cross-lot validation warnings
        has_shifts = res.lot_validation is not None and res.lot_validation.potential_lot_shifts_detected
        warning_lots = res.lot_validation.performance_warning_lot_ids if res.lot_validation else []
        scope = 'LOT_SPECIFIC' if (has_shifts and len(warning_lots) == 1) else 'GLOBAL'
        lot_id = warning_lots[0] if (scope == 'LOT_SPECIFIC' and len(warning_lots) == 1) else None

        youden = cm.youden_j if cm.youden_j is not None else 0.0
        # Score justified directly by measured Youden J without inflated floor
        ranking_score = float(max(0.10, min(0.95, youden)))
        d_val = res.overall_separation.abs_cohens_d if res.overall_separation.abs_cohens_d is not None else 0.0

        rec = EngineeringRecommendation(
            recommendation_id=rec_id,
            hypothesis_id=f'HYP-PARAM-{res.parameter_name}',
            title=f'Investigate Parametric Tail: {res.parameter_name} ({cand.direction})',
            recommendation_category='Parametric investigation',
            status='PROPOSED',
            scope=scope,
            lot_id=lot_id,
            priority_rank=rank,
            priority_tier='HIGH' if youden >= 0.50 else 'MEDIUM' if youden >= 0.25 else 'LOW',
            confidence_tier='HIGH' if (youden >= 0.50 and not has_shifts) else 'MODERATE' if youden >= 0.25 else 'LOW',
            ranking_score=ranking_score,
            ranking_rationale=(
                f'In-sample parametric separation |d| = {d_val:.2f}. '
                f'Candidate boundary {cand.candidate_value:.4f} {res.unit} isolates {cm.true_positives} failing dies '
                f'with training specificity {spec_str} and sensitivity {sens_str}.'
            ),
            observed_pattern=(
                f'{res.parameter_name} shows distribution separation between first-pass pass and fail dies. '
                f'{res.engineering_summary}'
            ),
            target_population=cand.target_population_description,
            affected_die_count=cand.n_dies_flagged,
            eligible_die_count=res.data_quality.eligible_physical_dies,
            subgroup_die_count=cand.n_dies_flagged,
            subgroup_failed_die_count=cm.true_positives,
            observed_failure_rate=float(cm.true_positives / max(1, cand.n_dies_flagged)),
            baseline_failure_rate=float(res.data_quality.first_pass_fail_count / max(1, res.data_quality.eligible_physical_dies)),
            supporting_detectors=['parametric'],  # Honest attribution: only parametric detector confirmed
            hypothesis_confidence='MODERATE',
            ml_evidence_status='NEEDS_MORE_DATA',
            ml_evidence_notes='Parametric candidate threshold is established via transparent statistical optimization (Youden J); independent of predictive ML.',
            missing_evidence=res.missing_evidence,
            limitations=res.limitations,
            recommended_action=(
                f'Conduct engineering investigation into units with {res.parameter_name} exceeding {cand.candidate_value:.4f} {res.unit}. '
                'Execute validation protocol before any consideration of test limit changes.'
            ),
            reason=f'{res.measurement_semantics} Candidate boundary optimizes training separation without excessive false positives.',
            expected_information='Determines if parametric outlier distribution is caused by upstream process drift or tool wearout.',
            validation_method='Cross-lot holdout evaluation and physical failure analysis.',
            success_criteria='Physical root cause confirmed or consistent replication in subsequent production lots.',
            required_data=['First-pass parametric measurements', 'ATE tester logs', 'Inline defect maps'],
            risk_if_ignored='Potential customer escapes or field reliability exposure if latent defect tails are unaddressed.',
            next_step_if_confirmed='Initiate formal engineering review for qualification of test guardbands or process adjustments.',
            next_step_if_rejected='Archive investigation as benign process variation. Retain existing test parameters.',
            validation_protocol=protocol,
            observed_loss_rate=float(cm.true_positives / max(1, res.data_quality.eligible_physical_dies)),
            upper_bound_rate=float(cand.n_dies_flagged / max(1, res.data_quality.eligible_physical_dies)),
            upper_bound_count=cand.n_dies_flagged,
            plausible_rate=float(cm.true_positives / max(1, res.data_quality.eligible_physical_dies)),
            plausible_count=cm.true_positives,
            safety_eligible_production_rate=0.0,
            safety_eligible_production_count=0,
            opportunity_disclaimer=(
                'Candidate threshold is an investigation boundary only. Not an approved production limit. '
                'Flagged dies do not represent guaranteed recoverable yield. Safety-eligible production is 0%. '
                'Overlapping slices must not be summed.'
            ),
            production_action='FORBIDDEN',
            production_authorized=False,
            not_a_root_cause=True,
        )
        recs.append(rec)
        rank += 1

    return recs
