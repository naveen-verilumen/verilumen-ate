"""HypothesisBundle → OpportunityBundle. Not a forecast. Production eligibility is 0."""

from __future__ import annotations

from pathlib import Path

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.common import cal
from yield_improvement.detectors.population import DetectorContext, DieView, build_context
from yield_improvement.detectors.runner import run_detectors
from yield_improvement.hypotheses.composer import compose
from yield_improvement.hypotheses.contract import Hypothesis, HypothesisBundle
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
)
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement, TestResult
from yield_improvement.opportunity.contract import (
    DISCLAIMER,
    AttributionMode,
    Opportunity,
    OpportunityBundle,
    OpportunitySummary,
)
from yield_improvement.opportunity.populations import PopulationSlice, die_key, resolve_population
from yield_improvement.utils.errors import ConfigError
from yield_improvement.yield_analysis.fpy import calculate_fpy

_NO_PLAUSIBLE_FAMILIES = {("TEST", "LIMIT_SENSITIVITY"), ("CORRELATED", "FAILURES"), ("TEST", "SEQUENCE")}


def production_safety_rate(config: AppConfig) -> float:
    value = float(config.safety.safety_eligible_production.value)
    if value != 0.0 or not config.safety.safety_eligible_production.immutable:
        raise ConfigError("safety_eligible_production must be immutable 0")
    return 0.0


def _is_fail(die: DieView, ctx: DetectorContext, mode: AttributionMode) -> bool:
    if mode == "PRIMARY_FAILURE":
        return die.failed
    if die.failed:
        return True
    rows = ctx.tests_by_attempt().get(die.attempt_id, [])
    return any(r.test_pass_fail == "FAIL" for r in rows)


def _fail_keys(ctx: DetectorContext, mode: AttributionMode) -> frozenset[str]:
    return frozenset(die_key(d) for d in ctx.dies if _is_fail(d, ctx, mode))


def _rate(count: int, n: int) -> float:
    return 0.0 if n <= 0 else round(count / n, 6)


def _include_in_union(hyp: Hypothesis, config: AppConfig) -> bool:
    if hyp.association_class == "PRIMARY_EVIDENCE":
        return True
    return cal(config, "opportunity_include_secondary_in_union") >= 1.0


def _plausible_excess(
    slice_: PopulationSlice,
    fail_keys: frozenset[str],
    n_eligible: int,
    hyp: Hypothesis,
    config: AppConfig,
) -> tuple[int | None, float | None, bool, str]:
    """Excess fail rate vs complement. Not a recoverable probability. PRELIMINARY."""
    if (hyp.family, hyp.detail) in _NO_PLAUSIBLE_FAMILIES:
        return None, None, True, "plausible_not_claimed_recoverable"
    if hyp.association_class in {"SECONDARY_ASSOCIATION", "INSUFFICIENT_EVIDENCE"}:
        return None, None, True, "plausible_not_estimable_for_association_class"
    if not slice_.resolvable or not slice_.affected:
        return None, None, True, "population_unresolved"
    n_slice = len(slice_.affected)
    n_comp = len(slice_.complement)
    min_g = int(cal(config, "n_min_group_compare"))
    if n_slice < min_g or n_comp < min_g:
        return None, None, True, "slice_below_n_min_group_compare"
    fail_slice = len(slice_.affected & fail_keys)
    fail_comp = len(slice_.complement & fail_keys)
    rate_comp = fail_comp / n_comp if n_comp else 0.0
    excess = max(0.0, fail_slice - rate_comp * n_slice)
    if hyp.association_class == "WEAK_ASSOCIATION":
        excess *= cal(config, "opportunity_plausible_weak_scale")
    count = int(round(excess))
    return count, _rate(count, n_eligible), False, "excess_fail_rate_vs_complement"


def _status(
    *,
    resolvable: bool,
    association: str,
    overlap: int,
    plausible_unavailable: bool,
    upper_bound_rate: float | None,
) -> str:
    if not resolvable or association == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_DATA"
    if association == "SECONDARY_ASSOCIATION":
        return "NOT_ESTIMABLE"
    if overlap > 0:
        return "OVERLAPPING"
    if not plausible_unavailable:
        return "PRELIMINARY"
    if upper_bound_rate is not None:
        return "ESTIMATED"
    return "OBSERVED"


def _statement(hyp: Hypothesis, observed_rate: float) -> str:
    pp = round(100.0 * observed_rate, 4)
    return (
        f"Observed loss associated with {hyp.family}.{hyp.detail} is {pp} percentage points; "
        "this represents an upper bound, not a predicted improvement."
    )


def estimate_opportunities(
    hypotheses: HypothesisBundle,
    ctx: DetectorContext,
    config: AppConfig,
    *,
    attribution_mode: AttributionMode = "PRIMARY_FAILURE",
) -> OpportunityBundle:
    production_safety_rate(config)
    n = ctx.n_eligible
    fail_keys = _fail_keys(ctx, attribution_mode)
    observed_count = len(fail_keys)
    observed_rate = _rate(observed_count, n)
    current_fpy = hypotheses.current_fpy
    if current_fpy is None and n:
        current_fpy = round(1.0 - observed_rate, 6)

    items: list[Opportunity] = []
    slices: dict[str, PopulationSlice] = {}
    fail_in_slice: dict[str, frozenset[str]] = {}

    no_actionable = hypotheses.no_confident_hypothesis or not hypotheses.hypotheses
    if hypotheses.no_confident_hypothesis:
        # Do not invent per-hypothesis opportunity. Overall observed loss remains in summary.
        opportunities: list[Opportunity] = []
    else:
        for hyp in hypotheses.hypotheses:
            slice_ = resolve_population(hyp, ctx, config)
            slices[hyp.hypothesis_id] = slice_
            fail_in_slice[hyp.hypothesis_id] = slice_.affected & fail_keys

        primary_ids = [h.hypothesis_id for h in hypotheses.hypotheses if _include_in_union(h, config)]
        union_fail = frozenset().union(*(fail_in_slice[i] for i in primary_ids)) if primary_ids else frozenset()

        opportunities = []
        for hyp in hypotheses.hypotheses:
            slice_ = slices[hyp.hypothesis_id]
            associated = fail_in_slice[hyp.hypothesis_id]
            obs_c = len(associated)
            obs_r = _rate(obs_c, n)
            others = frozenset().union(
                *(fail_in_slice[i] for i in primary_ids if i != hyp.hypothesis_id)
            ) if primary_ids else frozenset()
            overlap = associated & others
            exclusive = associated - others
            include = _include_in_union(hyp, config) and slice_.resolvable
            if include:
                upper_c, upper_r = obs_c, obs_r
            elif slice_.resolvable:
                upper_c, upper_r = obs_c, obs_r
            else:
                upper_c, upper_r = None, None
            plaus_c, plaus_r, plaus_na, plaus_method = _plausible_excess(
                slice_, fail_keys, n, hyp, config
            )
            if hyp.conflicting_detectors:
                plaus_c, plaus_r, plaus_na, plaus_method = None, None, True, "blocked_by_conflicting_detectors"
            status = _status(
                resolvable=slice_.resolvable,
                association=hyp.association_class,
                overlap=len(overlap) if include else 0,
                plausible_unavailable=plaus_na,
                upper_bound_rate=upper_r if include else None,
            )
            flags = ["NOT_ELIGIBLE_FOR_PRODUCTION"]
            if len(overlap) and include:
                flags.append("OVERLAPPING")
            if hyp.family == "TEST" and hyp.detail == "LIMIT_SENSITIVITY":
                flags.append("DOES_NOT_MODIFY_LIMITS")
            method = (
                f"observed=fails_in_affected/{n}; upper_bound=observed_associated_loss; "
                f"plausible={plaus_method}; attribution={attribution_mode}"
            )
            assumptions = [
                "Upper bound assumes every first-pass fail in the slice is recoverable, which is usually false.",
                "evidence_score is not a probability of recoverable yield.",
                "Plausible excess-rate recipe is PRELIMINARY and TO_BE_CALIBRATED.",
                f"Attribution mode is {attribution_mode}; primary and any-fail are not mixed silently.",
            ]
            limitations = [
                DISCLAIMER,
                "UNCONFIRMED hypothesis. not_a_root_cause remains true. This is not a production action.",
            ]
            if hyp.association_class == "SECONDARY_ASSOCIATION":
                limitations.append(
                    "Secondary association is excluded from the non-double-counted union by default."
                )
            if hyp.family == "TEST" and hyp.detail == "LIMIT_SENSITIVITY":
                limitations.append(
                    "Near-limit opportunity does not modify limits and does not propose a candidate limit."
                )
            if hyp.family == "TEST" and hyp.detail == "SEQUENCE":
                limitations.append(
                    "Later-test observations are censored by stop-on-fail behavior. Sequence opportunity is not invented."
                )
            limitations.extend(hyp.data_gaps)
            opportunities.append(
                Opportunity(
                    opportunity_id=f"OPP-{hyp.hypothesis_id}",
                    hypothesis_id=hyp.hypothesis_id,
                    family=hyp.family,
                    detail=hyp.detail,
                    association_class=hyp.association_class,
                    attribution_mode=attribution_mode,
                    status=status,  # type: ignore[arg-type]
                    status_flags=flags,
                    observed_loss_count=obs_c,
                    observed_loss_rate=obs_r,
                    upper_bound_count=upper_c,
                    upper_bound_rate=upper_r,
                    plausible_count=plaus_c,
                    plausible_rate=plaus_r,
                    plausible_unavailable=plaus_na,
                    safety_eligible_production_count=0,
                    safety_eligible_production_rate=0.0,
                    overlap_count=len(overlap),
                    union_count=len(union_fail) if include else None,
                    exclusive_count=len(exclusive) if include else len(associated),
                    intersection_count=len(overlap),
                    included_in_union=include,
                    evidence_tier=hyp.evidence_tier,
                    evidence_score=hyp.evidence_score,
                    eligible_population=n,
                    affected_population_count=len(slice_.affected),
                    population_definition=slice_.definition,
                    affected_die_ids=sorted(slice_.affected),
                    calculation_method=method,
                    calibration_status="PRELIMINARY",
                    assumptions=assumptions,
                    data_gaps=list(slice_.data_gaps) + list(hyp.data_gaps),
                    limitations=list(dict.fromkeys(limitations)),
                    statement=_statement(hyp, obs_r) if slice_.resolvable else "Population could not be established; no numerical opportunity invented.",
                    disclaimer=DISCLAIMER,
                )
            )
        items = opportunities

        if len(primary_ids) >= 2:
            union_c = len(union_fail)
            inter = None
            if len(primary_ids) == 2:
                a, b = primary_ids[0], primary_ids[1]
                inter = fail_in_slice[a] & fail_in_slice[b]
            else:
                inter_set = fail_in_slice[primary_ids[0]]
                for pid in primary_ids[1:]:
                    inter_set = inter_set & fail_in_slice[pid]
                inter = inter_set
            sum_u = sum(o.upper_bound_rate or 0.0 for o in items if o.included_in_union)
            items.append(
                Opportunity(
                    opportunity_id="OPP-UNION-PRIMARY",
                    hypothesis_id=None,
                    family="UNION",
                    detail="PRIMARY_EVIDENCE",
                    association_class="PRIMARY_EVIDENCE",
                    attribution_mode=attribution_mode,
                    status="OVERLAPPING" if inter else "ESTIMATED",
                    status_flags=["NOT_ELIGIBLE_FOR_PRODUCTION", "OVERLAPPING"],
                    observed_loss_count=union_c,
                    observed_loss_rate=_rate(union_c, n),
                    upper_bound_count=union_c,
                    upper_bound_rate=_rate(union_c, n),
                    plausible_count=None,
                    plausible_rate=None,
                    plausible_unavailable=True,
                    safety_eligible_production_count=0,
                    safety_eligible_production_rate=0.0,
                    overlap_count=len(inter or []),
                    union_count=union_c,
                    exclusive_count=union_c - len(inter or []),
                    intersection_count=len(inter or []),
                    included_in_union=True,
                    eligible_population=n,
                    affected_population_count=union_c,
                    population_definition="union of PRIMARY_EVIDENCE affected failed dies; not a sum of rates",
                    affected_die_ids=sorted(union_fail),
                    calculation_method="union_of_primary_associated_fails; individuals are not added",
                    calibration_status="PRELIMINARY",
                    assumptions=["Combined opportunity is the union, not the sum, of overlapping slices."],
                    limitations=[DISCLAIMER, f"sum_of_individual_upper_bounds_rate={round(sum_u, 6)} may exceed observed FPY loss."],
                    statement=(
                        f"Combined union of primary associated loss is {round(100.0 * _rate(union_c, n), 4)} "
                        "percentage points; this is not the sum of individual hypotheses and is not a predicted FPY gain."
                    ),
                    disclaimer=DISCLAIMER,
                )
            )

    included = [o for o in items if o.included_in_union and o.hypothesis_id]
    sum_upper = round(sum(o.upper_bound_rate or 0.0 for o in included), 6)
    if included:
        union_fail_all = frozenset().union(*(frozenset(fail_in_slice[o.hypothesis_id]) for o in included if o.hypothesis_id in fail_in_slice))
    else:
        union_fail_all = frozenset()
    union_c = len(union_fail_all)
    inter_c = 0
    if len(included) >= 2:
        running = fail_in_slice[included[0].hypothesis_id]
        for o in included[1:]:
            running = running & fail_in_slice[o.hypothesis_id]
        inter_c = len(running)

    plaus_rates = [o.plausible_rate for o in included if o.plausible_rate is not None]
    if not plaus_rates:
        plaus_total, plaus_na = None, True
    elif inter_c > 0:
        plaus_total = round(min(sum(plaus_rates), observed_rate), 6)
        plaus_na = False
    else:
        plaus_total = round(sum(plaus_rates), 6)
        plaus_na = False

    summary = OpportunitySummary(
        current_fpy=current_fpy,
        eligible_population=n,
        observed_loss_count=observed_count,
        observed_loss_rate=observed_rate,
        attribution_mode=attribution_mode,
        sum_of_individual_upper_bounds_rate=sum_upper,
        sum_of_individual_upper_bounds_exceeds_observed=sum_upper > observed_rate + 1e-12,
        union_upper_bound_count=union_c,
        union_upper_bound_rate=_rate(union_c, n),
        intersection_fail_count=inter_c,
        plausible_total_rate=plaus_total,
        plausible_unavailable=plaus_na,
        safety_eligible_total_count=0,
        safety_eligible_total_rate=0.0,
        no_actionable_opportunity=no_actionable,
        calculation_method=(
            "overall observed_loss = first_pass_fails / eligible; "
            "union_upper_bound = unique failed dies in PRIMARY slices; "
            "sum_of_individual_upper_bounds is labeled and may exceed observed loss"
        ),
        calibration_status="PRELIMINARY",
    )
    limitations = [
        DISCLAIMER,
        "Opportunity estimates are analytical. They are not production recommendations, ATE writes, or limit changes.",
        "safety_eligible_production is immutable 0 from configs/safety_policy.yaml.",
        "Do not interpret upper_bound as promised FPY gain.",
    ]
    if no_actionable:
        limitations.append("No actionable opportunity identified. Overall observed FPY loss is reported without invented causes.")
    return OpportunityBundle(
        analysis_id=hypotheses.analysis_id,
        attribution_mode=attribution_mode,
        summary=summary,
        opportunities=items,
        no_actionable_opportunity=no_actionable,
        data_gaps=list(hypotheses.data_gaps),
        limitations=limitations,
        disclaimer=DISCLAIMER,
        calibration_status="PRELIMINARY",
        config_versions={
            "safety_policy": config.safety.policy_version,
            "calibration": config.calibration.calibration_version,
            "fpy_policy": config.fpy.fpy_policy_version,
        },
    )


def estimate_from_dir(
    dataset_dir: str | Path,
    config: AppConfig | None = None,
    *,
    attribution_mode: AttributionMode = "PRIMARY_FAILURE",
) -> OpportunityBundle:
    folder = Path(dataset_dir)
    cfg = config or load_config()
    attempts = load_die_attempts(folder / "die_attempts.csv", cfg).attempts
    tests: list[TestResult] = []
    tr = folder / "test_results.csv"
    if tr.is_file():
        tests = load_test_results(tr, cfg).test_results
    parametric: list[ParametricMeasurement] = []
    pm = folder / "parametric_measurements.csv"
    if pm.is_file():
        parametric = load_parametric_measurements(pm, cfg).parametric
    return estimate_from_records(
        attempts,
        cfg,
        test_results=tests,
        parametric=parametric,
        analysis_id=folder.name,
        attribution_mode=attribution_mode,
    )


def estimate_from_records(
    attempts: list[DieAttempt],
    config: AppConfig,
    *,
    test_results: list[TestResult] | None = None,
    parametric: list[ParametricMeasurement] | None = None,
    analysis_id: str = "unknown",
    attribution_mode: AttributionMode = "PRIMARY_FAILURE",
) -> OpportunityBundle:
    tests = test_results or []
    params = parametric or []
    ctx = build_context(attempts, config, test_results=tests, parametric=params)
    detectors = run_detectors(attempts, config, test_results=tests, parametric=params)
    fpy = calculate_fpy(attempts, config, test_results=tests)
    hyps = compose(detectors, config, fpy=fpy.fpy, analysis_id=analysis_id)
    return estimate_opportunities(hyps, ctx, config, attribution_mode=attribution_mode)
