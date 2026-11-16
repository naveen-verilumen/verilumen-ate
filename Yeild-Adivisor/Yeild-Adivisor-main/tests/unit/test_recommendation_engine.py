from __future__ import annotations

import pytest

from yield_improvement.api.service import load_report
from yield_improvement.recommendations.contracts import (
    EngineeringRecommendation,
    RecommendationBundle,
)
from yield_improvement.recommendations.generator import generate_recommendations
from yield_improvement.recommendations.ranking import compute_recommendation_score, rank_recommendations


def test_v2_recommendations_counts_and_denominators():
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    assert bundle.dataset_id == "yi_synthetic_v2"
    assert bundle.recommendation_count > 0
    assert bundle.production_action == "FORBIDDEN"
    assert bundle.production_authorized is False
    assert bundle.safety_eligible_production_rate == 0.0

    # Verify canonical denominators
    assert report.fpy_summary.eligible_die_count == 2500
    assert report.fpy_summary.first_pass_pass_count == 2249
    assert report.fpy_summary.first_pass_fail_count == 251
    assert report.fpy_summary.fpy == pytest.approx(0.8996, abs=1e-4)
    assert report.fpy_summary.fpy_loss == pytest.approx(0.1004, abs=1e-4)

    # All recommendations must reference eligible_die_count == 2500
    recs_by_hyp = {r.hypothesis_id: r for r in bundle.recommendations if r.hypothesis_id}
    for rec in bundle.recommendations:
        assert rec.eligible_die_count == 2500
        assert rec.production_action == "FORBIDDEN"
        assert rec.production_authorized is False
        assert rec.safety_eligible_production_rate == 0.0
        assert rec.safety_eligible_production_count == 0
        assert rec.not_a_root_cause is True

    # Check Lot Variation recommendation
    assert "H-PROCESS.LOT_VARIATION" in recs_by_hyp
    lot_rec = recs_by_hyp["H-PROCESS.LOT_VARIATION"]
    assert lot_rec.recommendation_category == "Lot investigation"
    assert "L004" in lot_rec.target_population
    assert lot_rec.observed_failure_rate == pytest.approx(0.194, abs=1e-3)
    assert lot_rec.affected_die_count == 97

    # Check Spatial Border recommendation
    assert "H-SPATIAL.BORDER" in recs_by_hyp
    border_rec = recs_by_hyp["H-SPATIAL.BORDER"]
    assert border_rec.recommendation_category == "Spatial investigation"
    assert "BORDER" in border_rec.target_population
    assert border_rec.observed_failure_rate == pytest.approx(0.1311, abs=1e-3)
    assert border_rec.affected_die_count == 118
    assert border_rec.subgroup_die_count == 900
    assert border_rec.subgroup_failed_die_count == 118
    assert border_rec.subgroup_failed_die_count / border_rec.subgroup_die_count == pytest.approx(border_rec.observed_failure_rate, abs=1e-3)

    # Check Wafer Variation recommendation
    assert "H-PROCESS.WAFER_VARIATION" in recs_by_hyp
    wafer_rec = recs_by_hyp["H-PROCESS.WAFER_VARIATION"]
    assert wafer_rec.recommendation_category == "Wafer investigation"
    assert "W05" in wafer_rec.target_population
    assert wafer_rec.observed_failure_rate == pytest.approx(0.45, abs=1e-2)
    assert wafer_rec.affected_die_count == 45
    assert wafer_rec.subgroup_die_count == 100
    assert wafer_rec.subgroup_failed_die_count == 45

    # Check Near-Limit recommendation
    assert "H-TEST.LIMIT_SENSITIVITY" in recs_by_hyp
    limit_rec = recs_by_hyp["H-TEST.LIMIT_SENSITIVITY"]
    assert limit_rec.recommendation_category == "Near-limit investigation"
    assert "do not relax" in limit_rec.recommended_action.lower()
    assert limit_rec.affected_die_count == 67
    assert limit_rec.subgroup_die_count == 299
    assert limit_rec.subgroup_failed_die_count == 67
    assert limit_rec.observed_failure_rate == pytest.approx(0.2241, abs=1e-3)
    assert limit_rec.subgroup_failed_die_count / limit_rec.subgroup_die_count == pytest.approx(limit_rec.observed_failure_rate, abs=1e-3)


def test_v2_ml_status_reported_honestly():
    report = load_report("yi_synthetic_v2")
    # Even if an active ML snapshot is provided, V2 must report NEEDS_MORE_DATA
    fake_snapshot = {
        "available": True,
        "ml_support_status": "RELIABLE",
        "metrics": {"roc_auc": 0.4592},
    }
    bundle = generate_recommendations(report, ml_snapshot=fake_snapshot, dataset_id="yi_synthetic_v2")

    assert bundle.ml_evidence_status == "NEEDS_MORE_DATA"
    assert "insufficient generalizable predictive signal" in bundle.ml_evidence_summary
    for rec in bundle.recommendations:
        assert rec.ml_evidence_status == "NEEDS_MORE_DATA"


def test_deterministic_ranking():
    report = load_report("yi_synthetic_v2")
    bundle1 = generate_recommendations(report, dataset_id="yi_synthetic_v2")
    bundle2 = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    assert len(bundle1.recommendations) == len(bundle2.recommendations)
    for r1, r2 in zip(bundle1.recommendations, bundle2.recommendations, strict=True):
        assert r1.recommendation_id == r2.recommendation_id
        assert r1.priority_rank == r2.priority_rank
        assert r1.ranking_score == r2.ranking_score
        assert r1.priority_tier == r2.priority_tier
        assert r1.confidence_tier == r2.confidence_tier


def test_opportunity_not_additive_and_safety_zero():
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    for rec in bundle.recommendations:
        assert rec.safety_eligible_production_rate == 0.0
        assert rec.safety_eligible_production_count == 0
        assert "Overlapping slices must not be summed" in rec.opportunity_disclaimer


def test_validation_protocol_steps_present():
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    for rec in bundle.recommendations:
        proto = rec.validation_protocol
        assert proto.protocol_id.startswith(f"PROTO-{rec.recommendation_id}")
        assert len(proto.steps) == 7
        step_titles = [s.title for s in proto.steps]
        assert "Audit Data Quality & Denominators" in step_titles
        assert "Controlled Population Comparison" in step_titles
        assert "Process Equipment & Tool Lineage Review" in step_titles
        assert "Independent Material Replication" in step_titles
        assert "Physical Failure Analysis & Inline Metrology" in step_titles
        assert "Controlled Split-Lot DOE Proposal" in step_titles
        assert "Downstream Package & Reliability Qualification" in step_titles
        for s in proto.steps:
            assert s.investigation_action
            assert s.expected_measurement
            assert s.acceptance_criteria
            assert s.rejection_criteria


def test_safety_invariants_reject_violations():
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")
    first_dict = bundle.recommendations[0].model_dump()

    # Attempting to validate with production_authorized = True must raise ValueError
    with pytest.raises(ValueError):
        EngineeringRecommendation.model_validate({**first_dict, "production_authorized": True})

    # Attempting to validate with production_action != FORBIDDEN must raise ValueError
    with pytest.raises(ValueError):
        EngineeringRecommendation.model_validate({**first_dict, "production_action": "APPLY_TO_PRODUCTION"})

    # Attempting to validate with safety_eligible_production_rate != 0.0 must raise ValueError
    with pytest.raises(ValueError):
        EngineeringRecommendation.model_validate({**first_dict, "safety_eligible_production_rate": 0.05})

