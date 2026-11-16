"""Scenario injectors. Each mutates DieState.fail_p / measurements; does not write labels."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from yield_improvement.synthetic.baseline import DieState, Profile, radius_quantile
from yield_improvement.synthetic.config import SyntheticConfig
from yield_improvement.synthetic.ground_truth import TrueCause


@dataclass
class InjectionResult:
    true_causes: list[TrueCause]
    injected_parameters: dict[str, Any]
    affected_population: dict[str, Any]
    expected_signal: str
    confounders: list[str]
    difficulty: str
    notes: str | None = None
    flags: dict[str, Any] = field(default_factory=dict)


Injector = Callable[
    [SyntheticConfig, random.Random, list[DieState], Profile, dict[str, Any]],
    InjectionResult,
]


def _params(cfg: SyntheticConfig, scenario_id: str) -> dict[str, Any]:
    return dict(cfg.scenarios.get(scenario_id, {}))


def _lot_ids(dies: list[DieState]) -> list[str]:
    seen: list[str] = []
    for die in dies:
        if die.lot_id not in seen:
            seen.append(die.lot_id)
    return seen


def _wafer_keys(dies: list[DieState]) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for die in dies:
        key = (die.lot_id, die.wafer_id)
        if key not in seen:
            seen.append(key)
    return seen


def apply_s01(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    for die in dies:
        die.fail_p = min(0.95, die.fail_p + extra)
    return InjectionResult(
        true_causes=[TrueCause(family="RANDOM", detail="FAILURE")],
        injected_parameters={"extra_p": extra},
        affected_population={"rule": "all_dies_iid", "n_targeted": len(dies), "n_total": len(dies)},
        expected_signal="No strong systematic association with wafer position, equipment, lot, time, or temperature.",
        confounders=["baseline_lot_wafer_die_noise"],
        difficulty="easy",
        notes="Random extra fails independent of covariates.",
    )


def apply_s02(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    q = float(params["edge_radius_quantile"])
    threshold = radius_quantile([d.r for d in dies], q)
    n = 0
    for die in dies:
        if die.r >= threshold:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="SPATIAL", detail="EDGE")],
        injected_parameters={"extra_p": extra, "edge_radius_quantile": q, "radius_threshold": threshold},
        affected_population={"rule": f"r >= {threshold:.4f}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Higher failure concentration near wafer edge.",
        confounders=["baseline_spatial_noise"],
        difficulty="medium",
        flags={"radius_threshold": threshold, "mode": "edge"},
    )


def apply_s03(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    q = float(params["center_radius_quantile"])
    threshold = radius_quantile([d.r for d in dies], q)
    n = 0
    for die in dies:
        if die.r <= threshold:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="SPATIAL", detail="CENTER")],
        injected_parameters={"extra_p": extra, "center_radius_quantile": q, "radius_threshold": threshold},
        affected_population={"rule": f"r <= {threshold:.4f}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Central concentration of failures.",
        confounders=["baseline_spatial_noise"],
        difficulty="medium",
        flags={"radius_threshold": threshold, "mode": "center"},
    )


def apply_s04(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    q_in = float(params["ring_inner_quantile"])
    q_out = float(params["ring_outer_quantile"])
    radii = [d.r for d in dies]
    inner = radius_quantile(radii, q_in)
    outer = radius_quantile(radii, q_out)
    n = 0
    for die in dies:
        if inner <= die.r <= outer:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="SPATIAL", detail="RING")],
        injected_parameters={
            "extra_p": extra,
            "ring_inner_quantile": q_in,
            "ring_outer_quantile": q_out,
            "inner": inner,
            "outer": outer,
        },
        affected_population={"rule": f"{inner:.4f} <= r <= {outer:.4f}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Ring-shaped spatial failure pattern.",
        confounders=["baseline_spatial_noise"],
        difficulty="medium",
        flags={"inner": inner, "outer": outer, "mode": "ring"},
    )


def apply_s05(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    tester = str(params["affected_tester"])
    n = 0
    for die in dies:
        if die.tester_id == tester:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="EQUIPMENT", detail="DEGRADATION")],
        injected_parameters={"extra_p": extra, "affected_tester": tester},
        affected_population={"rule": f"tester_id == {tester}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Failure rate differs by equipment/tester.",
        confounders=["baseline_tester_offsets_are_small_and_not_the_planted_cause"],
        difficulty="medium",
    )


def apply_s06(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p_per_lot"])
    n_lots = profile.n_lots
    for die in dies:
        die.fail_p = min(0.95, die.fail_p + extra * die.lot_index)
    return InjectionResult(
        true_causes=[TrueCause(family="PROCESS", detail="DRIFT")],
        injected_parameters={"extra_p_per_lot": extra, "n_lots": n_lots},
        affected_population={"rule": "fail_p += extra_p_per_lot * lot_index", "n_targeted": len(dies), "n_total": len(dies)},
        expected_signal="Temporal degradation / later lots have higher failure rate.",
        confounders=["lot_to_lot_baseline_noise"],
        difficulty="medium",
    )


def apply_s07(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    hot = float(params["hot_threshold_c"])
    n = 0
    for die in dies:
        if die.temperature_c >= hot:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="ENVIRONMENT", detail="TEMPERATURE")],
        injected_parameters={"extra_p": extra, "hot_threshold_c": hot},
        affected_population={"rule": f"temperature_c >= {hot}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Failure rate changes with temperature.",
        confounders=["temperature_overlaps_lots_and_testers"],
        difficulty="medium",
    )


def apply_s08(cfg, rng, dies, profile, params) -> InjectionResult:
    extra_mean = float(params["extra_mean"])
    fraction = float(params["affected_lot_fraction"])
    parameter = str(params["parameter"])
    spec = cfg.parametric[parameter]
    lots = _lot_ids(dies)
    n_bad = max(1, int(round(fraction * len(lots))))
    bad_lots = set(rng.sample(lots, n_bad))
    n = 0
    for die in dies:
        if die.lot_id in bad_lots:
            mean = spec.pass_mean + extra_mean
            die.measurements[parameter] = rng.gauss(mean, spec.pass_sd)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="PARAMETRIC", detail="SHIFT")],
        injected_parameters={
            "extra_mean": extra_mean,
            "parameter": parameter,
            "affected_lots": sorted(bad_lots),
            "limits_unchanged": True,
            "upper_limit": spec.upper_limit,
        },
        affected_population={"rule": "selected lots", "affected_lots": sorted(bad_lots), "n_targeted": n, "n_total": len(dies)},
        expected_signal="Parameter distribution shift on affected lots.",
        confounders=["unaffected_lots_keep_baseline_distribution"],
        difficulty="medium",
        flags={"parametric": True, "parameter": parameter},
    )


def apply_s09(cfg, rng, dies, profile, params) -> InjectionResult:
    parameter = str(params["parameter"])
    spec = cfg.parametric[parameter]
    limit = spec.upper_limit
    if limit is None:
        raise ValueError("S09 requires an upper_limit")
    lo = float(params["near_limit_lo"]) * limit
    hi = float(params["near_limit_hi"]) * limit
    for die in dies:
        die.measurements[parameter] = rng.uniform(lo, hi)
    return InjectionResult(
        true_causes=[TrueCause(family="TEST", detail="LIMIT_SENSITIVITY")],
        injected_parameters={
            "parameter": parameter,
            "near_limit_lo": params["near_limit_lo"],
            "near_limit_hi": params["near_limit_hi"],
            "production_upper_limit": limit,
            "limits_modified": False,
        },
        affected_population={"rule": "all_dies_near_limit_measurements", "n_targeted": len(dies), "n_total": len(dies)},
        expected_signal="Measurements concentrated near the production limit; some pass, some fail.",
        confounders=["production_limits_are_unchanged"],
        difficulty="hard",
        flags={"parametric": True, "parameter": parameter, "tight_limit": True},
        notes="tight_limit is hidden; never written to agent-visible tables. Limits are not modified.",
    )


def apply_s10(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    retest_pass_rate = float(params["retest_pass_rate"])
    code = str(params["failure_code"])
    card = cfg.probe_cards[0]
    n = 0
    for die in dies:
        if die.probe_card_id == card:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="CONTACT", detail="PROBE")],
        injected_parameters={
            "extra_p": extra,
            "affected_probe_card": card,
            "retest_pass_rate": retest_pass_rate,
            "failure_code": code,
        },
        affected_population={"rule": f"probe_card_id == {card}", "n_targeted": n, "n_total": len(dies)},
        expected_signal="Failures associated with contact/probe conditions; some recover on retest.",
        confounders=["other_probe_cards_remain_populated"],
        difficulty="medium",
        flags={"force_failure_code": code, "retest_pass_rate": retest_pass_rate, "affected_probe_card": card},
    )


def apply_s11(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    normal = {t.test_id: t.sequence_index for t in cfg.tests}
    swapped = dict(normal)
    if "T_IDDQ" in swapped and "T_FUNC" in swapped:
        swapped["T_IDDQ"], swapped["T_FUNC"] = swapped["T_FUNC"], swapped["T_IDDQ"]
    n_normal = 0
    for die in dies:
        if rng.random() < 0.5:
            die.sequence_by_test = dict(normal)
            n_normal += 1
        else:
            die.sequence_by_test = dict(swapped)
    return InjectionResult(
        true_causes=[TrueCause(family="TEST", detail="SEQUENCE")],
        injected_parameters={"extra_p": extra, "preceding_test": "T_IDDQ", "dependent_test": "T_FUNC"},
        affected_population={
            "rule": "P(T_FUNC fail | T_IDDQ fail and IDDQ precedes FUNC) elevated",
            "n_normal_order": n_normal,
            "n_total": len(dies),
        },
        expected_signal="Conditional failure relationship with test sequence/order.",
        confounders=["half_of_dies_use_swapped_order"],
        difficulty="hard",
        flags={"sequence": True, "extra_p": extra},
    )


def apply_s12(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    n_bad = int(params["n_bad_lots"])
    lots = _lot_ids(dies)
    bad = set(rng.sample(lots, min(n_bad, len(lots))))
    n = 0
    for die in dies:
        if die.lot_id in bad:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    return InjectionResult(
        true_causes=[TrueCause(family="PROCESS", detail="LOT_VARIATION")],
        injected_parameters={"extra_p": extra, "affected_lots": sorted(bad)},
        affected_population={"rule": "selected lots", "affected_lots": sorted(bad), "n_targeted": n, "n_total": len(dies)},
        expected_signal="One or more lots have elevated failure rates.",
        confounders=["other_lots_keep_baseline_variation"],
        difficulty="easy",
    )


def apply_s13(cfg, rng, dies, profile, params) -> InjectionResult:
    extra = float(params["extra_p"])
    n_bad = int(params["n_bad_wafers"])
    wafers = _wafer_keys(dies)
    bad = set(rng.sample(wafers, min(n_bad, len(wafers))))
    n = 0
    for die in dies:
        if (die.lot_id, die.wafer_id) in bad:
            die.fail_p = min(0.95, die.fail_p + extra)
            n += 1
    labeled = [f"{lot}/{wafer}" for lot, wafer in sorted(bad)]
    return InjectionResult(
        true_causes=[TrueCause(family="PROCESS", detail="WAFER_VARIATION")],
        injected_parameters={"extra_p": extra, "affected_wafers": labeled},
        affected_population={"rule": "selected wafers", "affected_wafers": labeled, "n_targeted": n, "n_total": len(dies)},
        expected_signal="Specific wafers have elevated failure rates.",
        confounders=["within_wafer_baseline_variation"],
        difficulty="medium",
    )


def apply_s14(cfg, rng, dies, profile, params) -> InjectionResult:
    joint_p = float(params["joint_p"])
    single_p = float(params["single_p"])
    n_joint = 0
    for die in dies:
        draw = rng.random()
        if draw < joint_p:
            die.fail_test_ids = ["T_IDDQ", "T_FUNC"]
            die.failed = True
            n_joint += 1
        elif draw < joint_p + single_p:
            die.fail_test_ids = [rng.choice(["T_IDDQ", "T_FUNC"])]
            die.failed = True
        # else leave to baseline bernoulli in realize
    return InjectionResult(
        true_causes=[TrueCause(family="CORRELATED", detail="FAILURES")],
        injected_parameters={"joint_p": joint_p, "single_p": single_p, "modes": ["IDDQ", "FUNCTIONAL"]},
        affected_population={"rule": "joint IDDQ+FUNCTIONAL association", "n_joint": n_joint, "n_total": len(dies)},
        expected_signal="Two failure modes are statistically associated, not deterministic.",
        confounders=["some_single_mode_fails"],
        difficulty="medium",
        flags={"correlated": True},
    )


def apply_s15(cfg, rng, dies, profile, params) -> InjectionResult:
    extra_edge = float(params["extra_p_edge"])
    extra_lot = float(params["extra_p_per_lot"])
    q = float(params["edge_radius_quantile"])
    threshold = radius_quantile([d.r for d in dies], q)
    n_edge = 0
    for die in dies:
        die.fail_p = min(0.95, die.fail_p + extra_lot * die.lot_index)
        if die.r >= threshold:
            die.fail_p = min(0.95, die.fail_p + extra_edge)
            n_edge += 1
    return InjectionResult(
        true_causes=[
            TrueCause(family="SPATIAL", detail="EDGE"),
            TrueCause(family="PROCESS", detail="DRIFT"),
        ],
        injected_parameters={
            "extra_p_edge": extra_edge,
            "extra_p_per_lot": extra_lot,
            "radius_threshold": threshold,
        },
        affected_population={"rule": "edge dies + temporal drift", "n_edge_targeted": n_edge, "n_total": len(dies)},
        expected_signal="Competing explanations: spatial edge plus process drift.",
        confounders=["baseline_noise"],
        difficulty="hard",
        flags={"radius_threshold": threshold, "mode": "edge"},
    )


def apply_s16(cfg, rng, dies, profile, params) -> InjectionResult:
    return InjectionResult(
        true_causes=[TrueCause(family="NONE", detail="NO_CONFIDENT_ROOT_CAUSE")],
        injected_parameters={},
        affected_population={"rule": "none", "n_targeted": 0, "n_total": len(dies)},
        expected_signal="Only normal process variation and random noise. No planted systematic cause.",
        confounders=["baseline_lot_wafer_die_tester_noise"],
        difficulty="easy",
        notes="Future agent should return NO_CONFIDENT_ROOT_CAUSE.",
    )


REGISTRY: dict[str, Injector] = {
    "S01": apply_s01,
    "S02": apply_s02,
    "S03": apply_s03,
    "S04": apply_s04,
    "S05": apply_s05,
    "S06": apply_s06,
    "S07": apply_s07,
    "S08": apply_s08,
    "S09": apply_s09,
    "S10": apply_s10,
    "S11": apply_s11,
    "S12": apply_s12,
    "S13": apply_s13,
    "S14": apply_s14,
    "S15": apply_s15,
    "S16": apply_s16,
}

CORE_SCENARIOS = tuple(REGISTRY.keys())


def apply_scenario(
    scenario_id: str,
    cfg: SyntheticConfig,
    rng: random.Random,
    dies: list[DieState],
    profile: Profile,
) -> InjectionResult:
    if scenario_id not in REGISTRY:
        raise ValueError(f"Unknown scenario {scenario_id!r}")
    params = _params(cfg, scenario_id)
    return REGISTRY[scenario_id](cfg, rng, dies, profile, params)
