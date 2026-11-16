"""Join opportunity outputs to hidden ground truth. Opportunity engine never imports this module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.opportunity.engine import estimate_from_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

EXPECTED_PRIMARY = {
    "S02": {("SPATIAL", "EDGE")},
    "S03": {("SPATIAL", "CENTER")},
    "S04": {("SPATIAL", "RING")},
    "S05": {("EQUIPMENT", "DEGRADATION")},
    "S06": {("PROCESS", "DRIFT")},
    "S07": {("ENVIRONMENT", "TEMPERATURE")},
    "S08": {("PARAMETRIC", "SHIFT")},
    "S09": {("TEST", "LIMIT_SENSITIVITY")},
    "S12": {("PROCESS", "LOT_VARIATION")},
    "S13": {("PROCESS", "WAFER_VARIATION")},
    "S14": {("CORRELATED", "FAILURES")},
    "S15": {("SPATIAL", "EDGE"), ("PROCESS", "DRIFT")},
}


def evaluate_dataset(dataset_id: str, scenario_id: str, agent_dir: Path, config: AppConfig) -> dict[str, Any]:
    bundle = estimate_from_dir(agent_dir, config=config)
    public = bundle.to_public_dict()
    rows = []
    for item in bundle.opportunities:
        if item.hypothesis_id is None:
            continue
        rows.append(
            {
                "scenario": scenario_id,
                "dataset_id": dataset_id,
                "hypothesis": f"{item.family}.{item.detail}",
                "hypothesis_id": item.hypothesis_id,
                "observed_loss": item.observed_loss_rate,
                "upper_bound": item.upper_bound_rate,
                "plausible": item.plausible_rate,
                "production_eligible": item.safety_eligible_production_rate,
                "overlap": item.overlap_count,
                "status": item.status,
                "included_in_union": item.included_in_union,
                "association_class": item.association_class,
            }
        )
    identities = {(o.family, o.detail) for o in bundle.opportunities if o.hypothesis_id}
    expected = EXPECTED_PRIMARY.get(scenario_id, set())
    missing = sorted(f"{f}.{d}" for f, d in expected - identities)
    if scenario_id in {"S10", "S11"}:
        missing = []
    s15 = {}
    if scenario_id == "S15":
        edge = next((o for o in bundle.opportunities if o.family == "SPATIAL" and o.detail == "EDGE"), None)
        drift = next((o for o in bundle.opportunities if o.family == "PROCESS" and o.detail == "DRIFT"), None)
        union = next((o for o in bundle.opportunities if o.opportunity_id == "OPP-UNION-PRIMARY"), None)
        s15 = {
            "both_present": edge is not None and drift is not None,
            "union_rate": bundle.summary.union_upper_bound_rate,
            "sum_individual": bundle.summary.sum_of_individual_upper_bounds_rate,
            "overlap_count": union.overlap_count if union else None,
            "union_le_sum": bundle.summary.union_upper_bound_rate
            <= bundle.summary.sum_of_individual_upper_bounds_rate + 1e-12,
        }
    s09_text = json.dumps(public)
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "no_actionable_opportunity": bundle.no_actionable_opportunity,
        "observed_loss": bundle.summary.observed_loss_rate,
        "union_upper_bound": bundle.summary.union_upper_bound_rate,
        "sum_of_individual_upper_bounds": bundle.summary.sum_of_individual_upper_bounds_rate,
        "sum_exceeds_observed": bundle.summary.sum_of_individual_upper_bounds_exceeds_observed,
        "plausible_total": bundle.summary.plausible_total_rate,
        "production_eligible": bundle.summary.safety_eligible_total_rate,
        "missing_expected": missing,
        "n_opportunities": len(rows),
        "rows": rows,
        "s15": s15,
        "s09_no_set_limit": "SET_LIMIT" not in s09_text and "increase test limit" not in s09_text.lower(),
        "s09_no_candidate_limit": "candidate_limit" not in s09_text,
        "all_production_zero": all(r["production_eligible"] == 0.0 for r in rows) and bundle.summary.safety_eligible_total_rate == 0.0,
    }


def evaluate_all_opportunities(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    payload = json.loads((root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    rows = []
    for item in payload["scenarios"]:
        rows.append(evaluate_dataset(item["dataset_id"], item["scenario_id"], agent_root / item["dataset_id"], cfg))
    by = {r["scenario"]: r for r in rows}
    return {
        "rows": rows,
        "n_scenarios": len(rows),
        "s01_no_actionable": by["S01"]["no_actionable_opportunity"],
        "s16_no_actionable": by["S16"]["no_actionable_opportunity"],
        "s15_both_present": bool(by["S15"]["s15"].get("both_present")),
        "s15_union_le_sum": bool(by["S15"]["s15"].get("union_le_sum")),
        "all_production_zero": all(r["all_production_zero"] for r in rows),
        "s09_no_limit_change": by["S09"]["s09_no_set_limit"] and by["S09"]["s09_no_candidate_limit"],
    }


def write_opportunity_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_opportunities(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "opportunity_phase5.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
