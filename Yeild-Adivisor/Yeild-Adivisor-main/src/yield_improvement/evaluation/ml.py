"""Join ML outputs to hidden ground truth AFTER predictions. The ML package never imports this."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.ml.pipeline import run_ml, run_ml_and_compose
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

EXPECTED = {
    "S01": None,
    "S02": ("SPATIAL", "EDGE"),
    "S03": ("SPATIAL", "CENTER"),
    "S04": ("SPATIAL", "RING"),
    "S05": ("EQUIPMENT", "DEGRADATION"),
    "S06": ("PROCESS", "DRIFT"),
    "S07": ("ENVIRONMENT", "TEMPERATURE"),
    "S08": ("PARAMETRIC", "SHIFT"),
    "S09": ("TEST", "LIMIT_SENSITIVITY"),
    "S10": ("CONTACT", "PROBE"),
    "S11": ("TEST", "SEQUENCE"),
    "S12": ("PROCESS", "LOT_VARIATION"),
    "S13": ("PROCESS", "WAFER_VARIATION"),
    "S14": ("CORRELATED", "FAILURES"),
    "S15": ("SPATIAL", "EDGE"),
    "S16": None,
}

LIMIT_PHRASES = (
    "set_limit",
    "increase limit",
    "decrease limit",
    "change limit",
    "optimize limit",
    "set new limit",
    "candidate limit",
)


def evaluate_dataset_ml(dataset_id: str, scenario_id: str, agent_dir: Path, config: AppConfig) -> dict[str, Any]:
    ml_result, hyps = run_ml_and_compose(agent_dir, config=config, persist=False)
    blob = json.dumps(ml_result.to_public_dict()).lower()
    identities = {(e.family, e.detail) for e in ml_result.evidence}
    expected = EXPECTED.get(scenario_id)
    if expected is None:
        status = "NO_FORCED_HYPOTHESIS"
        detected = None
    elif expected in identities:
        status = "SUPPORTIVE"
        detected = f"{expected[0]}.{expected[1]}"
    elif identities:
        status = "DIVERGENT"
        detected = ",".join(f"{a}.{b}" for a, b in sorted(identities))
    else:
        status = "ABSENT"
        detected = None
    attached = any(any(isinstance(e, dict) and e.get("source") == "ml" for e in h.evidence) for h in hyps.hypotheses)
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "model_name": ml_result.model_name,
        "metrics": ml_result.metrics.model_dump(),
        "top_features": [r["feature"] for r in ml_result.feature_importance[:8]],
        "failure_capture_top10": ml_result.metrics.failure_capture_at_top_10_percent,
        "failure_capture_top20": ml_result.metrics.failure_capture_at_top_20_percent,
        "expected_signal": None if expected is None else f"{expected[0]}.{expected[1]}",
        "model_detected_signal": detected,
        "detection_status": status,
        "n_ml_evidence": len(ml_result.evidence),
        "ml_attached_to_hypothesis": attached,
        "n_hypotheses": len(hyps.hypotheses),
        "no_confident_hypothesis": hyps.no_confident_hypothesis,
        "has_edge": any(h.family == "SPATIAL" and h.detail == "EDGE" for h in hyps.hypotheses),
        "has_drift": any(h.family == "PROCESS" and h.detail == "DRIFT" for h in hyps.hypotheses),
        "combined_root_cause": any("EDGE_AND_DRIFT" in h.hypothesis_id for h in hyps.hypotheses),
        "no_limit_change": all(p not in blob for p in LIMIT_PHRASES),
        "production_authorized": ml_result.production_authorized,
        "production_rate": ml_result.safety_eligible_production_rate,
        "not_a_root_cause": ml_result.not_a_root_cause,
        "limitations": list(ml_result.limitations),
    }


def evaluate_all_ml(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    payload = json.loads((root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    rows = [
        evaluate_dataset_ml(item["dataset_id"], item["scenario_id"], agent_root / item["dataset_id"], cfg)
        for item in payload["scenarios"]
    ]
    by = {r["scenario"]: r for r in rows}
    first = rows[0]
    return {
        "n_scenarios": len(rows),
        "selected_model": first["model_name"],
        "rows": rows,
        "s16_no_forced": by["S16"]["no_confident_hypothesis"] is True,
        "s15_separate": by["S15"]["has_edge"] and by["S15"]["has_drift"] and not by["S15"]["combined_root_cause"],
        "s09_no_limit_change": by["S09"]["no_limit_change"],
        "all_production_unauthorized": all(r["production_authorized"] is False for r in rows),
        "all_production_zero": all(r["production_rate"] == 0.0 for r in rows),
        "ml_reaches_pipeline": any(r["ml_attached_to_hypothesis"] for r in rows),
    }


def write_ml_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_ml(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "ml_phase7.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
