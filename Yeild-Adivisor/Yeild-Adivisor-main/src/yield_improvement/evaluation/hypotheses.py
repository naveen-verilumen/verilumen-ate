"""Join composed hypotheses to hidden ground truth. Composer never imports this module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.hypotheses.composer import compose_from_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

# Expected PRIMARY identities. Evaluation only. Composer does not read this table.
EXPECTED_HYPOTHESES: dict[str, set[tuple[str, str]]] = {
    "S01": set(),
    "S02": {("SPATIAL", "EDGE")},
    "S03": {("SPATIAL", "CENTER")},
    "S04": {("SPATIAL", "RING")},
    "S05": {("EQUIPMENT", "DEGRADATION")},
    "S06": {("PROCESS", "DRIFT")},
    "S07": {("ENVIRONMENT", "TEMPERATURE")},
    "S08": {("PARAMETRIC", "SHIFT")},
    "S09": {("TEST", "LIMIT_SENSITIVITY")},
    "S10": {("CONTACT", "PROBE")},
    "S11": set(),  # sequence often censored; do not require a hypothesis
    "S12": {("PROCESS", "LOT_VARIATION")},
    "S13": {("PROCESS", "WAFER_VARIATION")},
    "S14": {("CORRELATED", "FAILURES")},
    "S15": {("SPATIAL", "EDGE"), ("PROCESS", "DRIFT")},
    "S16": set(),
}

OPTIONAL_IF_INSUFFICIENT = {"S10", "S11"}


def evaluate_dataset(
    dataset_id: str,
    scenario_id: str,
    agent_dir: Path,
    config: AppConfig,
) -> dict[str, Any]:
    bundle = compose_from_dir(agent_dir, config=config)
    expected = EXPECTED_HYPOTHESES.get(scenario_id, set())
    observed = {(h.family, h.detail) for h in bundle.hypotheses}
    present = sorted(f"{f}.{d}" for f, d in (expected & observed))
    missing = sorted(f"{f}.{d}" for f, d in (expected - observed))
    extra = sorted(f"{f}.{d}" for f, d in (observed - expected))
    dual_ok = True
    if scenario_id == "S15":
        dual_ok = ("SPATIAL", "EDGE") in observed and ("PROCESS", "DRIFT") in observed
        collapsed = any("EDGE" in h.detail and "DRIFT" in h.detail for h in bundle.hypotheses)
        dual_ok = dual_ok and not collapsed
    seq_insufficient = bundle.detector_summary.get("sequence") == "INSUFFICIENT_DATA"
    if scenario_id in OPTIONAL_IF_INSUFFICIENT and missing:
        # Do not fail S10/S11 when the relevant detector lacked observable data.
        still_missing = []
        for item in missing:
            family, _, detail = item.partition(".")
            related = {
                "CONTACT.PROBE": "contact",
                "TEST.SEQUENCE": "sequence",
            }.get(item)
            status = bundle.detector_summary.get(related or "", "")
            if status == "INSUFFICIENT_DATA":
                continue
            still_missing.append(item)
        missing = still_missing
    no_signal_ok = True
    if scenario_id in {"S01", "S16"}:
        no_signal_ok = bundle.no_confident_hypothesis is True
    ranking = [
        {
            "hypothesis_id": h.hypothesis_id,
            "family": h.family,
            "detail": h.detail,
            "rank": h.rank,
            "evidence_score": h.evidence_score,
            "evidence_tier": h.evidence_tier,
            "association_class": h.association_class,
            "not_a_root_cause": h.not_a_root_cause,
            "status": h.status,
        }
        for h in bundle.hypotheses
    ]
    return {
        "scenario": scenario_id,
        "dataset_id": dataset_id,
        "analysis_id": bundle.analysis_id,
        "no_confident_hypothesis": bundle.no_confident_hypothesis,
        "n_hypotheses": len(bundle.hypotheses),
        "expected_present": present,
        "missing_hypothesis": missing,
        "extra_hypothesis": extra,
        "false_hypothesis_count": len(extra),
        "dual_cause_ok": dual_ok,
        "no_signal_ok": no_signal_ok,
        "sequence_insufficient": seq_insufficient,
        "expected_recovered": len(missing) == 0,
        "ranking": ranking,
        "limitations": list(bundle.limitations),
        "all_not_a_root_cause": all(h.not_a_root_cause is True for h in bundle.hypotheses),
    }


def evaluate_all_hypotheses(config: AppConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    root = repo_root()
    summary_path = root / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    rows: list[dict[str, Any]] = []
    for item in payload["scenarios"]:
        rows.append(evaluate_dataset(item["dataset_id"], item["scenario_id"], agent_root / item["dataset_id"], cfg))
    recovered = sum(1 for r in rows if r["expected_recovered"])
    dual = next((r for r in rows if r["scenario"] == "S15"), None)
    s01 = next((r for r in rows if r["scenario"] == "S01"), None)
    s16 = next((r for r in rows if r["scenario"] == "S16"), None)
    return {
        "rows": rows,
        "n_scenarios": len(rows),
        "n_expected_recovered": recovered,
        "s15_dual_cause_ok": bool(dual and dual["dual_cause_ok"]),
        "s01_no_confident": bool(s01 and s01["no_signal_ok"]),
        "s16_no_confident": bool(s16 and s16["no_signal_ok"]),
        "all_not_a_root_cause": all(r["all_not_a_root_cause"] for r in rows),
    }


def write_hypothesis_evaluation(path: Path | None = None, config: AppConfig | None = None) -> Path:
    result = evaluate_all_hypotheses(config=config)
    out = path or (repo_root() / "evaluation" / "results" / "hypotheses_phase4.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
