from __future__ import annotations

import pytest

from yield_improvement.api.service import get_recommendations_bundle, load_report
from yield_improvement.recommendations.contracts import (
    EngineeringRecommendation,
    SupportingEvidenceItem,
)
from yield_improvement.recommendations.generator import generate_recommendations
from yield_improvement.reporting.contract import EngineeringReport, ReportHypothesis


def test_recommendation_traceability_schema_and_defaults():
    """Verify mandatory default values for evidence strength and validation status."""
    item = SupportingEvidenceItem(
        evidence_type="MEASURED_STATISTIC",
        evidence_classification="OBSERVED_FACT",
        source_dataset="test_ds",
        source_artifact="test_art",
        entity_scope="test_scope",
    )
    # Mandatory correction #2: SupportingEvidenceItem.validation_state must default to NOT_EVALUATED
    assert item.validation_state == "NOT_EVALUATED"

    from yield_improvement.recommendations.contracts import ValidationProtocol
    proto = ValidationProtocol(
        protocol_id="PROTO-TEST",
        replication_check="Check 3 lots",
        downstream_reliability_risk="None",
    )

    rec = EngineeringRecommendation(
        recommendation_id="REC-TEST",
        title="Test recommendation",
        recommendation_category="Lot investigation",
        priority_rank=1,
        priority_tier="LOW",
        confidence_tier="LOW",
        ranking_score=0.2,
        ranking_rationale="Test rationale",
        observed_pattern="Test pattern",
        target_population="Test population",
        affected_die_count=10,
        eligible_die_count=100,
        observed_failure_rate=0.1,
        baseline_failure_rate=0.05,
        hypothesis_confidence="LOW",
        ml_evidence_status="NOT_AVAILABLE",
        ml_evidence_notes="None",
        recommended_action="Investigate test action.",
        reason="Test reason",
        expected_information="Test expected",
        validation_method="Test val",
        success_criteria="Test criteria",
        risk_if_ignored="Test risk",
        next_step_if_confirmed="PM",
        next_step_if_rejected="Review",
        validation_protocol=proto,
        observed_loss_rate=0.01,
        production_action="FORBIDDEN",
        production_authorized=False,
        not_a_root_cause=True,
    )

    # Mandatory correction #1: Default evidence_strength must be INSUFFICIENT
    assert rec.evidence_strength == "INSUFFICIENT"
    # Mandatory correction #2: Default validation_status must be NOT_EVALUATED
    assert rec.validation_status == "NOT_EVALUATED"
    # Safety status default
    assert "ADVISORY_ONLY" in rec.safety_status
    assert "FORBIDDEN" in rec.safety_status


def test_insufficient_evidence_fail_closed_cannot_be_upgraded():
    """Verify that insufficient data, small sample sizes, or non-significant signals fail closed."""
    report = load_report("yi_synthetic_v2")

    # 1. Hypothesis explicitly flagged as INSUFFICIENT_EVIDENCE
    insufficient_hyp = report.hypotheses[0].model_copy(
        update={
            "evidence_tier": "INSUFFICIENT_EVIDENCE",
            "association_class": "INSUFFICIENT_EVIDENCE",
        }
    )
    # 2. Hypothesis with sample size < 10 failures
    small_sample_hyp = report.hypotheses[0].model_copy(
        update={
            "hypothesis_id": "H-TEST.SMALL_SAMPLE",
            "evidence_tier": "STRONG_EVIDENCE",
            "affected_population": {"label": "SMALL", "n": 20, "rate": 0.15},
            "observed_loss_rate": 0.0012,
        }
    )
    # 3. Hypothesis with non-significant p-value (p >= 0.05)
    insig_hyp = report.hypotheses[0].model_copy(
        update={
            "hypothesis_id": "H-TEST.INSIGNIFICANT",
            "evidence_tier": "STRONG_EVIDENCE",
            "statistical_evidence": [
                {
                    "detector": "lot",
                    "p_value": 0.42,
                    "adjusted_p_value": 0.58,
                    "effect_size": 0.01,
                    "sample_size": 2500,
                }
            ],
        }
    )
    # 4. Hypothesis with missing/empty statistical evidence records
    empty_stats_hyp = report.hypotheses[0].model_copy(
        update={
            "hypothesis_id": "H-TEST.EMPTY_STATS",
            "evidence_tier": "MODERATE_EVIDENCE",
            "statistical_evidence": [],
        }
    )
    # 5. Hypothesis claiming STRONG_EVIDENCE but single domain only
    single_domain_hyp = report.hypotheses[0].model_copy(
        update={
            "hypothesis_id": "H-TEST.SINGLE_DOMAIN",
            "evidence_tier": "STRONG_EVIDENCE",
            "supporting_detectors": ["lot"],
            "data_gaps": [],
            "affected_population": {"label": "L004", "n": 500, "rate": 0.194},
        }
    )

    test_report = report.model_copy(
        update={"hypotheses": [small_sample_hyp, insig_hyp, empty_stats_hyp, single_domain_hyp]}
    )
    bundle = generate_recommendations(test_report, dataset_id="yi_synthetic_v2")

    recs = {r.hypothesis_id: r for r in bundle.recommendations}

    # Small sample must fail closed to INSUFFICIENT despite strong evidence tier
    assert "H-TEST.SMALL_SAMPLE" in recs
    assert recs["H-TEST.SMALL_SAMPLE"].evidence_strength == "INSUFFICIENT"
    assert recs["H-TEST.SMALL_SAMPLE"].validation_status == "INSUFFICIENT_SAMPLE_SIZE"

    # Insignificant signal must fail closed to INSUFFICIENT
    assert "H-TEST.INSIGNIFICANT" in recs
    assert recs["H-TEST.INSIGNIFICANT"].evidence_strength == "INSUFFICIENT"
    assert recs["H-TEST.INSIGNIFICANT"].validation_status == "NO_STATISTICAL_SIGNIFICANCE"

    # Empty statistical evidence must fail closed to INSUFFICIENT and NOT_EVALUATED
    assert "H-TEST.EMPTY_STATS" in recs
    assert recs["H-TEST.EMPTY_STATS"].evidence_strength == "INSUFFICIENT"
    assert recs["H-TEST.EMPTY_STATS"].validation_status == "NOT_EVALUATED"

    # Single domain cannot achieve STRONG, must be capped at MODERATE
    assert "H-TEST.SINGLE_DOMAIN" in recs
    assert recs["H-TEST.SINGLE_DOMAIN"].evidence_strength == "MODERATE"
    assert recs["H-TEST.SINGLE_DOMAIN"].validation_status == "STATISTICAL_SIGNAL_VALIDATED"



def test_v2_canonical_traceability_and_provenance():
    """Verify evidence traceability, provenance, and calculated baseline in V2."""
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    assert bundle.recommendation_count > 0
    for rec in bundle.recommendations:
        # Traceability fields populated
        assert len(rec.summary) > 20
        assert len(rec.observed_facts) >= 3
        assert len(rec.supporting_evidence) >= 2
        assert len(rec.uncertainties) >= 2
        assert len(rec.data_gaps) >= 1
        assert len(rec.recommended_next_steps) >= 3

        # Safety invariants
        assert rec.production_action == "FORBIDDEN"
        assert rec.production_authorized is False
        assert rec.safety_eligible_production_rate == 0.0
        assert rec.safety_eligible_production_count == 0
        assert rec.not_a_root_cause is True
        assert "ADVISORY_ONLY" in rec.safety_status

        # Provenance on supporting evidence items
        for item in rec.supporting_evidence:
            assert item.source_dataset == "yi_synthetic_v2"
            assert len(item.source_artifact) > 0
            assert item.time_scope in {"FIRST_PASS", "HOLDOUT_LOTS"}
            if item.numerator is not None and item.denominator is not None:
                assert item.numerator <= item.denominator


def test_first_pass_filtering_and_baseline_calculation():
    """Verify exact first-pass numerators, denominators, and baseline comparison."""
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")
    recs = {r.hypothesis_id: r for r in bundle.recommendations}

    # Lot L004 recommendation
    lot_rec = recs["H-PROCESS.LOT_VARIATION"]
    assert lot_rec.affected_die_count == 97
    assert lot_rec.subgroup_die_count == 500
    assert lot_rec.eligible_die_count == 2500

    # Find subgroup measurement item and baseline item
    subgroup_item = next(
        i for i in lot_rec.supporting_evidence if i.evidence_type == "FIRST_PASS_SUBGROUP_MEASUREMENT"
    )
    assert subgroup_item.numerator == 97
    assert subgroup_item.denominator == 500
    assert subgroup_item.observed_value == 0.194
    assert subgroup_item.baseline_value == 0.077

    baseline_item = next(
        i for i in lot_rec.supporting_evidence if i.evidence_type == "FIRST_PASS_BASELINE_COMPARISON"
    )
    assert baseline_item.numerator == 154
    assert baseline_item.denominator == 2000
    assert baseline_item.observed_value == 0.077
    assert "Lot-excluded baseline" in baseline_item.entity_scope

    # Spatial Border recommendation
    border_rec = recs["H-SPATIAL.BORDER"]
    assert border_rec.affected_die_count == 118
    assert border_rec.subgroup_die_count == 900
    border_subgroup_item = next(
        i for i in border_rec.supporting_evidence if i.evidence_type == "FIRST_PASS_SUBGROUP_MEASUREMENT"
    )
    assert border_subgroup_item.numerator == 118
    assert border_subgroup_item.denominator == 900
    border_base_item = next(
        i for i in border_rec.supporting_evidence if i.evidence_type == "FIRST_PASS_BASELINE_COMPARISON"
    )
    # Remaining core dies: 2500 - 900 = 1600; remaining fails: 251 - 118 = 133
    assert border_base_item.numerator == 133
    assert border_base_item.denominator == 1600
    assert border_base_item.observed_value == pytest.approx(133 / 1600, abs=1e-4)


def test_evidence_classification_distinction():
    """Verify clear distinction between observed fact, statistical association, and unconfirmed hypothesis."""
    report = load_report("yi_synthetic_v2")
    bundle = generate_recommendations(report, dataset_id="yi_synthetic_v2")

    for rec in bundle.recommendations:
        classifications = {item.evidence_classification for item in rec.supporting_evidence}
        # Both observed facts (counts) and statistical associations (detector signals) must be present
        assert "OBSERVED_FACT" in classifications
        assert "STATISTICAL_ASSOCIATION" in classifications

        # Never describe statistical association as confirmed root cause
        for fact in rec.observed_facts:
            assert "root cause" not in fact.lower()


def test_lot_scoped_bundle_traceability():
    """Verify lot-scoped recommendations calculate denominators matching the selected lot."""
    bundle_dict = get_recommendations_bundle("yi_synthetic_v2", lot_id="L004")
    assert bundle_dict["selected_lot_id"] == "L004"
    assert bundle_dict["recommendation_count"] > 0

    recs = bundle_dict["recommendations"]
    l004_recs = [r for r in recs if r.get("scope") == "LOT_SPECIFIC"]
    assert len(l004_recs) > 0
    for r in l004_recs:
        assert r["lot_id"] == "L004"
        assert len(r["observed_facts"]) >= 3
        assert len(r["supporting_evidence"]) >= 2
