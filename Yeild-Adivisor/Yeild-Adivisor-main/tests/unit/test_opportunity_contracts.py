"""Opportunity schema, overlap, safety-zero, and attribution. No ground truth."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from yield_improvement.detectors.population import DetectorContext, DieView
from yield_improvement.hypotheses.contract import Hypothesis, HypothesisBundle
from yield_improvement.opportunity.contract import DISCLAIMER, Opportunity
from yield_improvement.opportunity.engine import estimate_opportunities, production_safety_rate
from yield_improvement.opportunity.populations import die_key, resolve_population
from yield_improvement.pipeline import run_fixture_dir
from yield_improvement.utils.paths import fixtures_fpy_dir, repo_root


def _ts():
    return datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


def _die(i: int, *, fail=False, lot="L1", wafer="W1", tester="T03", x=0.0, y=0.0, probe="PC-1"):
    return DieView(
        lot_id=lot,
        wafer_id=wafer,
        die_id=f"D{i:03d}",
        attempt_id=f"E{i}",
        failed=fail,
        x=x,
        y=y,
        r=(x**2 + y**2) ** 0.5,
        tester_id=tester,
        probe_card_id=probe,
        temperature_c=25.0,
        timestamp=_ts(),
        failure_code="F" if fail else None,
        primary_failure_code="F" if fail else None,
        primary_failure_family="PARAMETRIC" if fail else None,
        primary_failure_detail="SHIFT" if fail else None,
    )


def _hyp(
    family: str,
    detail: str,
    *,
    assoc="PRIMARY_EVIDENCE",
    affected=None,
    score=0.7,
    tier="MODERATE_EVIDENCE",
    hid=None,
):
    return Hypothesis(
        hypothesis_id=hid or f"H-{family}.{detail}",
        family=family,
        detail=detail,
        statement=f"Yield loss is associated with {family}.{detail}.",
        association_class=assoc,
        evidence_tier=tier,
        evidence_score=score,
        confidence_level="MEDIUM",
        rank=1,
        affected_population=affected,
        not_a_root_cause=True,
        status="UNCONFIRMED",
    )


def _bundle(hyps, n=10, no_confident=False, fpy=None):
    return HypothesisBundle(
        analysis_id="unit",
        current_fpy=fpy,
        n_eligible=n,
        no_confident_hypothesis=no_confident,
        hypotheses=hyps,
    )


def test_safety_eligible_production_is_zero_on_model():
    with pytest.raises(ValidationError):
        Opportunity(
            opportunity_id="OPP-X",
            hypothesis_id="H-X",
            attribution_mode="PRIMARY_FAILURE",
            status="ESTIMATED",
            status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION"],
            observed_loss_count=1,
            observed_loss_rate=0.1,
            upper_bound_count=1,
            upper_bound_rate=0.1,
            plausible_count=None,
            plausible_rate=None,
            plausible_unavailable=True,
            safety_eligible_production_count=1,
            safety_eligible_production_rate=0.0,
            eligible_population=10,
            affected_population_count=1,
            population_definition="x",
            calculation_method="x",
        )


def test_approved_for_production_rejected():
    with pytest.raises(ValidationError):
        Opportunity(
            opportunity_id="OPP-X",
            hypothesis_id="H-X",
            attribution_mode="PRIMARY_FAILURE",
            status="ESTIMATED",
            status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION", "APPROVED_FOR_PRODUCTION"],
            observed_loss_count=0,
            observed_loss_rate=0.0,
            upper_bound_count=0,
            upper_bound_rate=0.0,
            plausible_count=None,
            plausible_rate=None,
            plausible_unavailable=True,
            eligible_population=10,
            affected_population_count=0,
            population_definition="x",
            calculation_method="x",
        )


def test_config_safety_rate_is_zero(config):
    assert production_safety_rate(config) == 0.0
    assert config.safety.safety_eligible_production.value == 0.0
    assert config.safety.safety_eligible_production.immutable is True


def test_case_01_observed_loss(config):
    result = run_fixture_dir(fixtures_fpy_dir() / "case_01", config=config)
    assert result.eligible_die_count == 10
    assert result.first_pass_fail_count == 1
    observed = result.first_pass_fail_count / result.eligible_die_count
    assert observed == pytest.approx(0.1)


def test_observed_and_upper_bound_match(config):
    dies = [_die(i, fail=(i < 4), tester="T03" if i < 6 else "T01") for i in range(10)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle([_hyp("EQUIPMENT", "DEGRADATION", affected={"label": "T03"})], n=10, fpy=0.6)
    out = estimate_opportunities(hyps, ctx, config)
    item = next(o for o in out.opportunities if o.hypothesis_id == "H-EQUIPMENT.DEGRADATION")
    assert item.observed_loss_count == 4
    assert item.observed_loss_rate == pytest.approx(0.4)
    assert item.upper_bound_count == item.observed_loss_count
    assert item.upper_bound_rate == item.observed_loss_rate
    assert item.safety_eligible_production_rate == 0.0
    assert item.safety_eligible_production_count == 0
    assert "will increase" not in item.statement.lower()
    assert "upper bound, not a predicted improvement" in item.statement
    assert item.disclaimer == DISCLAIMER
    assert "PRIMARY_FAILURE" in item.calculation_method
    assert out.summary.observed_loss_count == 4
    assert out.summary.safety_eligible_total_rate == 0.0


def test_overlap_union_exclusive(config):
    dies = []
    for i in range(10):
        lot = "L1" if i < 7 else "L2"
        tester = "T03" if i < 5 or i >= 7 else "T01"
        fail = i < 3 or i == 7
        dies.append(_die(i, fail=fail, lot=lot, tester=tester))
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle(
        [
            _hyp("PROCESS", "LOT_VARIATION", affected={"label": "L1"}, hid="H-PROCESS.LOT_VARIATION"),
            _hyp("EQUIPMENT", "DEGRADATION", affected={"label": "T03"}, hid="H-EQUIPMENT.DEGRADATION"),
        ],
        n=10,
        fpy=0.6,
    )
    out = estimate_opportunities(hyps, ctx, config)
    lot = next(o for o in out.opportunities if o.detail == "LOT_VARIATION")
    eq = next(o for o in out.opportunities if o.detail == "DEGRADATION")
    union = next(o for o in out.opportunities if o.opportunity_id == "OPP-UNION-PRIMARY")
    assert lot.observed_loss_count == 3
    assert eq.observed_loss_count == 4
    assert union.intersection_count == 3
    assert union.union_count == 4
    assert union.exclusive_count == 1
    assert union.upper_bound_count == 4
    summed = (lot.upper_bound_rate or 0) + (eq.upper_bound_rate or 0)
    assert union.upper_bound_rate < summed
    assert out.summary.sum_of_individual_upper_bounds_exceeds_observed is True
    assert out.summary.union_upper_bound_count == 4
    assert lot.overlap_count == 3
    assert eq.exclusive_count == 1
    public = out.to_public_dict()
    assert public["summary"]["safety_eligible_total_rate"] == 0.0


def test_no_signal_does_not_invent_opportunity(config):
    dies = [_die(i, fail=(i == 0)) for i in range(10)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle([], n=10, no_confident=True, fpy=0.9)
    out = estimate_opportunities(hyps, ctx, config)
    assert out.no_actionable_opportunity is True
    assert out.opportunities == []
    assert out.summary.observed_loss_count == 1
    assert out.summary.observed_loss_rate == pytest.approx(0.1)
    assert out.summary.safety_eligible_total_rate == 0.0


def test_insufficient_population_no_plausible(config):
    dies = [_die(i, fail=(i < 2)) for i in range(10)]
    dies = [DieView(**{**d.__dict__, "x": None, "y": None, "r": None}) for d in dies]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle([_hyp("SPATIAL", "EDGE", affected={"region": "EDGE"})], n=10, fpy=0.8)
    out = estimate_opportunities(hyps, ctx, config)
    item = out.opportunities[0]
    assert item.status == "INSUFFICIENT_DATA"
    assert item.plausible_unavailable is True
    assert item.plausible_rate is None
    assert "missing_x_y" in item.data_gaps
    assert item.safety_eligible_production_rate == 0.0


def test_secondary_not_in_union(config):
    dies = [_die(i, fail=(i < 3), lot="L1" if i < 5 else "L2") for i in range(10)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle(
        [
            _hyp("PROCESS", "DRIFT", affected={"label": "late"}, hid="H-PROCESS.DRIFT"),
            _hyp(
                "PROCESS",
                "LOT_VARIATION",
                assoc="SECONDARY_ASSOCIATION",
                affected={"label": "L1"},
                hid="H-PROCESS.LOT_VARIATION",
                tier="WEAK_EVIDENCE",
                score=0.4,
            ),
        ],
        n=10,
        fpy=0.7,
    )
    out = estimate_opportunities(hyps, ctx, config)
    lot = next(o for o in out.opportunities if o.detail == "LOT_VARIATION")
    assert lot.status == "NOT_ESTIMABLE"
    assert lot.included_in_union is False
    assert lot.plausible_unavailable is True


def test_near_limit_does_not_modify_limits(config):
    dies = [_die(i, fail=(i < 3)) for i in range(12)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=12)
    hyps = _bundle([_hyp("TEST", "LIMIT_SENSITIVITY", affected={"band": "near"})], n=12, fpy=0.75)
    out = estimate_opportunities(hyps, ctx, config)
    item = next(o for o in out.opportunities if o.detail == "LIMIT_SENSITIVITY")
    blob = str(item.model_dump()).lower()
    assert "increase test limit" not in blob
    assert item.safety_eligible_production_rate == 0.0
    assert item.plausible_unavailable is True
    assert any("does not modify" in note.lower() for note in item.limitations)
    assert "DOES_NOT_MODIFY_LIMITS" in item.status_flags


def test_ranking_deterministic(config):
    dies = [_die(i, fail=(i < 2), tester="T03" if i < 5 else "T01") for i in range(10)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle([_hyp("EQUIPMENT", "DEGRADATION", affected={"label": "T03"})], n=10, fpy=0.8)
    a = estimate_opportunities(hyps, ctx, config)
    b = estimate_opportunities(hyps, ctx, config)
    assert a.model_dump() == b.model_dump()


def test_traceability_fields(config):
    dies = [_die(i, fail=(i == 0), tester="T03") for i in range(10)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=10)
    hyps = _bundle([_hyp("EQUIPMENT", "DEGRADATION", affected={"label": "T03"})], n=10, fpy=0.9)
    out = estimate_opportunities(hyps, ctx, config)
    item = out.opportunities[0]
    assert item.hypothesis_id == "H-EQUIPMENT.DEGRADATION"
    assert item.population_definition.startswith("tester_id=")
    assert die_key(dies[0]) in item.affected_die_ids
    assert item.eligible_population == 10
    assert "PRIMARY_FAILURE" in item.attribution_mode
    assert out.config_versions["safety_policy"]
    assert item.calculation_method


def test_primary_fail_not_mixed_with_any_fail_label(config):
    dies = [_die(i, fail=(i == 0)) for i in range(8)]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=8)
    hyps = _bundle([_hyp("EQUIPMENT", "DEGRADATION", affected={"label": "T03"})], n=8, fpy=0.875)
    primary = estimate_opportunities(hyps, ctx, config, attribution_mode="PRIMARY_FAILURE")
    any_fail = estimate_opportunities(hyps, ctx, config, attribution_mode="ANY_FAIL")
    assert primary.attribution_mode == "PRIMARY_FAILURE"
    assert any_fail.attribution_mode == "ANY_FAIL"
    assert primary.summary.attribution_mode != "ANY_FAIL" or any_fail.summary.attribution_mode == "ANY_FAIL"


def test_opportunity_package_does_not_import_ground_truth():
    src = repo_root() / "src" / "yield_improvement" / "opportunity"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("true_cause", "scenario_id", "RUN_SUMMARY", "yield_improvement.evaluation"):
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == []


def test_resolve_spatial_missing_xy(config):
    dies = [_die(i) for i in range(5)]
    dies = [DieView(**{**d.__dict__, "x": None, "y": None, "r": None}) for d in dies]
    ctx = DetectorContext(dies=dies, attempts=[], test_results=[], parametric=[], config=config, n_eligible=5)
    slice_ = resolve_population(_hyp("SPATIAL", "EDGE"), ctx, config)
    assert slice_.resolvable is False
    assert "missing_x_y" in slice_.data_gaps
