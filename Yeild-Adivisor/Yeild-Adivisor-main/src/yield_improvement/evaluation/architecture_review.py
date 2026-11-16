"""Architecture review orchestration. Hidden GT is joined only after OOF predictions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.runner import run_detectors_on_dir
from yield_improvement.evaluation.ml import EXPECTED, LIMIT_PHRASES
from yield_improvement.hypotheses.composer import compose
from yield_improvement.ml.benchmark import (
    ACTIVE_FEATURE_CONTRACT,
    CORE_MODELS,
    probe_extra_models,
    run_lolo_models,
)
from yield_improvement.ml.config import load_ml_config
from yield_improvement.ml.contracts import DISCLAIMER, MLPrediction
from yield_improvement.ml.dataset import load_ml_dataset
from yield_improvement.ml.evidence import build_ml_evidence
from yield_improvement.ml.features import fit_feature_builder
from yield_improvement.ml.pipeline import artifact_dir
from yield_improvement.pipeline import run_fixture_dir
from yield_improvement.utils.paths import phase2_agent_visible_dir, repo_root

REVIEW_VERSION = "yi_arch_review_v1"
ACTIVE_FILES = ("model.pkl", "metadata.json", "feature_list.json", "metrics.json")
REQUIRED_JSON_KEYS = (
    "review_version",
    "active_model",
    "models_evaluated",
    "unavailable_models",
    "dataset_summary",
    "feature_contract",
    "fold_assignments",
    "raw_metrics",
    "calibrated_metrics",
    "per_lot_metrics",
    "lot_stability",
    "paired_fold_comparisons",
    "calibration_analysis",
    "feature_importance_stability",
    "scenario_results",
    "limitations",
    "decision",
    "decision_rationale",
)


def hash_active_artifact() -> dict[str, str]:
    folder = artifact_dir(load_ml_config())
    out = {}
    for name in ACTIVE_FILES:
        path = folder / name
        if not path.is_file():
            raise FileNotFoundError(f"Active artifact missing: {path}")
        out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def assert_active_unchanged(before: dict[str, str], after: dict[str, str]) -> None:
    if before != after:
        raise RuntimeError(f"Active artifact mutated during architecture review: {before} vs {after}")


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        val = obj.item()
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
        return val
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def _s02_dir() -> Path:
    payload = json.loads((repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    for item in payload["scenarios"]:
        if item["scenario_id"] == "S02":
            return phase2_agent_visible_dir() / item["dataset_id"]
    raise FileNotFoundError("S02 missing")


def _predictions(frame, proba, cfg) -> list[MLPrediction]:
    rows = []
    recs = frame.to_dict(orient="records")
    for i, rec in enumerate(recs):
        p = float(np.clip(proba[i], 0.0, 1.0))
        rows.append(
            MLPrediction(
                die_id=str(rec["die_id"]),
                lot_id=str(rec["lot_id"]),
                wafer_id=str(rec["wafer_id"]),
                predicted_probability=p,
                raw_probability=p,
                predicted_class=1 if p >= 0.5 else 0,
                model_version=cfg.ml_version,
                feature_set_version=cfg.feature_set_version,
                calibration_version=cfg.calibration_version,
            )
        )
    return rows


def _policy_pack(hyps, ml_evidence, blob: str) -> dict[str, Any]:
    return {
        "n_hypotheses": len(hyps.hypotheses),
        "no_confident_hypothesis": hyps.no_confident_hypothesis,
        "has_edge": any(h.family == "SPATIAL" and h.detail == "EDGE" for h in hyps.hypotheses),
        "has_drift": any(h.family == "PROCESS" and h.detail == "DRIFT" for h in hyps.hypotheses),
        "combined_root_cause": any("EDGE_AND_DRIFT" in h.hypothesis_id for h in hyps.hypotheses),
        "no_limit_change": all(p not in blob for p in LIMIT_PHRASES),
        "n_ml_evidence": len(ml_evidence),
        "ml_attached": any(any(isinstance(e, dict) and e.get("source") == "ml" for e in h.evidence) for h in hyps.hypotheses),
        "production_authorized": False,
        "production_action": "FORBIDDEN",
    }


def _association_ranks(feat, oof) -> list[dict[str, Any]]:
    ranks = []
    oof = np.asarray(oof, dtype=float)
    for col in feat.columns:
        series = feat[col]
        num = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        if np.isfinite(num).sum() < 20:
            encoded = series.astype("category").cat.codes.to_numpy(dtype=float)
            encoded = encoded.astype(float)
            encoded[series.astype("category").cat.codes.to_numpy() < 0] = np.nan
            num = encoded
        mask = np.isfinite(num) & np.isfinite(oof)
        if mask.sum() < 20:
            continue
        if np.unique(num[mask]).size < 2:
            continue
        corr = float(np.corrcoef(num[mask], oof[mask])[0, 1])
        ranks.append(
            {
                "feature": col,
                "importance": abs(corr) if np.isfinite(corr) else 0.0,
                "kind": "predictive_abs_correlation_with_oof",
                "note": "Predictive association only. Not a causal effect.",
            }
        )
    ranks.sort(key=lambda r: -r["importance"])
    return ranks


def _scenario_model_row(name: str, data, bench: dict[str, Any], detectors, fpy_value, config: AppConfig, cfg, scenario_id: str) -> dict[str, Any]:
    oof = bench["_oof"][name]["raw"]
    preds = _predictions(data.frame, oof, cfg)
    builder = fit_feature_builder(data.frame, data.y)
    feat = builder.transform(data.frame)
    y = data.y.to_numpy()
    ranks = _association_ranks(feat, oof)
    evidence = build_ml_evidence(frame=feat, y=y, predictions=preds, importances=ranks, cfg=cfg.evidence, model_version=cfg.ml_version)
    hyps = compose(detectors, config, fpy=fpy_value, analysis_id=data.analysis_id, ml_evidence=list(evidence))
    blob = json.dumps([e.model_dump(mode="json") for e in evidence]).lower()
    identities = {(e.family, e.detail) for e in evidence}
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
    return {
        "raw_metrics": bench["models"][name]["raw"],
        "calibrated_metrics": bench["models"][name]["calibrated"],
        "detection_status": status,
        "model_detected_signal": detected,
        "top_features": [r["feature"] for r in ranks[:8]],
        **_policy_pack(hyps, evidence, blob),
        "feature_names": bench["models"][name]["feature_names"],
        "n_features": bench["models"][name]["n_features"],
    }


def evaluate_scenario_models(
    agent_dir: Path,
    scenario_id: str,
    model_names: list[str],
    config: AppConfig,
    *,
    bench: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_ml_config()
    data = load_ml_dataset(agent_dir, config=config)
    if bench is None:
        bench = run_lolo_models(data, model_names=model_names, cfg=cfg, with_importance=False)
    detectors = run_detectors_on_dir(agent_dir, config=config)
    fpy_value = run_fixture_dir(agent_dir, config=config).fpy if (agent_dir / "die_attempts.csv").is_file() else None
    per_model = {name: _scenario_model_row(name, data, bench, detectors, fpy_value, config, cfg, scenario_id) for name in model_names}
    return {
        "scenario": scenario_id,
        "dataset_id": agent_dir.name,
        "n_samples": bench["n_samples"],
        "n_lots": bench["n_lots"],
        "held_out_lots": [row["held_out_lot"] for row in bench["fold_assignments"]],
        "same_folds_all_models": True,
        "models": per_model,
        "s16_no_forced": all(per_model[n]["no_confident_hypothesis"] for n in model_names) if scenario_id == "S16" else None,
        "s15_separate": (
            all(per_model[n]["has_edge"] and per_model[n]["has_drift"] and not per_model[n]["combined_root_cause"] for n in model_names)
            if scenario_id == "S15"
            else None
        ),
        "s09_no_limit": all(per_model[n]["no_limit_change"] for n in model_names) if scenario_id == "S09" else None,
        "s01_no_forced_hypothesis": all(per_model[n]["no_confident_hypothesis"] for n in model_names) if scenario_id == "S01" else None,
        "s12_s13_no_id_features": (
            all("lot_id" not in per_model[n]["feature_names"] and "wafer_id" not in per_model[n]["feature_names"] for n in model_names)
            if scenario_id in {"S12", "S13"}
            else None
        ),
    }


def decide(detailed: dict[str, Any], unavailable: dict[str, Any], close: float = 0.02) -> dict[str, Any]:
    models = detailed["models"]
    n_lots = int(detailed["n_lots"])
    logistic = models["logistic"]["raw"]
    ranked = sorted(
        models,
        key=lambda n: (
            -(models[n]["raw"].get("pr_auc") or -1.0),
            models[n]["raw"].get("brier") or 1.0,
        ),
    )
    best = ranked[0]
    best_pr = models[best]["raw"].get("pr_auc") or -1.0
    log_pr = logistic.get("pr_auc") or -1.0
    log_cap10 = logistic.get("failure_capture_at_top_10_percent") or 0.0
    log_cap20 = logistic.get("failure_capture_at_top_20_percent") or 0.0
    log_sd = models["logistic"]["lot_stability_raw"]["pr_auc"]["std"]
    rationale = [
        f"n_lots = {n_lots}. Conclusions are preliminary; do not overclaim significance.",
        "Comparisons use raw LOLO OOF. Calibrated metrics are a separate probability-quality dimension and are never mixed with another model's raw scores.",
        "Selection is not based on a single metric (ROC-AUC, F1, recall, or PR-AUC alone).",
    ]
    if unavailable:
        rationale.append("Libraries that were unavailable were not scored. Status is NOT_EVALUATED, not inferior.")
    capture_floor_10 = log_cap10 - 0.03
    capture_floor_20 = log_cap20 - 0.03

    def _capture_ok(name: str) -> bool:
        cap10 = models[name]["raw"].get("failure_capture_at_top_10_percent") or 0.0
        cap20 = models[name]["raw"].get("failure_capture_at_top_20_percent") or 0.0
        return cap10 + 1e-12 >= capture_floor_10 and cap20 + 1e-12 >= capture_floor_20

    def _stable_ok(name: str) -> bool:
        sd = models[name]["lot_stability_raw"]["pr_auc"]["std"]
        return sd is None or log_sd is None or sd <= (log_sd + 0.03)

    if best == "logistic" or abs(best_pr - log_pr) <= close:
        alt = None
        for name in ranked:
            if name == "logistic":
                continue
            dpr = (models[name]["raw"].get("pr_auc") or -1.0) - log_pr
            if dpr > close and _capture_ok(name) and _stable_ok(name):
                alt = name
                break
        if alt is None:
            return {
                "decision": "KEEP_LOGISTIC",
                "recommended_architecture": "logistic",
                "confidence": "medium",
                "n_lots": n_lots,
                "close_tolerance": close,
                "rationale": rationale
                + [
                    "No alternative beat logistic PR-AUC by more than close_tolerance while also matching diagnostic capture and lot stability.",
                    f"Logistic PR-AUC={log_pr:.3f}, top-10 capture={log_cap10:.3f}, top-20 capture={log_cap20:.3f}.",
                    "When differences are within close tolerance, prefer the simpler, better-calibrated, easier-to-explain architecture.",
                ],
            }
        return {
            "decision": "CONSIDER_ALTERNATIVE",
            "recommended_architecture": alt,
            "confidence": "medium",
            "n_lots": n_lots,
            "close_tolerance": close,
            "rationale": rationale + [f"{alt} exceeded logistic on multiple dimensions including PR-AUC beyond {close}."],
        }
    cap10 = models[best]["raw"].get("failure_capture_at_top_10_percent") or 0.0
    cap20 = models[best]["raw"].get("failure_capture_at_top_20_percent") or 0.0
    sd = models[best]["lot_stability_raw"]["pr_auc"]["std"]
    if not _capture_ok(best):
        return {
            "decision": "KEEP_LOGISTIC",
            "recommended_architecture": "logistic",
            "confidence": "medium",
            "n_lots": n_lots,
            "close_tolerance": close,
            "rationale": rationale
            + [
                f"{best} has higher PR-AUC ({best_pr:.3f} vs {log_pr:.3f}) but worse diagnostic capture "
                f"(top-10 {cap10:.3f} vs {log_cap10:.3f}; top-20 {cap20:.3f} vs {log_cap20:.3f}). "
                "Capture is required for this diagnostic agent and is not recovered yield.",
            ],
        }
    if sd is not None and log_sd is not None and sd > log_sd + 0.05:
        return {
            "decision": "INCONCLUSIVE",
            "recommended_architecture": "logistic",
            "confidence": "low",
            "n_lots": n_lots,
            "close_tolerance": close,
            "rationale": rationale
            + [f"{best} has higher mean PR-AUC but worse lot SD ({sd:.3f} vs {log_sd:.3f}). n_lots={n_lots}."],
        }
    return {
        "decision": "CONSIDER_ALTERNATIVE",
        "recommended_architecture": best,
        "confidence": "medium",
        "n_lots": n_lots,
        "close_tolerance": close,
        "rationale": rationale
        + [f"{best} PR-AUC {best_pr:.3f} vs logistic {log_pr:.3f} with capture and lot stability not materially worse."],
    }


def run_architecture_review(config: AppConfig | None = None) -> dict[str, Any]:
    app = config or load_config()
    cfg = load_ml_config()
    before = hash_active_artifact()
    extra, unavailable_raw = probe_extra_models()
    unavailable = {
        name: {"status": "NOT_EVALUATED", "reason": "unavailable_due_to_environment", "detail": reason}
        for name, reason in unavailable_raw.items()
    }
    model_names = list(CORE_MODELS) + extra
    print(f"[architecture_review] models={model_names} unavailable={list(unavailable)}", flush=True)
    s02_dir = _s02_dir()
    s02 = load_ml_dataset(s02_dir, config=app)
    print("[architecture_review] S02 detailed LOLO + permutation importance", flush=True)
    detailed = run_lolo_models(s02, model_names=model_names, cfg=cfg, with_importance=True)
    payload = json.loads((repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    agent_root = phase2_agent_visible_dir()
    scenarios = []
    for item in payload["scenarios"]:
        sid = item["scenario_id"]
        agent_dir = agent_root / item["dataset_id"]
        print(f"[architecture_review] scenario {sid}", flush=True)
        if sid == "S02":
            scenarios.append(evaluate_scenario_models(agent_dir, sid, model_names, app, bench=detailed))
        else:
            scenarios.append(evaluate_scenario_models(agent_dir, sid, model_names, app))
    decision = decide(detailed, unavailable, close=cfg.selection.close_tolerance)
    after = hash_active_artifact()
    assert_active_unchanged(before, after)
    by = {r["scenario"]: r for r in scenarios}
    review = {
        "review_version": REVIEW_VERSION,
        "active_model": {"name": "logistic", "artifact": "yi_ml_v1", "architecture": "Logistic Regression", "status": "ACTIVE_UNCHANGED"},
        "models_evaluated": list(model_names),
        "unavailable_models": unavailable,
        "dataset_summary": {
            "analysis_id": s02.analysis_id,
            "scenario": "S02",
            "n_samples": detailed["n_samples"],
            "n_positives": detailed["n_positives"],
            "positive_rate": detailed["positive_rate"],
            "n_lots": detailed["n_lots"],
            "split_strategy": detailed["split_strategy"],
            "same_folds_all_models": True,
            "feature_count": 16,
            "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        },
        "feature_contract": list(ACTIVE_FEATURE_CONTRACT),
        "fold_assignments": detailed["fold_assignments"],
        "raw_metrics": {n: detailed["models"][n]["raw"] for n in detailed["models"]},
        "calibrated_metrics": {n: detailed["models"][n]["calibrated"] for n in detailed["models"]},
        "per_lot_metrics": {
            n: {"raw": detailed["models"][n]["per_lot_raw"], "calibrated": detailed["models"][n]["per_lot_calibrated"]}
            for n in detailed["models"]
        },
        "lot_stability": {n: detailed["models"][n]["lot_stability_raw"] for n in detailed["models"]},
        "paired_fold_comparisons": detailed["paired_fold_comparisons"],
        "calibration_analysis": {
            n: {
                "raw_brier": detailed["models"][n]["raw"].get("brier"),
                "calibrated_brier": detailed["models"][n]["calibrated"].get("brier"),
                "raw_log_loss": detailed["models"][n]["raw"].get("log_loss"),
                "calibrated_log_loss": detailed["models"][n]["calibrated"].get("log_loss"),
                "raw_ece": detailed["models"][n]["raw"].get("ece"),
                "calibrated_ece": detailed["models"][n]["calibrated"].get("ece"),
                "raw_calibration_error": detailed["models"][n]["raw"].get("calibration_error"),
                "calibrated_calibration_error": detailed["models"][n]["calibrated"].get("calibration_error"),
                "raw_reliability_bins": detailed["models"][n]["raw"].get("reliability_bins"),
                "calibrated_reliability_bins": detailed["models"][n]["calibrated"].get("reliability_bins"),
                "note": "Calibration quality is a separate dimension from discrimination. Nested isotonic is fit on outer-train in-sample scores only.",
            }
            for n in detailed["models"]
        },
        "operational": {
            n: {
                "train_seconds": detailed["models"][n]["train_seconds"],
                "inference_seconds": detailed["models"][n]["inference_seconds"],
                "complexity": detailed["models"][n]["complexity"],
            }
            for n in detailed["models"]
        },
        "feature_importance_stability": {n: detailed["models"][n]["feature_importance_stability"] for n in detailed["models"]},
        "scenario_results": scenarios,
        "scenario_policy": {
            "s01_no_forced": by["S01"]["s01_no_forced_hypothesis"],
            "s16_no_forced": by["S16"]["s16_no_forced"],
            "s15_separate": by["S15"]["s15_separate"],
            "s09_no_limit": by["S09"]["s09_no_limit"],
            "s11_no_sequence_features": all(
                "sequence" not in f.lower() and "later_test" not in f.lower() and "test_index" not in f.lower()
                for n, block in by["S11"]["models"].items()
                for f in block["feature_names"]
            ),
            "s12_no_lot_id_feature": by["S12"]["s12_s13_no_id_features"],
            "s13_no_wafer_id_feature": by["S13"]["s12_s13_no_id_features"],
        },
        "active_artifact_sha256_before": before,
        "active_artifact_sha256_after": after,
        "production_action": "FORBIDDEN",
        "production_authorized": False,
        "safety_eligible_production_count": 0,
        "safety_eligible_production_rate": 0.0,
        "retrained_active": False,
        "invoked_agents": [],
        "limitations": [
            DISCLAIMER,
            f"n_lots={detailed['n_lots']}. Paired differences are preliminary.",
            "CatBoost was not evaluated if unavailable; that is NOT_EVALUATED, not an inferiority claim.",
            "Permutation importance is predictive association only and is not a causal effect or root cause.",
            "Top-k capture is diagnostic concentration, not recovered yield.",
            "Calibrated metrics are never compared against another model's raw metrics.",
            "S12/S13 weakness, if present, is a feature-contract limitation (no lot_id/wafer_id memorization), not an architecture defect to 'fix'.",
            "S11 cannot use later-test or sequence indices; censoring limitations are preserved.",
        ],
        "decision": decision["decision"],
        "decision_rationale": decision,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return _json_safe(review)


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _md_table(review: dict[str, Any]) -> str:
    lines = [
        "| Model | ROC-AUC | PR-AUC | F1 | Recall | Brier | ECE | Top-10 | Top-20 | PR-AUC lot mean (SD) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, raw in review["raw_metrics"].items():
        stab = review["lot_stability"][name]["pr_auc"]
        lines.append(
            f"| {name} | {_fmt(raw.get('roc_auc'))} | {_fmt(raw.get('pr_auc'))} | {_fmt(raw.get('f1'))} | "
            f"{_fmt(raw.get('recall'))} | {_fmt(raw.get('brier'))} | {_fmt(raw.get('ece'))} | "
            f"{_fmt(raw.get('failure_capture_at_top_10_percent'))} | {_fmt(raw.get('failure_capture_at_top_20_percent'))} | "
            f"{_fmt(stab.get('mean'))} ({_fmt(stab.get('std'))}) |"
        )
    return "\n".join(lines)


def _importance_summary(review: dict[str, Any]) -> str:
    blocks = []
    for name, rows in review["feature_importance_stability"].items():
        if not rows:
            blocks.append(f"- `{name}`: permutation importance not computed or unstable (no fold-level ranks).")
            continue
        top = rows[:5]
        rank_std = [r.get("rank_std") or 0.0 for r in rows]
        unstable = sum(1 for s in rank_std if s >= 2.0)
        lines = ", ".join(
            f"{r['feature']} (rank mean {_fmt(r['rank_mean'])}, top-5 folds {r['n_folds_top5']}/{r['n_folds']})" for r in top
        )
        note = "Importance ranks move across lots." if unstable >= 3 else "Leading predictive associations are relatively consistent across lots."
        blocks.append(f"- `{name}`: {lines}. {note} Predictive association only, not causal.")
    return "\n".join(blocks)


def _paired_summary(review: dict[str, Any]) -> str:
    wanted = {("logistic", "random_forest", "pr_auc"), ("logistic", "hist_gbm", "pr_auc")}
    extra = [n for n in review["models_evaluated"] if n not in CORE_MODELS]
    for name in extra:
        wanted.add(("logistic", name, "pr_auc"))
    lines = []
    for row in review["paired_fold_comparisons"]:
        key = (row["model_a"], row["model_b"], row["metric"])
        if key not in wanted and (row["model_b"], row["model_a"], row["metric"]) not in {(a, b, m) for a, b, m in wanted}:
            if row["metric"] != "pr_auc" or row["model_a"] != "logistic":
                continue
        if row["metric"] != "pr_auc":
            continue
        lines.append(
            f"- {row['model_a']} − {row['model_b']} PR-AUC: mean {_fmt(row['mean_paired_difference_a_minus_b'])} "
            f"(SD {_fmt(row['std_paired_difference'])}); "
            f"{row['n_folds_a_better']} folds {row['model_a']} better, {row['n_folds_b_better']} folds {row['model_b']} better "
            f"(n_folds={row['n_folds']})."
        )
    return "\n".join(lines) if lines else "- No paired PR-AUC rows."


def render_markdown(review: dict[str, Any]) -> str:
    d = review["decision_rationale"]
    unav = review["unavailable_models"] or {}
    reasons = "\n".join(f"- {x}" for x in d["rationale"])
    unav_txt = json.dumps(unav, indent=2) if unav else "none"
    return f"""# Model architecture review (evaluation only)

**Active model unchanged:** Logistic Regression / `yi_ml_v1`.

**Decision:** `{review["decision"]}`

**Recommended architecture (not activated):** `{d["recommended_architecture"]}`

This document does not replace the active artifact, does not retrain `yi_ml_v1`, and does not authorize production.

## Dataset

- samples: {review["dataset_summary"]["n_samples"]}
- positives: {review["dataset_summary"]["n_positives"]} (rate {_fmt(review["dataset_summary"]["positive_rate"])})
- lots: {review["dataset_summary"]["n_lots"]} (leave-one-lot-out; **n_lots = {review["dataset_summary"]["n_lots"]}**)
- features: 16 (Phase 7 contract; no lot/wafer/die IDs, no hidden labels)
- same LOLO folds for every model: `{review["dataset_summary"]["same_folds_all_models"]}`

## Models

Evaluated: {", ".join(review["models_evaluated"])}

Unavailable / NOT_EVALUATED:

```json
{unav_txt}
```

Do not read unavailability as inferiority.

## Raw LOLO OOF (S02)

These columns are **raw**. Do not compare them to another model's calibrated scores.

{_md_table(review)}

Calibrated Brier / log loss / ECE live in `evaluation/results/model_architecture_review.json` under `calibration_analysis`. Calibration quality is a separate dimension from discrimination.

## Lot stability and paired fold differences

Stability uses per-held-out-lot metrics (mean, SD, min, max). A single pooled metric is not the stability conclusion.

{_paired_summary(review)}

## Feature importance stability

Permutation importance is computed independently on each LOLO held-out lot. This is predictive association only — not a root cause and not causal evidence.

{_importance_summary(review)}

## Decision rationale

{reasons}

n_lots = {d.get("n_lots", review["dataset_summary"]["n_lots"])}. Do not overclaim significance.

## Scenario policies

- S01 no invented hypothesis: {review["scenario_policy"]["s01_no_forced"]}
- S09 no limit verbs: {review["scenario_policy"]["s09_no_limit"]}
- S11 no sequence / later-test features: {review["scenario_policy"]["s11_no_sequence_features"]}
- S12 no lot_id feature: {review["scenario_policy"]["s12_no_lot_id_feature"]}
- S13 no wafer_id feature: {review["scenario_policy"]["s13_no_wafer_id_feature"]}
- S15 EDGE and DRIFT remain separate (no EDGE_AND_DRIFT): {review["scenario_policy"]["s15_separate"]}
- S16 no forced hypothesis: {review["scenario_policy"]["s16_no_forced"]}

S12/S13 remain weak if they are weak: lot/wafer identity is not a legal feature. That is a feature-contract limitation, not something to fix by memorization.

## Safety

- production_authorized: false
- production_action: FORBIDDEN
- safety_eligible_production_count: 0
- safety_eligible_production_rate: 0.0
- active artifact SHA-256 unchanged: {review["active_artifact_sha256_before"] == review["active_artifact_sha256_after"]}
- invoked_agents: []
- retrained_active: false

## Limitations

{chr(10).join("- " + x for x in review["limitations"])}
"""


def write_architecture_review(config: AppConfig | None = None) -> tuple[Path, Path]:
    review = run_architecture_review(config=config)
    json_path = repo_root() / "evaluation" / "results" / "model_architecture_review.json"
    md_path = repo_root() / "docs" / "MODEL_ARCHITECTURE_REVIEW.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(review), encoding="utf-8")
    return json_path, md_path
