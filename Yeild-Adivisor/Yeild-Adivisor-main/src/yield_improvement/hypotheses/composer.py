"""Compose UNCONFIRMED hypotheses from a DetectorBundle. Not a root-cause engine."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.common import cal
from yield_improvement.detectors.contract import DetectorBundle, DetectorResult, EvidenceItem
from yield_improvement.detectors.runner import run_detectors_on_dir
from yield_improvement.hypotheses.contract import (
    AssociationClass,
    Hypothesis,
    HypothesisBundle,
    StatisticalEvidence,
)
from yield_improvement.hypotheses.explain import render_explanation
from yield_improvement.hypotheses.identity import (
    CORRELATED_PARENTS,
    VALIDATION,
    hypothesis_id,
    identity_for,
    statement_for,
)
from yield_improvement.hypotheses.ranking import confidence_level, evidence_score, evidence_tier
from yield_improvement.pipeline import run_fixture_dir

# Methodological disclaimers live in limitations, not invented counter-evidence.
_DISCLAIMER_NAMES = {
    "association_is_not_causation",
    "does_not_modify_limits",
    "production_opportunity",
}


def _item_payload(item: EvidenceItem) -> dict[str, Any]:
    return {"name": item.name, "value": item.value, "note": item.note}


def _is_disclaimer(item: EvidenceItem) -> bool:
    return item.name in _DISCLAIMER_NAMES


def _independent_views(member_names: list[str]) -> bool:
    """True when two supporting detectors are not a documented parent/child pair."""
    if len(member_names) < 2:
        return False
    for i, a in enumerate(member_names):
        for b in member_names[i + 1 :]:
            a_parents = CORRELATED_PARENTS.get(a, ())
            b_parents = CORRELATED_PARENTS.get(b, ())
            if a in b_parents or b in a_parents:
                continue
            if a in CORRELATED_PARENTS and b in CORRELATED_PARENTS.get(a, ()):
                continue
            return True
    return False


def _association_class(
    member_names: list[str],
    signal_names: set[str],
    max_abs_effect: float,
    min_effect: float,
) -> AssociationClass:
    nested_of = [p for name in member_names for p in CORRELATED_PARENTS.get(name, ()) if p in signal_names]
    if nested_of:
        if max_abs_effect < 2.0 * min_effect:
            return "WEAK_ASSOCIATION"
        return "SECONDARY_ASSOCIATION"
    if max_abs_effect < 1.5 * min_effect:
        return "WEAK_ASSOCIATION"
    return "PRIMARY_EVIDENCE"


def _stat_from_result(name: str, result: DetectorResult, role: str) -> StatisticalEvidence:
    return StatisticalEvidence(
        detector=name,
        method=result.method,
        status=result.status,
        role=role,  # type: ignore[arg-type]
        sample_size=result.sample_size,
        effect_size=result.effect_size,
        effect_size_metric=result.effect_size_metric,
        p_value=result.p_value,
        adjusted_p_value=result.adjusted_p_value,
        correction_method=result.correction_method,
        affected_population=result.affected_population,
        baseline_population=result.baseline_population,
        scope=result.hypothesis_detail,
    )


def _eligible_die_coverage(n_eligible: int, sample_size: int | None) -> dict[str, Any]:
    """Coverage of eligible dies. Detector sample_size may be a different grain (e.g. measurements)."""
    raw = n_eligible if sample_size is None else int(sample_size)
    if n_eligible <= 0:
        return {"n_eligible": n_eligible, "n_used": raw, "fraction": None}
    n_used = min(raw, n_eligible)
    return {"n_eligible": n_eligible, "n_used": n_used, "fraction": round(n_used / n_eligible, 4)}


def compose(
    bundle: DetectorBundle,
    config: AppConfig,
    *,
    fpy: float | None = None,
    analysis_id: str = "unknown",
    ml_evidence: list | None = None,
    model_health_status: str | None = None,
    ml_support_status: str | None = None,
) -> HypothesisBundle:
    """DetectorBundle → unconfirmed HypothesisBundle. Ground truth is never read."""
    results = bundle.results
    signal_pairs: list[tuple[str, DetectorResult]] = [
        (name, result)
        for name, result in results.items()
        if result.status == "SIGNAL" and name != "no_signal"
    ]
    signal_names = {name for name, _ in signal_pairs}

    groups: dict[tuple[str, str], list[tuple[str, DetectorResult]]] = defaultdict(list)
    for name, result in signal_pairs:
        ident = identity_for(name, result)
        if ident is None:
            continue
        groups[ident].append((name, result))

    min_effect = cal(config, "min_effect_size_fpy_delta")
    draft: list[Hypothesis] = []

    for (family, detail), members in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        member_names = [n for n, _ in members]
        max_abs_effect = max(abs(r.effect_size or 0.0) for _, r in members)
        assoc = _association_class(member_names, signal_names, max_abs_effect, min_effect)
        children = [
            child
            for child, parents in CORRELATED_PARENTS.items()
            if child in signal_names and any(p in member_names for p in parents)
        ]
        supporting = list(dict.fromkeys([*member_names, *children]))
        independent = _independent_views(supporting) and assoc == "PRIMARY_EVIDENCE"

        stats: list[StatisticalEvidence] = []
        evidence_rows: list[dict[str, Any]] = []
        counter_rows: list[dict[str, Any]] = []
        limitations: list[str] = [
            "UNCONFIRMED association. not_a_root_cause is true. evidence_score is not a causal probability.",
            "evidence_score is PRELIMINARY and requires calibration on holdout scenarios.",
        ]
        gaps: list[str] = []
        for name, result in members:
            role = "PRIMARY_EVIDENCE" if assoc == "PRIMARY_EVIDENCE" else "SECONDARY_SUPPORT"
            stats.append(_stat_from_result(name, result, role))
            for item in result.evidence:
                evidence_rows.append({"detector": name, **_item_payload(item)})
            for item in result.counter_evidence:
                if _is_disclaimer(item):
                    limitations.append(f"{name}: {item.name}" + (f" — {item.note}" if item.note else ""))
                else:
                    counter_rows.append({"detector": name, **_item_payload(item)})
            gaps.extend(result.data_gaps)
            if result.sample_size is not None and result.sample_size < int(cal(config, "n_min_group_compare")):
                counter_rows.append(
                    {
                        "detector": name,
                        "name": "sample_size_below_group_minimum",
                        "value": result.sample_size,
                        "note": "Association observed on a slice below n_min_group_compare.",
                    }
                )
        for child in children:
            child_res = results[child]
            stats.append(_stat_from_result(child, child_res, "CORRELATED_SUPPORT"))
            limitations.append(
                f"Detector {child} analyzes a nested grain of {member_names}; "
                "it is correlated support, not an independent confirmation."
            )
            for item in child_res.evidence:
                evidence_rows.append({"detector": child, "role": "CORRELATED_SUPPORT", **_item_payload(item)})
            gaps.extend(child_res.data_gaps)

        if assoc in {"SECONDARY_ASSOCIATION", "WEAK_ASSOCIATION"}:
            parents = [
                p
                for name in member_names
                for p in CORRELATED_PARENTS.get(name, ())
                if p in signal_names
            ]
            counter_rows.append(
                {
                    "name": "nested_grain_of_another_signal",
                    "value": parents,
                    "note": (
                        "This association can be the nested lot/wafer/contact grain of another "
                        "signal (for example PROCESS.DRIFT or SPATIAL.EDGE). It is not independent "
                        "primary evidence and is not a root cause."
                    ),
                }
            )

        conflicting: list[str] = []
        for name, result in results.items():
            ident = identity_for(name, result) if result.status == "SIGNAL" else None
            if ident == (family, detail):
                continue
            if name in member_names or name in children:
                continue
            if result.status == "NO_SIGNAL" and name in member_names:
                conflicting.append(name)

        primary = members[0][1]
        n_cov = primary.sample_size if primary.sample_size is not None else bundle.n_eligible
        coverage = _eligible_die_coverage(bundle.n_eligible, n_cov)
        unique_gaps = list(dict.fromkeys(gaps))
        score = evidence_score(
            config=config,
            p_value=primary.p_value,
            adjusted_p_value=min(
                (r.adjusted_p_value for _, r in members if r.adjusted_p_value is not None),
                default=None,
            ),
            effect_size=max((r.effect_size for _, r in members if r.effect_size is not None), key=abs, default=None),
            effect_size_metric=primary.effect_size_metric,
            sample_size=max((r.sample_size or 0) for _, r in members) or None,
            n_gaps=len(unique_gaps),
            n_counter=len(counter_rows),
            association_class=assoc,
            independent_support=independent,
        )
        tier = evidence_tier(score, config, independent_support=independent)
        if assoc == "INSUFFICIENT_EVIDENCE":
            tier = "INSUFFICIENT_EVIDENCE"
        hid = hypothesis_id(family, detail)
        effect_sizes = [
            {
                "detector": n,
                "effect_size": r.effect_size,
                "effect_size_metric": r.effect_size_metric,
            }
            for n, r in members
        ]
        hyp = Hypothesis(
            hypothesis_id=hid,
            family=family,
            detail=detail,
            statement=statement_for(family, detail, primary.affected_population),
            status="UNCONFIRMED",
            not_a_root_cause=True,
            association_class=assoc,
            evidence_tier=tier,
            evidence_score=score,
            score_status="PRELIMINARY",
            confidence_level=confidence_level(tier, independent),  # type: ignore[arg-type]
            rank=0,
            evidence=evidence_rows,
            counter_evidence=counter_rows,
            supporting_detectors=supporting,
            conflicting_detectors=conflicting,
            competing_hypothesis_ids=[],
            statistical_evidence=stats,
            effect_sizes=effect_sizes,
            affected_population=primary.affected_population,
            data_coverage=coverage,
            data_gaps=unique_gaps,
            validation_required=list(VALIDATION.get(family, ["Confirm on independent material. Do not change production."])),
            limitations=list(dict.fromkeys(limitations)),
            explanation="",
        )
        hyp = hyp.model_copy(update={"explanation": render_explanation(hyp)})
        draft.append(hyp)

    ranked = sorted(
        draft,
        key=lambda h: (-h.evidence_score, h.family, h.detail, h.hypothesis_id),
    )
    ids = [h.hypothesis_id for h in ranked]
    finalized: list[Hypothesis] = []
    for i, hyp in enumerate(ranked, start=1):
        others = [hid for hid in ids if hid != hyp.hypothesis_id]
        finalized.append(
            hyp.model_copy(
                update={
                    "rank": i,
                    "competing_hypothesis_ids": others,
                    "explanation": render_explanation(
                        hyp.model_copy(update={"rank": i, "competing_hypothesis_ids": others})
                    ),
                }
            )
        )

    confident = [
        h
        for h in finalized
        if h.association_class == "PRIMARY_EVIDENCE"
        and h.evidence_tier in {"STRONG_EVIDENCE", "MODERATE_EVIDENCE"}
    ]
    no_confident = len(confident) == 0

    limitations = [
        "HypothesisBundle contains UNCONFIRMED associations only. No confirmed root cause.",
        "evidence_score is PRELIMINARY, not a probability of root cause, and is not calibrated for production.",
        "Competing hypotheses are preserved; dual-cause scenarios are not collapsed.",
        "Correlated detectors (lot/wafer nested in drift/spatial; contact nested in equipment) are not independent confirmation.",
    ]
    seq = results.get("sequence")
    if seq is not None and seq.status == "INSUFFICIENT_DATA":
        limitations.append(
            "Later-test observations are censored by stop-on-fail behavior. "
            "TEST.SEQUENCE is not composed from invented order or imputed later-test outcomes."
        )
    if results.get("no_signal") and results["no_signal"].status == "SIGNAL" and not signal_names:
        limitations.append("No systematic detector produced a SIGNAL. NO_CONFIDENT_HYPOTHESIS.")

    detector_summary = {name: res.status for name, res in results.items()}
    gaps = list(bundle.data_gaps)
    composed = HypothesisBundle(
        analysis_id=analysis_id,
        current_fpy=fpy,
        n_eligible=bundle.n_eligible,
        no_confident_hypothesis=no_confident,
        hypotheses=finalized,
        data_gaps=gaps,
        detector_summary=detector_summary,
        limitations=limitations,
        score_status="PRELIMINARY",
    )
    if ml_evidence:
        from yield_improvement.ml.evidence import attach_ml_evidence

        composed = attach_ml_evidence(
            composed,
            ml_evidence,
            model_health_status=model_health_status,
            ml_support_status=ml_support_status,
        )
    elif ml_support_status == "NEEDS_MORE_DATA":
        from yield_improvement.ml.evidence import attach_ml_evidence

        composed = attach_ml_evidence(
            composed,
            [],
            model_health_status=model_health_status,
            ml_support_status=ml_support_status,
        )
    return composed


def compose_from_dir(dataset_dir: str | Path, config: AppConfig | None = None) -> HypothesisBundle:
    """Load agent-visible files, run detectors, then compose. Does not open hidden labels."""
    folder = Path(dataset_dir)
    cfg = config or load_config()
    detectors = run_detectors_on_dir(folder, config=cfg)
    fpy_value = None
    attempts = folder / "die_attempts.csv"
    if attempts.is_file():
        fpy_result = run_fixture_dir(folder, config=cfg)
        fpy_value = fpy_result.fpy
    return compose(detectors, cfg, fpy=fpy_value, analysis_id=folder.name)
