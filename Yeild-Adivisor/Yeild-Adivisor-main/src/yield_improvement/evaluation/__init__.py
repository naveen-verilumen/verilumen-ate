"""Join detector outputs to hidden ground truth. Detectors never import this module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.runner import run_detectors_on_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

# Expected systematic detectors for each scenario. Others should be NO_SIGNAL
# (false positives are counted). no_signal is expected on S01/S16 only.
EXPECTED_SIGNALS: dict[str, dict[str, tuple[str, str]]] = {
    "S01": {"no_signal": ("NONE", "NO_MEANINGFUL_SIGNAL")},
    "S02": {"spatial": ("SPATIAL", "EDGE")},
    "S03": {"spatial": ("SPATIAL", "CENTER")},
    "S04": {"spatial": ("SPATIAL", "RING")},
    "S05": {"equipment": ("EQUIPMENT", "DEGRADATION")},
    "S06": {"temporal": ("PROCESS", "DRIFT")},
    "S07": {"temperature": ("ENVIRONMENT", "TEMPERATURE")},
    "S08": {"parametric": ("PARAMETRIC", "SHIFT")},
    "S09": {"near_limit": ("TEST", "LIMIT_SENSITIVITY")},
    "S10": {"contact": ("CONTACT", "PROBE")},
    "S11": {"sequence": ("TEST", "SEQUENCE")},
    "S12": {"lot": ("PROCESS", "LOT_VARIATION")},
    "S13": {"wafer": ("PROCESS", "WAFER_VARIATION")},
    "S14": {"correlation": ("CORRELATED", "FAILURES")},
    "S15": {
        "spatial": ("SPATIAL", "EDGE"),
        "temporal": ("PROCESS", "DRIFT"),
    },
    "S16": {"no_signal": ("NONE", "NO_MEANINGFUL_SIGNAL")},
}

FAMILY_MATCH: dict[str, str] = {
    "equipment": "EQUIPMENT",
    "spatial": "SPATIAL",
    "temporal": "PROCESS",
    "temperature": "ENVIRONMENT",
    "parametric": "PARAMETRIC",
    "near_limit": "TEST",
    "sequence": "TEST",
    "contact": "CONTACT",
    "lot": "PROCESS",
    "wafer": "PROCESS",
    "correlation": "CORRELATED",
    "no_signal": "NONE",
}


def _detail_ok(detector: str, expected_detail: str, observed_detail: str | None) -> bool:
    if detector in {"equipment", "contact", "lot", "wafer", "temperature"}:
        return True
    if detector == "no_signal":
        return observed_detail in {"NO_MEANINGFUL_SIGNAL", "INSUFFICIENT_EVIDENCE"}
    return observed_detail == expected_detail


def evaluate_dataset(
    dataset_id: str,
    scenario_id: str,
    agent_dir: Path,
    config: AppConfig,
) -> list[dict[str, Any]]:
    bundle = run_detectors_on_dir(agent_dir, config=config)
    expected = EXPECTED_SIGNALS.get(scenario_id, {})
    rows: list[dict[str, Any]] = []
    for detector, result in bundle.results.items():
        exp = expected.get(detector)
        observed_signal = result.status == "SIGNAL"
        expected_signal = exp is not None
        family_ok = True
        detail_ok = True
        if exp and observed_signal:
            family_ok = result.hypothesis_family == exp[0] or (
                detector in FAMILY_MATCH and result.hypothesis_family == FAMILY_MATCH[detector]
            )
            detail_ok = _detail_ok(detector, exp[1], result.hypothesis_detail)
        correct = expected_signal and observed_signal and family_ok and detail_ok
        if detector == "no_signal" and expected_signal and observed_signal:
            correct = _detail_ok("no_signal", exp[1], result.hypothesis_detail)
        false_positive = observed_signal and not expected_signal
        false_negative = expected_signal and not (observed_signal and family_ok and detail_ok)
        if detector == "no_signal" and expected_signal:
            false_negative = not observed_signal
        rows.append(
            {
                "scenario": scenario_id,
                "dataset_id": dataset_id,
                "detector": detector,
                "expected_signal": expected_signal,
                "observed_signal": observed_signal,
                "status": result.status,
                "hypothesis_family": result.hypothesis_family,
                "hypothesis_detail": result.hypothesis_detail,
                "effect_size": result.effect_size,
                "p_value": result.p_value,
                "adjusted_p_value": result.adjusted_p_value,
                "correct": correct,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "true_negative": (not expected_signal) and (not observed_signal),
                "sample_size": result.sample_size,
                "data_gaps": list(result.data_gaps),
                "confidence": result.confidence,
                "method": result.method,
            }
        )
    return rows


def evaluate_all_synthetic(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    summary_path = root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    rows: list[dict[str, Any]] = []
    for item in payload["scenarios"]:
        ds = item["dataset_id"]
        sid = item["scenario_id"]
        rows.extend(evaluate_dataset(ds, sid, agent_root / ds, cfg))
    tp = sum(1 for r in rows if r["correct"])
    fp = sum(1 for r in rows if r["false_positive"])
    fn = sum(1 for r in rows if r["false_negative"])
    tn = sum(1 for r in rows if r["true_negative"])
    return {
        "rows": rows,
        "counts": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
        "n_rows": len(rows),
    }


def write_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_synthetic(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "detectors_phase3.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
