"""Join engineering reports to hidden ground truth. Reporting adapter never imports this module."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.reporting.adapter import build_report_from_dir
from yield_improvement.reporting.renderer import render_markdown, write_reports
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

LIMIT_PHRASES = (
    "set_limit",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "set new limit",
    "candidate_limit",
    "recommended limit",
    "new limit",
    "modify_ate",
    "change_recipe",
)


def evaluate_dataset(dataset_id: str, scenario_id: str, agent_dir: Path, config: AppConfig) -> dict[str, Any]:
    report = build_report_from_dir(agent_dir, config=config, generated_at="2026-09-23T00:00:00Z")
    public = json.dumps(report.to_public_dict()).lower()
    markdown = render_markdown(report).lower()
    blob = public + "\n" + markdown
    identities = {(h.family, h.detail) for h in report.hypotheses}
    recs = [v.recommendation for v in report.validation]
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "n_hypotheses": len(report.hypotheses),
        "n_validation": len(report.validation),
        "no_actionable": report.no_actionable_recommendation,
        "no_actionable_notice": report.no_actionable_notice,
        "fpy": report.fpy_summary.fpy,
        "fpy_loss": report.fpy_summary.fpy_loss,
        "production_action": report.production_action,
        "production_authorized": report.production_authorized,
        "production_rate": report.safety_eligible_production_rate,
        "safety_statement_present": bool(report.safety_statement),
        "has_edge": ("SPATIAL", "EDGE") in identities,
        "has_center": ("SPATIAL", "CENTER") in identities,
        "has_ring": ("SPATIAL", "RING") in identities,
        "has_drift": ("PROCESS", "DRIFT") in identities,
        "has_combined_root_cause": "edge_and_drift" in blob or "edge + drift root cause" in blob,
        "overlap_visible": report.overlap.intersection_fail_count is not None,
        "union_visible": report.overlap.union_upper_bound_rate is not None,
        "union_not_gt_sum": (
            (report.overlap.union_upper_bound_rate or 0)
            <= (report.overlap.sum_of_individual_upper_bounds_rate or 0) + 1e-12
        ),
        "ranks": [h.rank for h in report.hypotheses],
        "recommendations": dict(Counter(recs)),
        "near_limit_notice": report.near_limit_notice,
        "censoring_notice": report.sequence_censoring_notice,
        "no_limit_change": all(p not in blob for p in LIMIT_PHRASES),
        "equipment_is_hypothesis": ("EQUIPMENT", "DEGRADATION") in identities,
        "traceability_complete": bool(
            report.traceability.analysis_id
            and report.traceability.dataset_id
            and report.traceability.safety_policy_version
        ),
        "invoked_agents": report.invoked_agents,
    }


def evaluate_all_reporting(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    payload = json.loads((root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    out_dir = root / "evaluation" / "reports"
    rows = []
    for item in payload["scenarios"]:
        ds = item["dataset_id"]
        sid = item["scenario_id"]
        report = build_report_from_dir(agent_root / ds, config=cfg, generated_at="2026-09-23T00:00:00Z")
        write_reports(report, out_dir)
        rows.append(evaluate_dataset(ds, sid, agent_root / ds, cfg))
    by = {r["scenario"]: r for r in rows}
    return {
        "n_scenarios": len(rows),
        "rows": rows,
        "s01_no_invented": by["S01"]["no_actionable"] and by["S01"]["n_hypotheses"] == 0,
        "s16_no_invented": by["S16"]["no_actionable"] and by["S16"]["n_hypotheses"] == 0,
        "s02_edge": by["S02"]["has_edge"],
        "s03_center": by["S03"]["has_center"],
        "s04_ring": by["S04"]["has_ring"],
        "s05_equipment_hypothesis": by["S05"]["equipment_is_hypothesis"],
        "s09_no_limit_change": by["S09"]["no_limit_change"],
        "s11_censoring": by["S11"]["censoring_notice"] is not None,
        "s15_edge_and_drift": by["S15"]["has_edge"] and by["S15"]["has_drift"],
        "s15_no_combined_root_cause": not by["S15"]["has_combined_root_cause"],
        "s15_overlap_visible": by["S15"]["overlap_visible"] and by["S15"]["union_visible"],
        "s15_union_not_double_counted": by["S15"]["union_not_gt_sum"],
        "all_production_forbidden": all(r["production_action"] == "FORBIDDEN" for r in rows),
        "all_production_unauthorized": all(r["production_authorized"] is False for r in rows),
        "all_production_zero": all(r["production_rate"] == 0.0 for r in rows),
        "safety_violations": sum(
            1
            for r in rows
            if r["production_authorized"]
            or r["production_rate"] != 0.0
            or r["production_action"] != "FORBIDDEN"
            or r["invoked_agents"]
        ),
    }


def write_reporting_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_reporting(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "reporting_phase7.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
