# Engine - Stage 1.2
from __future__ import annotations
import math
from typing import Sequence
import numpy as np
import pandas as pd

from yield_improvement.parametric_analysis.contracts import (
    CandidateThreshold,
    ConfusionMatrix,
    LotValidationFold,
    LotValidationSummary,
    ParameterSummaryStatistics,
    ParametricAnalysisReport,
    ParametricAnalysisResult,
    PopulationDataQuality,
    SeparationMetrics,
    ThresholdDirection,
    ThresholdStatus,
)
from yield_improvement.parametric_analysis.extractor import FirstPassDieParametricRecord, ExtractionResult
from yield_improvement.parametric_analysis.registry import PARAMETER_REGISTRY, ParameterDefinition

def _compute_stats(values: Sequence[float]) -> ParameterSummaryStatistics:
    if not values:
        return ParameterSummaryStatistics(
            count=0, available=False, min=None, max=None, mean=None, median=None, std=None,
            p05=None, p25=None, p75=None, p95=None, iqr=None
        )
    arr = np.array([v for v in values if v is not None and not np.isnan(v) and not np.isinf(v)], dtype=float)
    if len(arr) == 0:
        return ParameterSummaryStatistics(
            count=0, available=False, min=None, max=None, mean=None, median=None, std=None,
            p05=None, p25=None, p75=None, p95=None, iqr=None
        )
    p05, p25, med, p75, p95 = np.percentile(arr, [5, 25, 50, 75, 95])
    return ParameterSummaryStatistics(
        count=len(arr),
        available=True,
        min=float(np.min(arr)),
        max=float(np.max(arr)),
        mean=float(np.mean(arr)),
        median=float(med),
        std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        p05=float(p05),
        p25=float(p25),
        p75=float(p75),
        p95=float(p95),
        iqr=float(p75 - p25),
    )

def _compute_separation(pass_vals: Sequence[float], fail_vals: Sequence[float]) -> SeparationMetrics:
    if not pass_vals or not fail_vals:
        return SeparationMetrics(
            mean_difference=None,
            pooled_standard_deviation=None,
            cohens_d=None,
            abs_cohens_d=None,
            distribution_overlap_description='Insufficient sample count to evaluate separation',
            large_effect_size_flag=False,
        )
    p_arr = np.array([v for v in pass_vals if v is not None and not np.isnan(v) and not np.isinf(v)], dtype=float)
    f_arr = np.array([v for v in fail_vals if v is not None and not np.isnan(v) and not np.isinf(v)], dtype=float)
    n_p, n_f = len(p_arr), len(f_arr)
    if n_p < 2 or n_f < 2:
        return SeparationMetrics(
            mean_difference=None,
            pooled_standard_deviation=None,
            cohens_d=None,
            abs_cohens_d=None,
            distribution_overlap_description='Fewer than 2 valid observations in pass or fail groups',
            large_effect_size_flag=False,
        )

    m_p, m_f = float(np.mean(p_arr)), float(np.mean(f_arr))
    s_p = float(np.std(p_arr, ddof=1))
    s_f = float(np.std(f_arr, ddof=1))

    diff = m_f - m_p
    pooled_s = math.sqrt(((n_p - 1) * s_p**2 + (n_f - 1) * s_f**2) / (n_p + n_f - 2)) if (n_p + n_f > 2) else 1.0
    d = diff / pooled_s if pooled_s > 1e-9 else 0.0
    abs_d = abs(d)

    if abs_d >= 0.8:
        overlap_desc = f'Large effect size (|d| = {abs_d:.2f} >= 0.80). Substantial distribution separation.'
        large_flag = True
    elif abs_d >= 0.4:
        overlap_desc = f'Moderate effect size (|d| = {abs_d:.2f} >= 0.40). Noticeable distribution shift.'
        large_flag = True
    elif abs_d >= 0.2:
        overlap_desc = f'Weak effect size (|d| = {abs_d:.2f} >= 0.20). Substantial distribution overlap.'
        large_flag = False
    else:
        overlap_desc = f'Negligible effect size (|d| = {abs_d:.2f} < 0.20). Distributions virtually overlapping.'
        large_flag = False

    return SeparationMetrics(
        mean_difference=diff,
        pooled_standard_deviation=pooled_s,
        cohens_d=d,
        abs_cohens_d=abs_d,
        distribution_overlap_description=overlap_desc,
        large_effect_size_flag=large_flag,
    )

def _evaluate_cutpoint(
    measurements: Sequence[float],
    targets: Sequence[bool],
    cut: float,
    direction: ThresholdDirection,
    population_desc: str = 'Measured first-pass dies',
) -> ConfusionMatrix:
    arr_m = np.array(measurements, dtype=float)
    arr_t = np.array(targets, dtype=bool)

    if direction == 'UPPER_BOUND':
        pred = arr_m > cut
    elif direction == 'LOWER_BOUND':
        pred = arr_m < cut
    else:
        pred = np.zeros_like(arr_t, dtype=bool)

    tp = int(np.sum(pred & arr_t))
    fp = int(np.sum(pred & (~arr_t)))
    fn = int(np.sum((~pred) & arr_t))
    tn = int(np.sum((~pred) & (~arr_t)))

    n_pos = tp + fn
    n_neg = tn + fp
    n_pred_pos = tp + fp
    total_eval = len(arr_m)

    sens = (tp / n_pos) if n_pos > 0 else None
    spec = (tn / n_neg) if n_neg > 0 else None
    prec = (tp / n_pred_pos) if n_pred_pos > 0 else None
    rec = sens
    youden = (sens + spec - 1.0) if (sens is not None and spec is not None) else None

    return ConfusionMatrix(
        evaluated_population_description=population_desc,
        total_evaluated_count=total_eval,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        sensitivity=float(sens) if sens is not None else None,
        specificity=float(spec) if spec is not None else None,
        precision=float(prec) if prec is not None else None,
        recall=float(rec) if rec is not None else None,
        youden_j=float(youden) if youden is not None else None,
    )

def _optimize_candidate_threshold(
    records: list[FirstPassDieParametricRecord],
    target_failure_code: str | None,
    direction: ThresholdDirection,
) -> tuple[float | None, ConfusionMatrix | None]:
    if not records:
        return None, None

    if direction == 'BAND':
        return None, None

    valid_recs = [r for r in records if r.measurement is not None and not np.isnan(r.measurement) and not np.isinf(r.measurement)]
    if len(valid_recs) < 30:
        return None, None

    measurements = [r.measurement for r in valid_recs]
    if max(measurements) - min(measurements) < 1e-9:
        return None, None

    if target_failure_code:
        targets = [(r.failure_code == target_failure_code) for r in valid_recs]
    else:
        targets = [r.first_pass_failed for r in valid_recs]

    n_targets = sum(targets)
    n_non_targets = len(targets) - n_targets
    # Mandatory requirement: at least 15 target failures and 30 non-targets
    if n_targets < 15 or n_non_targets < 30:
        return None, None

    best_j = -1.0
    best_cut = None
    best_cm = None

    candidate_grid = np.unique(np.percentile(measurements, np.linspace(40, 98, 59)))
    for cut in candidate_grid:
        cm = _evaluate_cutpoint(measurements, targets, cut, direction, population_desc='Training dies with valid measurements')
        if cm.sensitivity is not None and cm.specificity is not None:
            if cm.sensitivity >= 0.25 and cm.specificity >= 0.70:
                if cm.youden_j is not None and cm.youden_j > best_j:
                    best_j = cm.youden_j
                    best_cut = float(cut)
                    best_cm = cm

    return best_cut, best_cm

def _run_loo_lot_validation(
    records: list[FirstPassDieParametricRecord],
    target_failure_code: str | None,
    direction: ThresholdDirection,
    lots: list[str],
) -> LotValidationSummary:
    folds: list[LotValidationFold] = []

    for held_out in lots:
        train_recs = [r for r in records if r.lot_id != held_out]
        test_recs = [r for r in records if r.lot_id == held_out]

        train_m = [r for r in train_recs if r.measurement is not None and not np.isnan(r.measurement)]
        if target_failure_code:
            train_t_count = sum(1 for r in train_m if r.failure_code == target_failure_code)
        else:
            train_t_count = sum(1 for r in train_m if r.first_pass_failed)
        train_nt_count = len(train_m) - train_t_count

        # Candidate selection strictly on train_recs
        cut, _ = _optimize_candidate_threshold(train_recs, target_failure_code, direction)
        train_established = cut is not None

        test_m = [r.measurement for r in test_recs if r.measurement is not None and not np.isnan(r.measurement)]
        if target_failure_code:
            test_t = [(r.failure_code == target_failure_code) for r in test_recs if r.measurement is not None and not np.isnan(r.measurement)]
        else:
            test_t = [r.first_pass_failed for r in test_recs if r.measurement is not None and not np.isnan(r.measurement)]

        train_lot_ids = [l for l in lots if l != held_out]
        n_test_fails = sum(test_t)
        n_test_non_targets = len(test_m) - n_test_fails

        if not train_established:
            # Report INSUFFICIENT_TRAIN_DATA cleanly with no evaluated threshold performance
            folds.append(
                LotValidationFold(
                    held_out_lot_id=held_out,
                    train_lot_ids=train_lot_ids,
                    train_candidate_established=False,
                    train_candidate_value=None,
                    train_target_fails=train_t_count,
                    train_non_target_count=train_nt_count,
                    held_out_die_count=len(test_m),
                    held_out_target_fails=n_test_fails,
                    held_out_non_target_count=n_test_non_targets,
                    held_out_true_positives=0,
                    held_out_false_positives=0,
                    held_out_false_negatives=0,
                    held_out_true_negatives=0,
                    held_out_sensitivity=None,
                    held_out_specificity=None,
                    fold_status='INSUFFICIENT_TRAIN_DATA',
                )
            )
            continue

        cm = _evaluate_cutpoint(test_m, test_t, cut, direction, population_desc=f'Held-out lot {held_out} measured dies')
        fold_status = 'NO_HELD_OUT_TARGET_FAILURES' if n_test_fails == 0 else 'EVALUATED'

        folds.append(
            LotValidationFold(
                held_out_lot_id=held_out,
                train_lot_ids=train_lot_ids,
                train_candidate_established=True,
                train_candidate_value=float(cut),
                train_target_fails=train_t_count,
                train_non_target_count=train_nt_count,
                held_out_die_count=len(test_m),
                held_out_target_fails=n_test_fails,
                held_out_non_target_count=n_test_non_targets,
                held_out_true_positives=cm.true_positives,
                held_out_false_positives=cm.false_positives,
                held_out_false_negatives=cm.false_negatives,
                held_out_true_negatives=cm.true_negatives,
                held_out_sensitivity=cm.sensitivity,
                held_out_specificity=cm.specificity,
                fold_status=fold_status,
            )
        )

    warning_lots = []
    insufficient_train_lots = []
    for f in folds:
        if f.fold_status == 'INSUFFICIENT_TRAIN_DATA':
            insufficient_train_lots.append(f.held_out_lot_id)
        elif f.fold_status == 'EVALUATED':
            if f.held_out_specificity is not None and f.held_out_specificity < 0.65:
                warning_lots.append(f.held_out_lot_id)
            elif f.held_out_target_fails >= 5 and f.held_out_sensitivity is not None and f.held_out_sensitivity < 0.20:
                warning_lots.append(f.held_out_lot_id)

    has_shifts = len(warning_lots) > 0 or len(insufficient_train_lots) > 0
    warning_all = sorted(set(warning_lots + insufficient_train_lots))

    if insufficient_train_lots and not warning_lots:
        gen_desc = (
            f"Fold(s) holding out {insufficient_train_lots} had insufficient target failures in training material (<15) "
            "to establish a candidate threshold (INSUFFICIENT_TRAIN_DATA). While held-out baseline lots maintain high specificity, "
            "cross-lot sensitivity cannot be confirmed due to zero or near-zero held-out target failures in baseline lots."
        )
    elif has_shifts:
        gen_desc = (
            f"Cross-lot performance warnings observed on held-out lot(s) {warning_all}. "
            "Candidate thresholds are investigation-only boundaries and must not be considered generally validated across shifted lots."
        )
    else:
        gen_desc = (
            "Candidate threshold maintains consistent specificity across evaluated baseline lots, "
            "but generalization across lots remains unproven due to limited excursion samples."
        )

    return LotValidationSummary(
        evaluation_strategy='Leave-One-Out Lot Cross-Validation (5 folds)',
        folds=folds,
        generalization_assessment=gen_desc,
        potential_lot_shifts_detected=has_shifts,
        performance_warning_lot_ids=warning_all,
    )

def analyze_parameter(
    param_def: ParameterDefinition,
    records: list[FirstPassDieParametricRecord],
    total_eligible_dies: int,
    lots: list[str],
    wafers: list[str],
    retests_excluded: int,
) -> ParametricAnalysisResult:
    all_vals = [r.measurement for r in records if r.measurement is not None and not np.isnan(r.measurement)]
    pass_vals = [r.measurement for r in records if (not r.first_pass_failed) and r.measurement is not None and not np.isnan(r.measurement)]
    fail_vals = [r.measurement for r in records if r.first_pass_failed and r.measurement is not None and not np.isnan(r.measurement)]

    n_measured = len(all_vals)
    missing_measurements = max(0, total_eligible_dies - n_measured)

    target_code = param_def.target_failure_code
    spec_fail_vals = [r.measurement for r in records if (r.failure_code == target_code) and r.measurement is not None and not np.isnan(r.measurement)] if target_code else []

    overall_stats = _compute_stats(all_vals)
    pass_stats = _compute_stats(pass_vals)
    fail_stats = _compute_stats(fail_vals)
    spec_stats = _compute_stats(spec_fail_vals) if target_code and spec_fail_vals else None

    overall_sep = _compute_separation(pass_vals, fail_vals)
    spec_sep = _compute_separation(pass_vals, spec_fail_vals) if (target_code and spec_fail_vals) else None

    n_target_code_fails = len(spec_fail_vals) if target_code else 0
    n_non_targets = n_measured - n_target_code_fails

    data_qual = PopulationDataQuality(
        eligible_physical_dies=total_eligible_dies,
        valid_first_pass_measurements=n_measured,
        missing_measurements=missing_measurements,
        retest_measurements_excluded=retests_excluded,
        quarantined_attempts_count=0,
        quarantined_dies_count=0,
        first_pass_pass_count=len(pass_vals),
        first_pass_fail_count=len(fail_vals),
        target_failure_code_count=n_target_code_fails,
        non_target_count=n_non_targets,
        n_lots_covered=len(lots),
        n_wafers_covered=len(wafers),
        data_quality_warnings=[f'{missing_measurements} eligible physical dies are missing measurements for {param_def.parameter_name}'] if missing_measurements > 0 else [],
    )

    primary_sep = spec_sep if (spec_sep is not None and spec_sep.abs_cohens_d is not None and (overall_sep.abs_cohens_d is None or spec_sep.abs_cohens_d > overall_sep.abs_cohens_d)) else overall_sep
    active_target_code = target_code if (spec_sep is not None and spec_sep.abs_cohens_d is not None and spec_sep.abs_cohens_d >= 0.40) else None

    candidate = None
    lot_val = None
    threshold_status: ThresholdStatus = 'NO_THRESHOLD_ESTABLISHED'
    missing_evidence: list[str] = []
    limitations: list[str] = [
        'Advisory statistical investigation only. Not an approved production limit.',
        'Dataset records only primary failure code; simultaneous co-fail mechanisms cannot be fully isolated.',
        'No authoritative production specifications exist; synthetic generator reference only.',
    ]

    if param_def.default_direction == 'BAND':
        threshold_status = 'INSUFFICIENT_EVIDENCE'
        limitations.append('Two-sided BAND threshold optimization is not currently supported; returns INSUFFICIENT_EVIDENCE.')
        eng_summary = f'{param_def.parameter_name} is a two-sided parameter. BAND threshold estimation is not supported without dual-boundary optimization.'
    elif not param_def.analysis_eligible or primary_sep.abs_cohens_d is None or primary_sep.abs_cohens_d < 0.25:
        threshold_status = 'INSUFFICIENT_EVIDENCE'
        d_val = primary_sep.abs_cohens_d if primary_sep.abs_cohens_d is not None else 0.0
        limitations.append(f'Parametric distribution exhibits heavy overlap with passing dies (|d| = {d_val:.2f} < 0.25).')
        missing_evidence.append('No statistically meaningful failure separation observed in V2 dataset.')
        eng_summary = f'{param_def.parameter_name} distributions for passing and failing dies overlap substantially (|d| = {d_val:.2f}). No candidate threshold is justified.'
    else:
        best_cut, best_cm = _optimize_candidate_threshold(records, active_target_code, param_def.default_direction)
        if best_cut is not None and best_cm is not None:
            threshold_status = 'INVESTIGATION_CANDIDATE_ONLY'
            n_flagged = best_cm.true_positives + best_cm.false_positives

            candidate = CandidateThreshold(
                candidate_value=best_cut,
                direction=param_def.default_direction,
                status='INVESTIGATION_CANDIDATE_ONLY',
                target_population_description=(
                    f'First-pass dies with {param_def.parameter_name} > {best_cut:.4f} {param_def.unit}'
                    if param_def.default_direction == 'UPPER_BOUND'
                    else f'First-pass dies with {param_def.parameter_name} < {best_cut:.4f} {param_def.unit}'
                ),
                target_failure_code=active_target_code,
                selection_method='Youden J Optimization on measured training distribution',
                selection_objective='Maximize Sensitivity + Specificity - 1 subject to Sens >= 0.25 and Spec >= 0.70',
                n_dies_flagged=n_flagged,
                flagged_share_of_measured=float(n_flagged / n_measured) if n_measured > 0 else 0.0,
                flagged_share_of_all_eligible=float(n_flagged / total_eligible_dies) if total_eligible_dies > 0 else 0.0,
                training_confusion_matrix=best_cm,
                uncertainty_notes=f'Evaluated on {n_measured} measured physical dies (out of {total_eligible_dies} total eligible dies) across {len(lots)} lots. Target failure count: {sum(1 for r in records if r.failure_code == active_target_code) if active_target_code else len(fail_vals)}.',
                disclaimer='INVESTIGATION_CANDIDATE_ONLY. Not an approved production limit. Production action is FORBIDDEN. Safety-eligible production is 0.0%.',
            )

            lot_val = _run_loo_lot_validation(records, active_target_code, param_def.default_direction, lots)
            if lot_val.potential_lot_shifts_detected:
                limitations.append(f'Performance varies across lots: potential lot shift or insufficient training excursion in {lot_val.performance_warning_lot_ids}.')

            d_val = primary_sep.abs_cohens_d if primary_sep.abs_cohens_d is not None else 0.0
            sens_val = best_cm.sensitivity if best_cm.sensitivity is not None else 0.0
            spec_val = best_cm.specificity if best_cm.specificity is not None else 0.0
            eng_summary = (
                f'{param_def.parameter_name} shows significant separation (|d| = {d_val:.2f}). '
                f'Candidate boundary {best_cut:.4f} {param_def.unit} ({param_def.default_direction}) flags {n_flagged} dies in-sample '
                f'(flagged share of measured: {n_flagged/max(1,n_measured):.1%}, flagged share of eligible: {n_flagged/max(1,total_eligible_dies):.1%}) '
                f'with training sensitivity {sens_val:.1%} and specificity {spec_val:.1%}. '
                'Strictly for engineering investigation.'
            )
        else:
            threshold_status = 'INSUFFICIENT_EVIDENCE'
            limitations.append('Candidate cutpoint could not meet minimal sensitivity (25%) and specificity (70%) criteria.')
            missing_evidence.append('Sample size of specific test failures is too small for stable thresholding.')
            d_val = primary_sep.abs_cohens_d if primary_sep.abs_cohens_d is not None else 0.0
            eng_summary = f'{param_def.parameter_name} has separation (|d| = {d_val:.2f}), but target failure counts are too low to estimate a stable threshold.'

    return ParametricAnalysisResult(
        parameter_name=param_def.parameter_name,
        source_field=param_def.source_field,
        unit=param_def.unit,
        measurement_semantics=param_def.measurement_semantics,
        spec_provenance=param_def.spec_provenance,
        synthetic_reference_lower=param_def.synthetic_reference_lower,
        synthetic_reference_upper=param_def.synthetic_reference_upper,
        spec_disclaimer='No authoritative production specifications exist in repository. Reference limits shown are synthetic generator inputs only.',
        data_quality=data_qual,
        overall_distribution=overall_stats,
        pass_distribution=pass_stats,
        fail_distribution=fail_stats,
        specific_failure_distribution=spec_stats,
        target_failure_code=target_code,
        overall_separation=overall_sep,
        specific_failure_separation=spec_sep,
        threshold_status=threshold_status,
        candidate_threshold=candidate,
        lot_validation=lot_val,
        missing_evidence=missing_evidence,
        limitations=limitations,
        engineering_summary=eng_summary,
    )

def run_parametric_analysis(
    extraction: ExtractionResult,
    dataset_id: str,
) -> ParametricAnalysisReport:
    results: list[ParametricAnalysisResult] = []

    for param_name, param_def in PARAMETER_REGISTRY.items():
        records = extraction.records_by_param.get(param_name, [])
        res = analyze_parameter(
            param_def=param_def,
            records=records,
            total_eligible_dies=extraction.eligible_dies_count,
            lots=extraction.lots_present,
            wafers=extraction.wafers_present,
            retests_excluded=extraction.retests_excluded_count // max(1, len(PARAMETER_REGISTRY)),
        )
        results.append(res)

    return ParametricAnalysisReport(
        dataset_id=dataset_id,
        generated_at=pd.Timestamp.now(tz='UTC').isoformat(),
        n_parameters_analyzed=len(results),
        results=results,
        extraction_warnings=extraction.warnings,
        quarantined_attempts_count=extraction.quarantined_attempts_count,
        safety_invariants={
            'production_action': 'FORBIDDEN',
            'production_authorized': False,
            'safety_eligible_production': 0.0,
        },
        production_action='FORBIDDEN',
        production_authorized=False,
        safety_eligible_production_rate=0.0,
    )
