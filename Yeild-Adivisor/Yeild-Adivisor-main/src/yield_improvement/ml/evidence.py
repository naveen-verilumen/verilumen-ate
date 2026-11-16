"""Convert ML predictions and importances into SECONDARY_SUPPORT evidence. Not a root cause."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from yield_improvement.hypotheses.contract import Hypothesis, HypothesisBundle
from yield_improvement.hypotheses.explain import render_explanation
from yield_improvement.hypotheses.identity import hypothesis_id
from yield_improvement.ml.config import EvidenceCfg
from yield_improvement.ml.contracts import DISCLAIMER, MLEvidence, MLPrediction

FEATURE_TO_FAMILY: dict[str, tuple[str, str | None]] = {
    "die_x": ("SPATIAL", None),
    "die_y": ("SPATIAL", None),
    "normalized_x": ("SPATIAL", None),
    "normalized_y": ("SPATIAL", None),
    "radial_distance": ("SPATIAL", None),
    "edge_distance": ("SPATIAL", "EDGE"),
    "spatial_region": ("SPATIAL", None),
    "tester_id": ("EQUIPMENT", "DEGRADATION"),
    "tester_fail_rate": ("EQUIPMENT", "DEGRADATION"),
    "probe_card_id": ("CONTACT", "PROBE"),
    "probe_fail_rate": ("CONTACT", "PROBE"),
    "prober_id": ("EQUIPMENT", "DEGRADATION"),
    "temperature_c": ("ENVIRONMENT", "TEMPERATURE"),
    "timestamp_epoch": ("PROCESS", "DRIFT"),
    "IR_DROP_MV": ("PARAMETRIC", "SHIFT"),
    "THERMAL_C": ("PARAMETRIC", "SHIFT"),
    "SETUP_SLACK_PS": ("PARAMETRIC", "SHIFT"),
    "HOLD_SLACK_PS": ("PARAMETRIC", "SHIFT"),
    "TEST_TIME_MS": ("PARAMETRIC", "SHIFT"),
}

_ML_LIMITS = [
    DISCLAIMER,
    "ML evidence is SECONDARY_SUPPORT and is not an independent confirmation of a statistical detector that uses the same features.",
    "ML does not recommend or modify test limits, recipes, equipment, or ATE.",
]


def _spatial_detail(frame: pd.DataFrame, high_idx: np.ndarray) -> str | None:
    if "radial_distance" not in frame.columns:
        return None
    r = pd.to_numeric(frame["radial_distance"], errors="coerce")
    if r.notna().sum() < 20:
        return None
    high = r.to_numpy()[high_idx]
    rest_mask = np.ones(len(r), dtype=bool)
    rest_mask[high_idx] = False
    rest = r.to_numpy()[rest_mask]
    high = high[~np.isnan(high)]
    rest = rest[~np.isnan(rest)]
    if high.size < 8 or rest.size < 8:
        return None
    if float(np.mean(high)) > float(np.mean(rest)):
        return "EDGE"
    if float(np.mean(high)) < float(np.mean(rest)):
        return "CENTER"
    return None


def build_ml_evidence(
    *,
    frame: pd.DataFrame,
    y: np.ndarray,
    predictions: list[MLPrediction],
    importances: list[dict],
    cfg: EvidenceCfg,
    model_version: str,
) -> list[MLEvidence]:
    if not predictions:
        return []
    proba = np.array([p.predicted_probability for p in predictions], dtype=float)
    k = max(1, int(np.ceil(cfg.top_risk_fraction * len(proba))))
    high_idx = np.argsort(-proba)[:k]
    ranked = [row for row in importances if row.get("importance", 0) > 0]
    ranked = ranked[: cfg.min_importance_rank]
    family_hits: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in ranked:
        mapped = FEATURE_TO_FAMILY.get(str(row["feature"]))
        if mapped is None:
            continue
        family, detail = mapped
        if family == "SPATIAL" and detail is None:
            detail = _spatial_detail(frame, high_idx) or "EDGE"
        if family == "TEST":
            continue
        if detail is None:
            continue
        family_hits[(family, detail)].append(row)
    # Near-limit is never emitted as a limit-change recommendation. Parametric SHIFT only.
    evidence: list[MLEvidence] = []
    n = len(predictions)
    coverage_xy = float(pd.to_numeric(frame.get("die_x"), errors="coerce").notna().mean()) if "die_x" in frame else 0.0
    for (family, detail), rows in sorted(family_hits.items()):
        high_y = y[high_idx]
        rest_mask = np.ones(len(y), dtype=bool)
        rest_mask[high_idx] = False
        rest_y = y[rest_mask]
        high_rate = float(high_y.mean()) if high_y.size else 0.0
        rest_rate = float(rest_y.mean()) if rest_y.size else 0.0
        delta = high_rate - rest_rate
        if delta < cfg.min_rate_delta:
            continue
        strength = min(1.0, max(0.0, delta / 0.25) * 0.7 + min(1.0, sum(r["importance"] for r in rows)) * 0.3)
        cov = coverage_xy if family == "SPATIAL" else 1.0
        hid = hypothesis_id(family, detail)
        evidence.append(
            MLEvidence(
                hypothesis_id=hid,
                family=family,
                detail=detail,
                evidence_type="ML_PREDICTIVE_ASSOCIATION",
                evidence_role="SECONDARY_SUPPORT",
                affected_population={
                    "definition": f"top_{int(cfg.top_risk_fraction * 100)}_percent_predicted_risk",
                    "n": int(k),
                    "observed_fail_rate": high_rate,
                },
                prediction_summary={
                    "baseline_fail_rate": rest_rate,
                    "high_risk_fail_rate": high_rate,
                    "rate_delta": round(delta, 4),
                    "n_scored": n,
                },
                feature_importance=rows,
                predictive_strength=round(float(strength), 4),
                coverage=round(float(cov), 4),
                independence=False,
                model_version=model_version,
                limitations=list(_ML_LIMITS),
                not_a_root_cause=True,
            )
        )
    return evidence


DEGRADED_HEALTH = frozenset({"DEGRADED", "NEEDS_RETRAINING", "INSUFFICIENT_DATA"})


def attach_ml_evidence(
    bundle: HypothesisBundle,
    evidence: list[MLEvidence],
    model_health_status: str | None = None,
    ml_support_status: str | None = None,
) -> HypothesisBundle:
    """Attach ML packets onto matching statistical hypotheses. Does not re-rank or rescore.

    NEEDS_MORE_DATA means the finding must not be presented as ML-supported.
    """
    if ml_support_status == "NEEDS_MORE_DATA":
        limitations = list(bundle.limitations) + [
            "ML support is NEEDS_MORE_DATA. This investigation finding is not ML-supported.",
            "ML does not recommend or modify test limits, recipes, equipment, or ATE.",
            DISCLAIMER,
        ]
        summary = dict(bundle.detector_summary)
        summary["ml"] = "NEEDS_MORE_DATA"
        summary["ml_supported"] = "false"
        if model_health_status:
            summary["ml_health"] = model_health_status
        return bundle.model_copy(
            update={
                "limitations": list(dict.fromkeys(limitations)),
                "detector_summary": summary,
            }
        )
    if not evidence:
        limitations = list(bundle.limitations) + [
            "No ML predictive evidence met the documented concentration threshold.",
            DISCLAIMER,
        ]
        if model_health_status in DEGRADED_HEALTH:
            limitations.append(
                f"ML evidence is flagged because model_health_status={model_health_status}. "
                "Statistical evidence remains independently usable."
            )
        summary = dict(bundle.detector_summary)
        summary["ml"] = "ML_FLAGGED" if model_health_status in DEGRADED_HEALTH else "OBSERVATION_ONLY"
        if model_health_status:
            summary["ml_health"] = model_health_status
        return bundle.model_copy(update={"limitations": list(dict.fromkeys(limitations)), "detector_summary": summary})
    by_id = {(e.family, e.detail): e for e in evidence}
    updated: list[Hypothesis] = []
    matched = set()
    for hyp in bundle.hypotheses:
        item = by_id.get((hyp.family, hyp.detail))
        if item is None:
            updated.append(hyp)
            continue
        matched.add((hyp.family, hyp.detail))
        extra = {
            "source": "ml",
            "evidence_type": item.evidence_type,
            "role": item.evidence_role,
            "predictive_strength": item.predictive_strength,
            "note": "ML predictive evidence supports this hypothesis. This is not a confirmed root cause.",
            "prediction_summary": item.prediction_summary,
            "feature_importance": item.feature_importance,
            "model_health_status": model_health_status or "UNKNOWN",
            "trust": "REDUCED" if model_health_status in DEGRADED_HEALTH else "SECONDARY",
        }
        if model_health_status in DEGRADED_HEALTH:
            extra["evidence_limitation"] = (
                f"ML evidence is flagged because model_health_status={model_health_status}. "
                "Statistical evidence remains independently usable."
            )
            extra["note"] = (
                "ML predictive evidence is flagged due to model health. "
                "This is not a confirmed root cause and must not be treated at healthy-model trust."
            )
        limits = list(hyp.limitations) + list(item.limitations)
        if model_health_status in DEGRADED_HEALTH:
            limits.append(str(extra["evidence_limitation"]))
        new_hyp = hyp.model_copy(
            update={
                "evidence": list(hyp.evidence) + [extra],
                "limitations": list(dict.fromkeys(limits)),
            }
        )
        new_hyp = new_hyp.model_copy(update={"explanation": render_explanation(new_hyp)})
        updated.append(new_hyp)
    unmatched = [e for e in evidence if (e.family, e.detail) not in matched]
    limitations = list(bundle.limitations)
    limitations.append(DISCLAIMER)
    limitations.append(
        "ML evidence is not added into evidence_score. Statistical and ML scores are not summed."
    )
    if unmatched:
        names = ", ".join(f"{e.family}.{e.detail}" for e in unmatched)
        limitations.append(
            "ML produced predictive observations without a matching statistical hypothesis "
            f"({names}). These observations are not forced into a new root-cause hypothesis."
        )
    summary = dict(bundle.detector_summary)
    if model_health_status in DEGRADED_HEALTH:
        summary["ml"] = "ML_FLAGGED"
    else:
        summary["ml"] = "PREDICTIVE_SUPPORT" if matched else "OBSERVATION_ONLY"
    if model_health_status:
        summary["ml_health"] = model_health_status
    return bundle.model_copy(
        update={
            "hypotheses": updated,
            "limitations": list(dict.fromkeys(limitations)),
            "detector_summary": summary,
        }
    )
