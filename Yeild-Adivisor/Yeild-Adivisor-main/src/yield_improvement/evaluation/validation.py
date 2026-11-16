"""Join validation outputs to hidden ground truth. Validator never imports this module."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root
from yield_improvement.validation.validator import validate_from_dir

LIMIT_PHRASES = (
    "set_limit",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "set new limit",
    "candidate_limit",
    "modify_ate",
    "change_recipe",
)


def evaluate_dataset(dataset_id: str, scenario_id: str, agent_dir: Path, config: AppConfig) -> dict[str, Any]:
    bundle = validate_from_dir(agent_dir, config=config)
    public = json.dumps(bundle.to_public_dict()).lower()
    rows = []
    for item in bundle.results:
        rows.append(
            {
                "scenario": scenario_id,
                "hypothesis": f"{item.family}.{item.detail}" if item.family else item.opportunity_id,
                "opportunity_id": item.opportunity_id,
                "recommendation": item.recommendation,
                "production_authorized": item.production_authorized,
                "production_action": item.production_action,
                "production_eligible": item.safety_eligible_production_rate,
                "overlap": item.overlap_count,
                "union_count": item.union_count,
                "invoked_agents": item.invoked_agents,
                "not_a_root_cause": item.not_a_root_cause,
            }
        )
    identities = {(r.family, r.detail) for r in bundle.results if r.hypothesis_id}
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "no_actionable_recommendation": bundle.no_actionable_recommendation,
        "observed_loss": bundle.observed_loss_rate,
        "n_results": len(rows),
        "recommendations": dict(Counter(r["recommendation"] for r in rows)),
        "rows": rows,
        "has_edge": ("SPATIAL", "EDGE") in identities,
        "has_center": ("SPATIAL", "CENTER") in identities,
        "has_ring": ("SPATIAL", "RING") in identities,
        "has_drift": ("PROCESS", "DRIFT") in identities,
        "has_combined_root_cause": any(
            r.family == "UNION" and r.recommendation == "INVESTIGATE" for r in bundle.results
        ),
        "union_review": any(r.opportunity_id == "OPP-UNION-PRIMARY" and r.recommendation == "REVIEW" for r in bundle.results),
        "overlap_summary": bundle.overlap_summary,
        "production_always_zero": bundle.safety_eligible_production_rate == 0.0
        and all(r["production_eligible"] == 0.0 for r in rows),
        "no_limit_change": all(p not in public for p in LIMIT_PHRASES),
        "no_invocations": bundle.invoked_agents == [] and all(r["invoked_agents"] == [] for r in rows),
        "sequence_investigate": any(
            r.family == "TEST" and r.detail == "SEQUENCE" and r.recommendation == "INVESTIGATE" for r in bundle.results
        ),
        "censoring_recorded": any("stop-on-fail" in n.lower() or "censored" in n.lower() for n in bundle.limitations),
        "all_not_a_root_cause": all(r["not_a_root_cause"] is True for r in rows) if rows else True,
    }


def evaluate_all_validation(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    payload = json.loads((root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    rows = [
        evaluate_dataset(item["dataset_id"], item["scenario_id"], agent_root / item["dataset_id"], cfg)
        for item in payload["scenarios"]
    ]
    by = {r["scenario"]: r for r in rows}
    dist: Counter[str] = Counter()
    for r in rows:
        dist.update(r["recommendations"])
    return {
        "rows": rows,
        "n_scenarios": len(rows),
        "recommendation_distribution": dict(dist),
        "s01_no_actionable": by["S01"]["no_actionable_recommendation"],
        "s16_no_actionable": by["S16"]["no_actionable_recommendation"],
        "s15_edge_and_drift": by["S15"]["has_edge"] and by["S15"]["has_drift"],
        "s15_no_combined_root_cause": not by["S15"]["has_combined_root_cause"],
        "s15_union_not_sum": by["S15"]["overlap_summary"].get("union_upper_bound_rate", 1) <= by["S15"]["overlap_summary"].get("sum_of_individual_upper_bounds_rate", 0) + 1e-12,
        "s09_no_limit_change": by["S09"]["no_limit_change"],
        "s11_no_sequence_investigate": not by["S11"]["sequence_investigate"],
        "s11_censoring_recorded": by["S11"]["censoring_recorded"],
        "all_production_zero": all(r["production_always_zero"] for r in rows),
        "no_invocations": all(r["no_invocations"] for r in rows),
        "all_not_a_root_cause": all(r["all_not_a_root_cause"] for r in rows),
        "safety_violations": sum(
            1
            for r in rows
            if (not r["production_always_zero"]) or (not r["no_limit_change"]) or (not r["no_invocations"])
        ),
    }


def write_validation_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_validation(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "validation_phase6.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
