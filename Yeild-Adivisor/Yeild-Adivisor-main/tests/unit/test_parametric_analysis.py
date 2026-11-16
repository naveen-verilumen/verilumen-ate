# Substantive Regression Tests for Stage 1.1 Parametric Analysis
import pytest
import numpy as np
from yield_improvement.config.loader import load_config
from yield_improvement.ingestion.loader import load_die_attempts, load_parametric_measurements
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement
from yield_improvement.parametric_analysis import (
    CandidateThreshold,
    ParametricAnalysisReport,
    ParametricAnalysisResult,
    PARAMETER_REGISTRY,
    extract_first_pass_parametric_data,
    run_parametric_analysis,
    build_parametric_recommendations,
)
from yield_improvement.parametric_analysis.engine import _optimize_candidate_threshold, _evaluate_cutpoint

@pytest.fixture(scope='module')
def setup_canonical_data():
    cfg = load_config()
    attempts_res = load_die_attempts('data/synthetic/agent_visible/yi_synthetic_v2/die_attempts.csv', cfg)
    param_res = load_parametric_measurements('data/synthetic/agent_visible/yi_synthetic_v2/parametric_measurements.csv', cfg)
    return attempts_res.attempts, param_res.parametric

def test_canonical_extraction_counts(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)

    assert extraction.eligible_dies_count == 2500
    assert extraction.first_pass_pass_count == 2249
    assert extraction.first_pass_fail_count == 251
    assert extraction.retests_excluded_count == 480
    assert extraction.quarantined_attempts_count == 0
    assert extraction.quarantined_dies_count == 0
    assert len(extraction.warnings) == 0

def test_extraction_quarantines_conflicting_metadata(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    # Create conflicting attempt: is_first_attempt=True but attempt_number=2
    bad_attempt = DieAttempt(
        attempt_id='BAD-ATT-001',
        lot_id='L001',
        wafer_id='W01',
        die_id='D999',
        product_id='DEV_A',
        step_id='WS_SORT',
        is_first_attempt=True,
        attempt_number=2,  # Conflicting!
        pass_fail='FAIL',
    )
    bad_param = ParametricMeasurement(
        attempt_id='BAD-ATT-001',
        parameter_name='IDDQ',
        measurement=60.0,
        unit='uA',
    )
    test_attempts = list(attempts) + [bad_attempt]
    test_param = list(parametric) + [bad_param]

    extraction = extract_first_pass_parametric_data(test_attempts, test_param)
    assert extraction.quarantined_attempts_count >= 1
    assert extraction.quarantined_dies_count >= 1
    assert any('conflicting first-pass metadata' in w for w in extraction.warnings)
    # The bad die measurement must NOT be in IDDQ records
    assert not any(r.attempt_id == 'BAD-ATT-001' for r in extraction.records_by_param.get('IDDQ', []))

def test_extraction_quarantines_duplicate_physical_dies(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    # Duplicate physical die L001/W01/D001
    dup_attempt = DieAttempt(
        attempt_id='DUP-ATT-001',
        lot_id='L001',
        wafer_id='W01',
        die_id='D001',  # D001 already exists in canonical V2
        product_id='DEV_A',
        step_id='WS_SORT',
        is_first_attempt=True,
        attempt_number=1,
        pass_fail='PASS',
    )
    test_attempts = list(attempts) + [dup_attempt]
    extraction = extract_first_pass_parametric_data(test_attempts, parametric)

    assert extraction.quarantined_dies_count >= 1
    assert any('duplicate first-pass attempts' in w for w in extraction.warnings)
    # D001 must be quarantined and completely excluded from eligible dies
    assert not any(r.die_id == 'D001' and r.lot_id == 'L001' and r.wafer_id == 'W01' for r in extraction.records_by_param.get('IDDQ', []))
    assert extraction.eligible_dies_count == 2499

def test_extraction_orphan_and_duplicate_parameters():
    attempts = [
        DieAttempt(
            attempt_id='ATT-01', lot_id='L001', wafer_id='W01', die_id='D001',
            product_id='DEV_A', step_id='WS_SORT', is_first_attempt=True, attempt_number=1, pass_fail='PASS'
        )
    ]
    parametric = [
        ParametricMeasurement(attempt_id='ATT-01', parameter_name='IDDQ', measurement=30.0, unit='uA'),
        ParametricMeasurement(attempt_id='ATT-01', parameter_name='IDDQ', measurement=35.0, unit='uA'), # Duplicate param measurement
        ParametricMeasurement(attempt_id='ATT-ORPHAN', parameter_name='IDDQ', measurement=50.0, unit='uA'), # Orphan attempt_id
        ParametricMeasurement(attempt_id='ATT-01', parameter_name='VMIN', measurement=float('nan'), unit='V'), # Non-finite measurement
    ]
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    assert extraction.eligible_dies_count == 1
    assert len(extraction.records_by_param['IDDQ']) == 1 # Only first measurement kept
    assert len(extraction.records_by_param.get('VMIN', [])) == 0 # NaN rejected
    assert any('Duplicate measurement' in w for w in extraction.warnings)
    assert any('orphan attempt_id' in w for w in extraction.warnings)
    assert any('non-finite' in w for w in extraction.warnings)

def test_unsupported_band_direction_returns_none():
    cut, cm = _optimize_candidate_threshold([], None, 'BAND')
    assert cut is None
    assert cm is None

def test_held_out_labels_do_not_affect_training_cutpoint(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    iddq_recs = extraction.records_by_param['IDDQ']

    # Select candidate on lots L001-L004 (held out L005)
    train_recs = [r for r in iddq_recs if r.lot_id != 'L005']
    cut1, _ = _optimize_candidate_threshold(train_recs, 'IDDQ', 'UPPER_BOUND')

    # Modify labels of held-out lot L005 arbitrarily
    test_recs_flipped = [
        r if r.lot_id != 'L005' else
        type(r)(
            attempt_id=r.attempt_id, lot_id=r.lot_id, wafer_id=r.wafer_id, die_id=r.die_id,
            parameter_name=r.parameter_name, measurement=r.measurement, unit=r.unit,
            first_pass_failed=not r.first_pass_failed, failure_code='IDDQ', condition_id=r.condition_id,
            temperature_c=r.temperature_c, voltage_v=r.voltage_v
        )
        for r in iddq_recs
    ]
    train_recs_2 = [r for r in test_recs_flipped if r.lot_id != 'L005']
    cut2, _ = _optimize_candidate_threshold(train_recs_2, 'IDDQ', 'UPPER_BOUND')

    assert cut1 is not None
    assert cut1 == cut2, 'Training cutpoint must not change when held-out lot labels are altered'

def test_held_out_lot_with_zero_target_fails_handled_cleanly():
    cm = _evaluate_cutpoint([10.0, 20.0, 30.0], [False, False, False], 25.0, 'UPPER_BOUND')
    assert cm.true_positives == 0
    assert cm.false_negatives == 0
    assert cm.sensitivity is None  # 0/0 represented as None, not NaN or 0.0 division error
    assert cm.specificity == 2.0 / 3.0

def test_constant_valued_and_small_class_rejected():
    from yield_improvement.parametric_analysis.extractor import FirstPassDieParametricRecord
    # Constant values
    const_recs = [
        FirstPassDieParametricRecord('A', 'L1', 'W1', f'D{i}', 'P', 5.0, 'V', True, 'CODE', 'NONE', None, None)
        for i in range(50)
    ]
    cut, cm = _optimize_candidate_threshold(const_recs, 'CODE', 'UPPER_BOUND')
    assert cut is None

    # Small positive class (< 15 targets)
    few_recs = [
        FirstPassDieParametricRecord('A', 'L1', 'W1', f'D{i}', 'P', float(i), 'V', (i < 5), 'CODE', 'NONE', None, None)
        for i in range(50)
    ]
    cut2, cm2 = _optimize_candidate_threshold(few_recs, 'CODE', 'UPPER_BOUND')
    assert cut2 is None

def test_recommendation_bridge_honest_provenance(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')
    recs = build_parametric_recommendations(report)

    for r in recs:
        # Check honest detector attribution
        assert r.supporting_detectors == ['parametric']
        assert 'near_limit' not in r.supporting_detectors
        assert r.production_action == 'FORBIDDEN'
        assert r.production_authorized is False
        assert r.safety_eligible_production_rate == 0.0
        assert r.safety_eligible_production_count == 0
        assert r.not_a_root_cause is True
        assert 'INVESTIGATION_CANDIDATE_ONLY' in r.opportunity_disclaimer or 'investigation boundary only' in r.opportunity_disclaimer

def test_loo_fold_insufficient_train_data(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')

    # In canonical yi_synthetic_v2, L004 holds 27 of 38 IDDQ failures and 29 of 39 VMIN failures.
    # When L004 is held out, training material has only 11 IDDQ and 10 VMIN failures (< 15 minimum).
    iddq_res = next(r for r in report.results if r.parameter_name == 'IDDQ')
    assert iddq_res.lot_validation is not None
    fold_l004 = next(f for f in iddq_res.lot_validation.folds if f.held_out_lot_id == 'L004')
    assert fold_l004.train_candidate_established is False
    assert fold_l004.train_candidate_value is None
    assert fold_l004.fold_status == 'INSUFFICIENT_TRAIN_DATA'
    assert fold_l004.held_out_sensitivity is None
    assert fold_l004.held_out_specificity is None
    assert fold_l004.held_out_true_positives == 0

    vmin_res = next(r for r in report.results if r.parameter_name == 'VMIN')
    assert vmin_res.lot_validation is not None
    fold_vmin_l004 = next(f for f in vmin_res.lot_validation.folds if f.held_out_lot_id == 'L004')
    assert fold_vmin_l004.train_candidate_established is False
    assert fold_vmin_l004.fold_status == 'INSUFFICIENT_TRAIN_DATA'

def test_incomplete_parameter_dataset_population_denominators(setup_canonical_data):
    from yield_improvement.parametric_analysis.engine import analyze_parameter
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)

    # Total physical dies eligible is 2500
    assert extraction.eligible_dies_count == 2500
    iddq_recs = extraction.records_by_param['IDDQ']
    assert len(iddq_recs) == 2500

    # Simulate an incomplete parameter dataset by retaining only 2000 measurements (500 missing)
    incomplete_iddq_recs = iddq_recs[:2000]
    iddq_def = PARAMETER_REGISTRY['IDDQ']

    res = analyze_parameter(
        param_def=iddq_def,
        records=incomplete_iddq_recs,
        total_eligible_dies=extraction.eligible_dies_count,
        lots=extraction.lots_present,
        wafers=extraction.wafers_present,
        retests_excluded=0,
    )

    # Strictly check population data quality separation
    assert res.data_quality.eligible_physical_dies == 2500
    assert res.data_quality.valid_first_pass_measurements == 2000
    assert res.data_quality.missing_measurements == 500
    assert len(res.data_quality.data_quality_warnings) == 1
    assert '500 eligible physical dies are missing measurements for IDDQ' in res.data_quality.data_quality_warnings[0]

    # Candidate threshold flagged share of measured vs all eligible
    assert res.candidate_threshold is not None
    cand = res.candidate_threshold
    assert cand.n_dies_flagged > 0
    assert cand.flagged_share_of_measured == pytest.approx(cand.n_dies_flagged / 2000, rel=1e-5)
    assert cand.flagged_share_of_all_eligible == pytest.approx(cand.n_dies_flagged / 2500, rel=1e-5)
    assert cand.flagged_share_of_measured > cand.flagged_share_of_all_eligible

def test_exhaustive_confusion_matrix_reconciliation(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')

    for r in report.results:
        if r.candidate_threshold is not None:
            cand = r.candidate_threshold
            cm = cand.training_confusion_matrix
            # Assert TP + FP + FN + TN == total_evaluated_count == valid_first_pass_measurements
            assert cm.true_positives + cm.false_positives + cm.false_negatives + cm.true_negatives == cm.total_evaluated_count
            assert cm.total_evaluated_count == r.data_quality.valid_first_pass_measurements
            # Flagged dies count must strictly equal TP + FP
            assert cand.n_dies_flagged == cm.true_positives + cm.false_positives
            # Sensitivity must be TP / (TP + FN)
            target_count = cm.true_positives + cm.false_negatives
            assert target_count > 0
            assert cm.sensitivity == pytest.approx(cm.true_positives / target_count, rel=1e-5)
            # Specificity must be TN / (TN + FP)
            non_target_count = cm.true_negatives + cm.false_positives
            assert non_target_count > 0
            assert cm.specificity == pytest.approx(cm.true_negatives / non_target_count, rel=1e-5)

        if r.lot_validation is not None:
            for f in r.lot_validation.folds:
                if f.train_candidate_established:
                    f_sum = f.held_out_true_positives + f.held_out_false_positives + f.held_out_false_negatives + f.held_out_true_negatives
                    assert f_sum == f.held_out_die_count
                    if f.held_out_target_fails > 0:
                        assert f.held_out_sensitivity == pytest.approx(f.held_out_true_positives / f.held_out_target_fails, rel=1e-5)
                    else:
                        assert f.held_out_sensitivity is None  # 0 target fails must yield None
                    held_out_non_targets = f.held_out_die_count - f.held_out_target_fails
                    if held_out_non_targets > 0:
                        assert f.held_out_specificity == pytest.approx(f.held_out_true_negatives / held_out_non_targets, rel=1e-5)
                else:
                    assert f.fold_status == 'INSUFFICIENT_TRAIN_DATA'
                    assert f.held_out_sensitivity is None
                    assert f.held_out_specificity is None
                    assert f.held_out_true_positives == 0
                    assert f.held_out_false_positives == 0

def test_missing_or_invalid_measurements_are_not_classified(setup_canonical_data):
    from yield_improvement.parametric_analysis.extractor import FirstPassDieParametricRecord
    from yield_improvement.parametric_analysis.engine import _evaluate_cutpoint

    # Create dummy records with NaN, Inf, and None
    recs = [
        FirstPassDieParametricRecord('A1', 'L1', 'W1', 'D1', 'IDDQ', np.nan, 'uA', True, 'IDDQ', 'NONE', None, None),
        FirstPassDieParametricRecord('A2', 'L1', 'W1', 'D2', 'IDDQ', np.inf, 'uA', False, None, 'NONE', None, None),
        FirstPassDieParametricRecord('A3', 'L1', 'W1', 'D3', 'IDDQ', -np.inf, 'uA', False, None, 'NONE', None, None),
        FirstPassDieParametricRecord('A4', 'L1', 'W1', 'D4', 'IDDQ', None, 'uA', True, 'IDDQ', 'NONE', None, None),
        FirstPassDieParametricRecord('A5', 'L1', 'W1', 'D5', 'IDDQ', 50.0, 'uA', True, 'IDDQ', 'NONE', None, None),
        FirstPassDieParametricRecord('A6', 'L1', 'W1', 'D6', 'IDDQ', 20.0, 'uA', False, None, 'NONE', None, None),
    ]

    valid_vals = [r.measurement for r in recs if r.measurement is not None and not np.isnan(r.measurement) and not np.isinf(r.measurement)]
    valid_targets = [r.first_pass_failed for r in recs if r.measurement is not None and not np.isnan(r.measurement) and not np.isinf(r.measurement)]

    assert len(valid_vals) == 2
    cm = _evaluate_cutpoint(valid_vals, valid_targets, 30.0, 'UPPER_BOUND', population_desc='Valid test')
    assert cm.total_evaluated_count == 2
    assert cm.true_positives == 1
    assert cm.false_positives == 0
    assert cm.false_negatives == 0
    assert cm.true_negatives == 1

def test_stage_1_4_independent_class_count_invariants(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')

    for r in report.results:
        if r.candidate_threshold is None:
            continue
        ct = r.candidate_threshold
        cm = ct.training_confusion_matrix
        code = r.target_failure_code
        all_recs = extraction.records_by_param[r.parameter_name]

        # 1. In-sample independent counts
        actual_target_fails = sum(1 for rec in all_recs if rec.failure_code == code)
        actual_non_targets = sum(1 for rec in all_recs if rec.failure_code != code)
        assert cm.true_positives + cm.false_negatives == actual_target_fails
        assert cm.false_positives + cm.true_negatives == actual_non_targets
        assert cm.true_positives + cm.false_positives + cm.false_negatives + cm.true_negatives == cm.total_evaluated_count
        assert cm.total_evaluated_count == len(all_recs)

        # 2. LOO folds independent counts
        assert r.lot_validation is not None
        for f in r.lot_validation.folds:
            held_out_recs = [rec for rec in all_recs if rec.lot_id == f.held_out_lot_id]
            train_recs = [rec for rec in all_recs if rec.lot_id != f.held_out_lot_id]

            expected_train_t = sum(1 for rec in train_recs if rec.failure_code == code)
            expected_train_nt = sum(1 for rec in train_recs if rec.failure_code != code)
            expected_held_out_t = sum(1 for rec in held_out_recs if rec.failure_code == code)
            expected_held_out_nt = sum(1 for rec in held_out_recs if rec.failure_code != code)

            assert f.train_target_fails == expected_train_t
            assert f.train_non_target_count == expected_train_nt
            assert f.held_out_die_count == len(held_out_recs)
            assert f.held_out_target_fails == expected_held_out_t
            assert f.held_out_non_target_count == expected_held_out_nt

            if f.train_candidate_established:
                assert f.train_target_fails >= 15
                assert f.train_non_target_count >= 30
                assert f.held_out_true_positives + f.held_out_false_negatives == expected_held_out_t
                assert f.held_out_false_positives + f.held_out_true_negatives == expected_held_out_nt
                assert (
                    f.held_out_true_positives + f.held_out_false_positives +
                    f.held_out_false_negatives + f.held_out_true_negatives
                ) == f.held_out_die_count

                if expected_held_out_t > 0:
                    assert f.held_out_sensitivity == pytest.approx(f.held_out_true_positives / expected_held_out_t, rel=1e-5)
                else:
                    assert f.held_out_sensitivity is None
                    assert f.fold_status == 'NO_HELD_OUT_TARGET_FAILURES'

                if expected_held_out_nt > 0:
                    assert f.held_out_specificity == pytest.approx(f.held_out_true_negatives / expected_held_out_nt, rel=1e-5)
            else:
                assert f.fold_status == 'INSUFFICIENT_TRAIN_DATA'
                assert f.train_target_fails < 15
                assert f.held_out_sensitivity is None
                assert f.held_out_specificity is None
                assert f.held_out_true_positives == 0
                assert f.held_out_false_positives == 0
                assert f.held_out_false_negatives == 0
                assert f.held_out_true_negatives == 0

def test_vmin_l001_reproducible_ground_truth(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')

    vmin_res = next(r for r in report.results if r.parameter_name == 'VMIN')
    fold_l001 = next(f for f in vmin_res.lot_validation.folds if f.held_out_lot_id == 'L001')

    # Independent ground truth assertion on VMIN L001 fold
    assert fold_l001.train_candidate_established is True
    assert fold_l001.train_candidate_value == pytest.approx(0.8103534, rel=1e-5)
    assert fold_l001.train_target_fails == 35  # L002(0) + L003(2) + L004(29) + L005(4)
    assert fold_l001.train_non_target_count == 1965
    assert fold_l001.held_out_die_count == 500
    assert fold_l001.held_out_target_fails == 4
    assert fold_l001.held_out_non_target_count == 496

    # In L001, all 4 VMIN failures have measurement <= 0.633V (mean 0.6015V), below training candidate 0.8104V
    assert fold_l001.held_out_true_positives == 0
    assert fold_l001.held_out_false_negatives == 4
    assert fold_l001.held_out_false_positives == 5
    assert fold_l001.held_out_true_negatives == 491
    assert fold_l001.held_out_sensitivity == 0.0
    assert fold_l001.held_out_specificity == pytest.approx(491 / 496, rel=1e-5)

def test_lower_bound_and_upper_bound_directions():
    from yield_improvement.parametric_analysis.engine import _evaluate_cutpoint
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    targets = [True, True, False, False, False]

    # Lower bound test: val < cut flags die as target
    cm_lower = _evaluate_cutpoint(vals, targets, 2.5, 'LOWER_BOUND')
    assert cm_lower.true_positives == 2  # 1.0, 2.0 < 2.5
    assert cm_lower.false_negatives == 0
    assert cm_lower.false_positives == 0
    assert cm_lower.true_negatives == 3  # 3.0, 4.0, 5.0 >= 2.5
    assert cm_lower.sensitivity == 1.0
    assert cm_lower.specificity == 1.0

    # Upper bound test: val > cut flags die as target
    cm_upper = _evaluate_cutpoint(vals, targets, 2.5, 'UPPER_BOUND')
    assert cm_upper.true_positives == 0  # targets are 1.0, 2.0; neither > 2.5
    assert cm_upper.false_negatives == 2
    assert cm_upper.false_positives == 3  # non-targets 3.0, 4.0, 5.0 > 2.5
    assert cm_upper.true_negatives == 0
    assert cm_upper.sensitivity == 0.0
    assert cm_upper.specificity == 0.0

def test_stage_1_5_no_candidate_reporting_and_target_counts(setup_canonical_data):
    attempts, parametric = setup_canonical_data
    extraction = extract_first_pass_parametric_data(attempts, parametric)
    report = run_parametric_analysis(extraction, 'yi_synthetic_v2')

    # Audit VMAX (which has 12 target failures in canonical V2, but INSUFFICIENT_EVIDENCE for candidate)
    vmax_res = next(r for r in report.results if r.parameter_name == 'VMAX')
    assert vmax_res.threshold_status == 'INSUFFICIENT_EVIDENCE'
    assert vmax_res.candidate_threshold is None
    # Actual target failure code count must be preserved and visible in data_quality
    assert vmax_res.data_quality.target_failure_code_count == 12
    assert vmax_res.data_quality.non_target_count == 2488
    assert vmax_res.data_quality.eligible_physical_dies == 2500
    assert vmax_res.data_quality.valid_first_pass_measurements == 2500

    # Audit SUPPLY_CURRENT (which is mapped to LEAKAGE in registry and has 9 failures in canonical V2)
    sc_res = next(r for r in report.results if r.parameter_name == 'SUPPLY_CURRENT')
    assert sc_res.threshold_status == 'INSUFFICIENT_EVIDENCE'
    assert sc_res.candidate_threshold is None
    assert sc_res.target_failure_code == 'LEAKAGE'
    assert sc_res.data_quality.target_failure_code_count == 9
    assert sc_res.data_quality.non_target_count == 2491

    # Audit VDD (BAND rail with no target code)
    vdd_res = next(r for r in report.results if r.parameter_name == 'VDD')
    assert vdd_res.threshold_status == 'INSUFFICIENT_EVIDENCE'
    assert vdd_res.candidate_threshold is None
    assert vdd_res.target_failure_code is None
    assert vdd_res.data_quality.target_failure_code_count == 0
    assert vdd_res.data_quality.non_target_count == 2500




