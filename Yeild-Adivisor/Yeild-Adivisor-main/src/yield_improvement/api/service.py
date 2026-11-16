"""Assemble dashboard payloads by copying existing outputs. No new formulas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yield_improvement.config.test_catalog import public_test_catalog
from yield_improvement.monitoring.contracts import DEGRADED_EVIDENCE_STATES, DISCLAIMER as HEALTH_DISCLAIMER
from yield_improvement.ml.contracts import DISCLAIMER as ML_DISCLAIMER
from yield_improvement.reporting.contract import (
    DISCLAIMER,
    NO_ACTIONABLE_NOTICE,
    SAFETY_STATEMENT,
    EngineeringReport,
    ReportHypothesis,
    ReportInvestigationItem,
    ReportOpportunity,
    ReportValidation,
)
from yield_improvement.reporting.renderer import load_report_json
from yield_improvement.utils.paths import active_synthetic_dir, fixtures_fpy_dir, phase2_agent_visible_dir, phase2_monitoring_dir, repo_root

DEGRADED_HEALTH = frozenset(DEGRADED_EVIDENCE_STATES)
ACTIVE_DATASET_ID = "yi_synthetic_v2"


INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def display_lot_name(lot_id: str) -> str:
    text = str(lot_id).strip()
    if len(text) >= 2 and text[0] in {"L", "l"} and text[1:].isdigit():
        return f"LOT {int(text[1:]):03d}"
    return text


def _add_lot_token(tokens: set[str], value: object) -> None:
    if isinstance(value, list):
        for item in value:
            _add_lot_token(tokens, item)
        return
    if not isinstance(value, str) or not value.strip():
        return
    text = value.strip()
    tokens.add(text)
    if ":" in text:
        tokens.add(text.rsplit(":", 1)[-1])
    if "/" in text:
        tokens.add(text.split("/", 1)[0])


def population_lot_ids(affected: dict[str, Any] | None) -> set[str]:
    """Lot identifiers referenced by a finding's affected population."""
    tokens: set[str] = set()
    if not isinstance(affected, dict):
        return tokens
    for key in ("group", "label", "lot_id", "comparison", "lots"):
        _add_lot_token(tokens, affected.get(key))
    return tokens


def _is_actionable_finding(hyp: ReportHypothesis) -> bool:
    if hyp.evidence_tier == INSUFFICIENT_EVIDENCE:
        return False
    if hyp.association_class == INSUFFICIENT_EVIDENCE:
        return False
    return True


def _applies_to_lot(hyp: ReportHypothesis, lot_id: str, *, require_explicit_lot: bool) -> bool:
    tokens = population_lot_ids(hyp.affected_population)
    if lot_id in tokens:
        return True
    if require_explicit_lot:
        return False
    return True


def overlay_lot_investigation(
    global_report: EngineeringReport,
    lot_report: EngineeringReport,
    lot_id: str,
) -> EngineeringReport:
    """Overlay lot-scoped analysis onto global report.

    Lot-scoped FPY metrics, Pareto, executive summary, evidence findings,
    and data gaps are used from lot_report. Hypotheses, opportunities, and
    investigation plan are filtered and merged for the selected lot.
    INSUFFICIENT_EVIDENCE is omitted.
    """
    scoped: list[ReportHypothesis] = []
    for hyp in lot_report.hypotheses:
        if not _is_actionable_finding(hyp):
            continue
        if hyp.family == "PROCESS" and hyp.detail == "LOT_VARIATION":
            continue
        if not _applies_to_lot(hyp, lot_id, require_explicit_lot=False):
            continue
        scoped.append(hyp)
    by_id = {hyp.hypothesis_id: hyp for hyp in scoped}

    for hyp in global_report.hypotheses:
        if not _is_actionable_finding(hyp):
            continue
        if hyp.hypothesis_id in by_id:
            continue
        if not _applies_to_lot(hyp, lot_id, require_explicit_lot=True):
            continue
        by_id[hyp.hypothesis_id] = hyp

    merged = sorted(by_id.values(), key=lambda item: (item.rank, item.hypothesis_id))
    merged = [item.model_copy(update={"rank": index}) for index, item in enumerate(merged, start=1)]
    hyp_ids = {item.hypothesis_id for item in merged}

    opportunities: list[ReportOpportunity] = []
    seen_hyps: set[str] = set()
    for source in (lot_report.opportunities, global_report.opportunities):
        for item in source:
            if item.family == "UNION":
                continue
            hid = item.hypothesis_id
            if not hid or hid not in hyp_ids or hid in seen_hyps:
                continue
            opportunities.append(item)
            seen_hyps.add(hid)

    plan: list[ReportInvestigationItem] = []
    seen_plan: set[str] = set()
    for source in (lot_report.investigation_plan, global_report.investigation_plan):
        for item in source:
            hid = item.hypothesis_id
            if hid and hid not in hyp_ids:
                continue
            key = hid or f"{item.family}.{item.detail}"
            if key in seen_plan:
                continue
            plan.append(item)
            seen_plan.add(key)

    validation: list[ReportValidation] = []
    seen_val: set[str] = set()
    for source in (lot_report.validation, global_report.validation):
        for item in source:
            hid = item.hypothesis_id
            if hid and hid not in hyp_ids:
                continue
            key = hid or item.validation_id
            if key in seen_val:
                continue
            validation.append(item)
            seen_val.add(key)

    has_limit = any(item.family == "TEST" and item.detail == "LIMIT_SENSITIVITY" for item in merged)
    near_limit = lot_report.near_limit_notice or global_report.near_limit_notice if has_limit else None
    no_actionable = len(merged) == 0
    return global_report.model_copy(
        update={
            "fpy_summary": lot_report.fpy_summary,
            "loss_summary": lot_report.loss_summary,
            "executive_summary": lot_report.executive_summary,
            "evidence_findings": lot_report.evidence_findings,
            "hypotheses": merged,
            "opportunities": opportunities,
            "investigation_plan": plan,
            "validation": validation,
            "data_gaps": lot_report.data_gaps,
            "overlap": lot_report.overlap,
            "near_limit_notice": near_limit,
            "no_actionable_recommendation": no_actionable,
            "no_actionable_notice": NO_ACTIONABLE_NOTICE if no_actionable else None,
        }
    )


def dataset_roots() -> list[Path]:
    """Lookup roots for analysis by ID. Production listing does not use this."""
    return [
        active_synthetic_dir(),
        fixtures_fpy_dir(),
        phase2_agent_visible_dir(),
        phase2_monitoring_dir(),
        repo_root() / "data" / "synthetic" / "monitoring" / "agent_visible",
        repo_root() / "reports",
    ]


def reports_dir() -> Path:
    return repo_root() / "reports"


def persisted_report_path(dataset_id: str) -> Path:
    return reports_dir() / f"{dataset_id}_engineering_report.json"


def health_report_path(dataset_id: str) -> Path:
    return repo_root() / "evaluation" / "monitoring" / f"{dataset_id}_model_health.json"


def find_dataset_dir(dataset_id: str) -> Path | None:
    if "/" in dataset_id or "\\" in dataset_id or ".." in dataset_id:
        return None
    for root in dataset_roots():
        candidate = root / dataset_id
        if (candidate / "die_attempts.csv").is_file():
            return candidate
    return None


def _read_lots(folder: Path) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    for name in ("lot_metadata.csv", "lots.csv"):
        path = folder / name
        if not path.is_file():
            continue
        import csv

        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                lot_id = (row.get("lot_id") or "").strip()
                if not lot_id or any(item["lot_id"] == lot_id for item in lots):
                    continue
                lots.append({"lot_id": lot_id, "display_name": display_lot_name(lot_id)})
        if lots:
            return lots
    attempts = folder / "die_attempts.csv"
    if attempts.is_file():
        import csv

        seen: set[str] = set()
        with attempts.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                lot_id = (row.get("lot_id") or "").strip()
                if lot_id and lot_id not in seen:
                    seen.add(lot_id)
                    lots.append({"lot_id": lot_id, "display_name": display_lot_name(lot_id)})
    return lots


def _is_active_production_folder(folder: Path) -> bool:
    if not folder.is_dir() or folder.name.startswith("ds_"):
        return False
    return (folder / "die_attempts.csv").is_file()


def list_datasets() -> list[dict[str, Any]]:
    """Production selector: current V2 dataset only. Old ds_* / ds_mon_* are excluded."""
    rows: list[dict[str, Any]] = []
    root = active_synthetic_dir()
    if not root.is_dir():
        return rows
    for folder in sorted(root.iterdir()):
        if not _is_active_production_folder(folder):
            continue
        manifest: dict[str, Any] = {}
        man_path = folder / "manifest.json"
        if man_path.is_file():
            try:
                loaded = json.loads(man_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    manifest = loaded
            except json.JSONDecodeError:
                manifest = {}
        lots = _read_lots(folder)
        rows.append(
            {
                "dataset_id": folder.name,
                "display_name": manifest.get("display_name") or "Yield Improvement V2",
                "dataset_type": manifest.get("dataset_type") or "SYNTHETIC",
                "path": str(folder),
                "has_die_attempts": True,
                "has_persisted_report": persisted_report_path(folder.name).is_file(),
                "has_health_report": health_report_path(folder.name).is_file(),
                "n_lots": manifest.get("n_lots") or len(lots),
                "n_wafers": manifest.get("n_wafers"),
                "n_dies": manifest.get("n_dies") or manifest.get("die_count"),
                "die_count": manifest.get("n_dies") or manifest.get("die_count"),
                "product_id": manifest.get("product_id"),
                "lots": lots,
            }
        )
    rows.sort(key=lambda item: item["dataset_id"])
    return rows


def load_report(dataset_id: str, *, lot_id: str | None = None) -> EngineeringReport:
    if not lot_id:
        persisted = persisted_report_path(dataset_id)
        if persisted.is_file():
            return load_report_json(persisted)
    folder = find_dataset_dir(dataset_id)
    if folder is None:
        raise FileNotFoundError(f"dataset not found: {dataset_id}")
    from yield_improvement.reporting.adapter import build_report_from_dir

    return build_report_from_dir(folder, lot_id=lot_id)


def load_registry_snapshot() -> dict[str, Any]:
    try:
        from yield_improvement.model_lifecycle.registry import default_paths, load_registry

        registry = load_registry(default_paths())
    except Exception:  # noqa: BLE001 — dashboard must still render without a registry
        return {
            "available": False,
            "active_version": None,
            "state": None,
            "architecture": None,
        }
    active = registry.get("active_version")
    model = (registry.get("models") or {}).get(active or "", {})
    return {
        "available": True,
        "active_version": active,
        "state": model.get("state"),
        "architecture": model.get("architecture"),
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "automatic_activation": False,
        "automatic_retraining": False,
    }


def _snapshot_support(metrics: dict[str, Any] | None) -> str:
    from yield_improvement.ml.reliability import NEEDS_MORE_DATA, ml_support_status

    if not isinstance(metrics, dict) or metrics.get("positive_rate") is None:
        return NEEDS_MORE_DATA
    return ml_support_status(metrics, None, float(metrics["positive_rate"]))


def load_ml_snapshot() -> dict[str, Any]:
    """Copy persisted champion metadata/metrics. Does not train or infer."""
    registry = load_registry_snapshot()
    version = registry.get("active_version") or "yi_ml_v1"
    folder = repo_root() / "artifacts" / "ml" / str(version)
    metrics_path = folder / "metrics.json"
    metadata_path = folder / "metadata.json"
    if not metrics_path.is_file() or not metadata_path.is_file():
        return {
            "available": False,
            "model_name": None,
            "model_version": version,
            "evidence_role": "SECONDARY_SUPPORT",
            "independence": False,
            "metrics": None,
            "calibration": None,
            "feature_names": [],
            "feature_importance": [],
            "disclaimer": ML_DISCLAIMER,
            "note": "Active model artifacts are not available.",
        }
    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metrics = metrics_payload.get("metrics") if isinstance(metrics_payload, dict) else None
    calibration = None
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("calibration"), dict):
        calibration = metrics_payload["calibration"]
    elif isinstance(metadata, dict) and isinstance(metadata.get("selected_metrics"), dict):
        calibration = None
    feature_importance: list[dict[str, Any]] = []
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("feature_importance"), list):
        feature_importance = list(metrics_payload["feature_importance"])
    feature_names = []
    if isinstance(metadata, dict):
        names = metadata.get("feature_names")
        if isinstance(names, list):
            feature_names = [str(item) for item in names]
    return {
        "available": True,
        "model_name": metadata.get("model_name") if isinstance(metadata, dict) else None,
        "model_version": metadata.get("model_version") if isinstance(metadata, dict) else version,
        "feature_set_version": metadata.get("feature_set_version") if isinstance(metadata, dict) else None,
        "split_strategy": metadata.get("split_strategy") if isinstance(metadata, dict) else None,
        "evidence_role": "SECONDARY_SUPPORT",
        "independence": False,
        "metrics": metrics if isinstance(metrics, dict) else None,
        "calibration": calibration,
        "feature_names": feature_names,
        "feature_importance": feature_importance,
        "disclaimer": ML_DISCLAIMER,
        "source": "artifacts",
        "ml_support_status": _snapshot_support(metrics if isinstance(metrics, dict) else None),
        "ml_supported": _snapshot_support(metrics if isinstance(metrics, dict) else None) == "RELIABLE",
    }


def _dimension_snapshot(block: Any) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None
    return {
        "dimension": block.get("dimension"),
        "status": block.get("status"),
        "availability": block.get("availability"),
        "notes": block.get("notes") or "",
    }


def load_health_snapshot(dataset_id: str) -> dict[str, Any]:
    """Copy a persisted ModelHealthReport if present. Does not run monitoring."""
    path = health_report_path(dataset_id)
    if not path.is_file():
        return {
            "available": False,
            "overall_status": None,
            "reduced_ml_evidence": False,
            "model_version": None,
            "dimensions": None,
            "recommendations": [],
            "triggers": [],
            "disclaimer": HEALTH_DISCLAIMER,
            "note": "No persisted model-health report for this dataset.",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "overall_status": None,
            "reduced_ml_evidence": False,
            "model_version": None,
            "dimensions": None,
            "recommendations": [],
            "triggers": [],
            "disclaimer": HEALTH_DISCLAIMER,
            "note": "Persisted health report is not an object.",
        }
    status = payload.get("overall_status")
    return {
        "available": True,
        "overall_status": status,
        "reduced_ml_evidence": status in DEGRADED_HEALTH,
        "model_version": payload.get("model_version") or payload.get("active_model_version"),
        "label_mode": payload.get("label_mode"),
        "dimensions": {
            "feature_drift": _dimension_snapshot(payload.get("feature_drift")),
            "prediction_drift": _dimension_snapshot(payload.get("prediction_drift")),
            "target_drift": _dimension_snapshot(payload.get("target_drift")),
            "calibration": _dimension_snapshot(payload.get("calibration")),
            "performance": _dimension_snapshot(payload.get("performance")),
            "data_quality": _dimension_snapshot(payload.get("data_quality")),
        },
        "recommendations": list(payload.get("recommendations") or []),
        "triggers": list(payload.get("triggers") or []),
        "disclaimer": payload.get("disclaimer") or HEALTH_DISCLAIMER,
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "retrained": False,
        "model_replaced": False,
    }


def get_recommendations_bundle(
    dataset_id: str,
    *,
    lot_id: str | None = None,
    global_report: EngineeringReport | None = None,
    lot_report: EngineeringReport | None = None,
) -> dict[str, Any]:
    from yield_improvement.recommendations.generator import generate_recommendations
    from yield_improvement.recommendations.ranking import rank_recommendations
    from yield_improvement.recommendations.storage import FeedbackStore

    selected = lot_id.strip() if isinstance(lot_id, str) and lot_id.strip() else None
    ml_snap = load_ml_snapshot()

    # Reuse provided global_report if valid for this dataset, else load
    if global_report is None or not isinstance(global_report, EngineeringReport) or global_report.dataset_id != dataset_id:
        global_report = load_report(dataset_id)
    global_bundle = generate_recommendations(global_report, ml_snapshot=ml_snap, dataset_id=dataset_id)

    if not selected:
        bundle = global_bundle
    else:
        # Reuse provided lot_report if valid for this dataset, else load
        if lot_report is None or not isinstance(lot_report, EngineeringReport) or lot_report.dataset_id != dataset_id:
            lot_report = load_report(dataset_id, lot_id=selected)
        lot_bundle = generate_recommendations(lot_report, ml_snapshot=ml_snap, dataset_id=dataset_id)

        combined: dict[str, Any] = {}
        # 1. Lot-specific findings from lot_report
        for r in lot_bundle.recommendations:
            combined[r.recommendation_id] = r.model_copy(
                update={"scope": "LOT_SPECIFIC", "lot_id": selected}
            )

        # 2. Findings from global report
        for r in global_bundle.recommendations:
            if r.scope == "LOT_SPECIFIC":
                # Check if this lot is explicitly named
                if r.lot_id == selected or (r.target_population and selected in r.target_population):
                    if r.recommendation_id not in combined:
                        combined[r.recommendation_id] = r.model_copy(
                            update={"scope": "LOT_SPECIFIC", "lot_id": selected}
                        )
            else:
                # GLOBAL finding: preserve if not already covered by lot-specific finding
                if r.recommendation_id not in combined:
                    combined[r.recommendation_id] = r

        ranked = rank_recommendations(list(combined.values()))
        lot_has_specific = any(r.scope == "LOT_SPECIFIC" for r in ranked)
        lot_note = None
        if not lot_has_specific:
            lot_note = (
                f"No separate lot-specific anomalies were detected for {display_lot_name(selected)} "
                "(observed failure rate is below baseline). Retaining applicable product-wide global investigations."
            )

        bundle = global_bundle.model_copy(
            update={
                "selected_lot_id": selected,
                "lot_note": lot_note,
                "recommendation_count": len(ranked),
                "recommendations": ranked,
            }
        )

    # Overlay current feedback statuses
    store = FeedbackStore()
    updated_recs = []
    for rec in bundle.recommendations:
        status = store.get_current_status(dataset_id, rec.recommendation_id)
        if status != rec.status:
            rec = rec.model_copy(update={"status": status})
        updated_recs.append(rec)

    bundle = bundle.model_copy(update={"recommendations": updated_recs})
    return bundle.model_dump(mode="json")


def get_parametric_analysis(dataset_id: str, *, lot_id: str | None = None) -> dict[str, Any]:
    from yield_improvement.config.loader import load_config
    from yield_improvement.ingestion.loader import load_die_attempts, load_parametric_measurements
    from yield_improvement.parametric_analysis import extract_first_pass_parametric_data, run_parametric_analysis

    folder = find_dataset_dir(dataset_id)
    if folder is None:
        raise FileNotFoundError(f"Dataset '{dataset_id}' not found.")

    cfg = load_config()
    attempts_path = folder / "die_attempts.csv"
    param_path = folder / "parametric_measurements.csv"

    if not attempts_path.exists() or not param_path.exists():
        raise FileNotFoundError(f"Parametric files missing in dataset '{dataset_id}'.")

    all_attempts = load_die_attempts(attempts_path, cfg).attempts
    all_param = load_parametric_measurements(param_path, cfg).parametric

    selected = lot_id.strip() if isinstance(lot_id, str) and lot_id.strip() else None
    if not selected:
        extraction = extract_first_pass_parametric_data(all_attempts, all_param)
        report = run_parametric_analysis(extraction, dataset_id)
        return report.model_dump(mode="json")

    # Global extraction provides established candidate boundaries
    global_extraction = extract_first_pass_parametric_data(all_attempts, all_param)
    global_report = run_parametric_analysis(global_extraction, dataset_id)

    # Lot-scoped extraction provides lot-specific passing and failing distributions
    lot_attempts = [a for a in all_attempts if a.lot_id == selected]
    lot_attempt_ids = {a.attempt_id for a in lot_attempts}
    lot_param = [p for p in all_param if p.attempt_id in lot_attempt_ids]
    lot_extraction = extract_first_pass_parametric_data(lot_attempts, lot_param)
    lot_report = run_parametric_analysis(lot_extraction, dataset_id)

    # Use lot-scoped distributions, while preserving established candidate boundaries from global
    global_by_param = {r.parameter_name: r for r in global_report.results}
    scoped_results = []
    for r in lot_report.results:
        g_res = global_by_param.get(r.parameter_name)
        if g_res and g_res.candidate_threshold:
            r = r.model_copy(
                update={
                    "candidate_threshold": g_res.candidate_threshold,
                    "threshold_status": g_res.threshold_status,
                }
            )
        scoped_results.append(r)

    combined_report = lot_report.model_copy(update={"results": scoped_results})
    return combined_report.model_dump(mode="json")



def assemble_dashboard(dataset_id: str, *, lot_id: str | None = None) -> dict[str, Any]:
    selected = lot_id.strip() if isinstance(lot_id, str) and lot_id.strip() else None
    folder = find_dataset_dir(dataset_id)
    lots = _read_lots(folder) if folder is not None else []

    if not selected:
        global_report = load_report(dataset_id)
        lot_report = None
        report = global_report
    else:
        if folder is not None:
            from yield_improvement.config.loader import load_config
            from yield_improvement.reporting.adapter import build_report_from_data, load_canonical_data

            cfg = load_config()
            attempts, tests, parametric, cfg = load_canonical_data(folder, cfg)
            global_report = build_report_from_data(
                folder.name, attempts, tests, parametric, cfg, lot_id=None
            )
            lot_report = build_report_from_data(
                folder.name, attempts, tests, parametric, cfg, lot_id=selected
            )
        else:
            global_report = load_report(dataset_id)
            lot_report = load_report(dataset_id, lot_id=selected)
        report = overlay_lot_investigation(global_report, lot_report, selected)

    payload = report.to_public_dict()
    ml = load_ml_snapshot()
    health = load_health_snapshot(dataset_id)
    registry = load_registry_snapshot()
    recommendations_bundle = get_recommendations_bundle(
        dataset_id,
        lot_id=selected,
        global_report=global_report,
        lot_report=lot_report if selected else None,
    )
    return {
        "dataset_id": report.dataset_id,
        "selected_lot_id": selected,
        "selected_lot_display": display_lot_name(selected) if selected else None,
        "lots": lots,
        "generated_at": report.generated_at,
        "report": payload,
        "test_catalog": public_test_catalog(),
        "ml": ml,
        "health": health,
        "registry": registry,
        "recommendations": recommendations_bundle,
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "safety_eligible_production_count": 0,
        "safety_eligible_production_rate": 0.0,
        "invoked_agents": [],
        "safety_statement": SAFETY_STATEMENT,
        "disclaimer": DISCLAIMER,
    }

