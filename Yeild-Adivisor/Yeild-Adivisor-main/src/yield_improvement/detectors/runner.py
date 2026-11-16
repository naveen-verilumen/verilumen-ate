"""Run all Phase 3 detectors and apply Benjamini-Hochberg FDR. No ranking."""

from __future__ import annotations

from pathlib import Path

from yield_improvement.config.loader import AppConfig, load_config
from yield_improvement.detectors.common import cal
from yield_improvement.detectors.contact import detect_contact
from yield_improvement.detectors.contract import DetectorBundle, DetectorResult
from yield_improvement.detectors.correlation import detect_correlation
from yield_improvement.detectors.equipment import detect_equipment
from yield_improvement.detectors.lot import detect_lot
from yield_improvement.detectors.near_limit import detect_near_limit
from yield_improvement.detectors.no_signal import detect_no_signal
from yield_improvement.detectors.parametric import detect_parametric
from yield_improvement.detectors.population import build_context
from yield_improvement.detectors.sequence import detect_sequence
from yield_improvement.detectors.spatial import detect_spatial
from yield_improvement.detectors.stats import benjamini_hochberg
from yield_improvement.detectors.temperature import detect_temperature
from yield_improvement.detectors.temporal import detect_temporal
from yield_improvement.detectors.wafer import detect_wafer
from yield_improvement.ingestion.loader import (
    load_die_attempts,
    load_parametric_measurements,
    load_test_results,
)
from yield_improvement.models.canonical import DieAttempt, ParametricMeasurement, TestResult


def _effect_ok(hyp, min_effect: float, ks_d_min: float) -> bool:
    metric = hyp.effect_size_metric or "fail_rate_difference"
    value = hyp.effect_size
    if value is None:
        return False
    if metric == "ks_d":
        return value >= ks_d_min
    if metric == "jaccard":
        return value >= 0.15
    if metric == "mann_kendall_tau":
        return abs(value) >= 0.5
    if metric == "near_limit_mass":
        return value >= 0.20
    return abs(value) >= min_effect


def _apply_fdr(
    results: dict[str, DetectorResult],
    q: float,
    min_effect: float,
    ks_d_min: float,
) -> dict[str, DetectorResult]:
    keys: list[tuple[str, int | None]] = []
    pvals: list[float | None] = []
    for name, res in results.items():
        if not res.hypotheses:
            if res.p_value is not None:
                keys.append((name, None))
                pvals.append(res.p_value)
            continue
        for i, hyp in enumerate(res.hypotheses):
            keys.append((name, i))
            pvals.append(hyp.p_value)
    adjusted = benjamini_hochberg(pvals, q)
    by_det: dict[str, list[float]] = {}
    hyp_adj: dict[tuple[str, int], float | None] = {}
    for (name, idx), adj in zip(keys, adjusted):
        if adj is not None:
            by_det.setdefault(name, []).append(adj)
        if idx is not None:
            hyp_adj[(name, idx)] = adj
    out: dict[str, DetectorResult] = {}
    for name, res in results.items():
        adj_win = min(by_det[name]) if by_det.get(name) else None
        status = res.status
        family = res.hypothesis_family
        detail = res.hypothesis_detail
        effect = res.effect_size
        p_raw = res.p_value
        conf = res.confidence
        affected = res.affected_population
        baseline = res.baseline_population
        if res.hypotheses:
            viable = []
            for i, hyp in enumerate(res.hypotheses):
                adj = hyp_adj.get((name, i))
                if adj is not None and adj <= q and _effect_ok(hyp, min_effect, ks_d_min):
                    viable.append((hyp, adj))
            if res.status == "SIGNAL":
                has_p = any(h.p_value is not None for h in res.hypotheses)
                if viable:
                    winner, adj_win = max(viable, key=lambda t: abs(t[0].effect_size or 0.0))
                    family = winner.family
                    detail = winner.detail
                    effect = winner.effect_size
                    p_raw = winner.p_value
                    affected = {
                        "label": winner.label,
                        "n": winner.n_affected,
                        "rate": winner.rate_affected,
                    }
                    baseline = {"n": winner.n_baseline, "rate": winner.rate_baseline}
                elif has_p:
                    status = "NO_SIGNAL"
                    conf = "LOW"
                    family = None
                    detail = None
                # else: SIGNAL from a non-p evidence path (e.g. near-limit mass); keep
            elif by_det.get(name):
                adj_win = min(by_det[name])
        elif status == "SIGNAL" and adj_win is not None and adj_win > q:
            status = "NO_SIGNAL"
            conf = "LOW"
            family = None
            detail = None
        out[name] = res.model_copy(
            update={
                "status": status,
                "hypothesis_family": family,
                "hypothesis_detail": detail,
                "effect_size": effect,
                "p_value": p_raw,
                "adjusted_p_value": adj_win,
                "correction_method": "benjamini_hochberg",
                "confidence": conf,
                "affected_population": affected,
                "baseline_population": baseline,
                "not_a_root_cause": True,
            }
        )
    return out


def run_detectors(
    attempts: list[DieAttempt],
    config: AppConfig,
    test_results: list[TestResult] | None = None,
    parametric: list[ParametricMeasurement] | None = None,
) -> DetectorBundle:
    ctx = build_context(attempts, config, test_results=test_results, parametric=parametric)
    raw = {
        "spatial": detect_spatial(ctx),
        "equipment": detect_equipment(ctx),
        "temporal": detect_temporal(ctx),
        "temperature": detect_temperature(ctx),
        "parametric": detect_parametric(ctx),
        "near_limit": detect_near_limit(ctx),
        "sequence": detect_sequence(ctx),
        "contact": detect_contact(ctx),
        "lot": detect_lot(ctx),
        "wafer": detect_wafer(ctx),
        "correlation": detect_correlation(ctx),
    }
    q = cal(config, "fdr_q")
    alpha = cal(config, "significance_level_alpha")
    min_effect = cal(config, "min_effect_size_fpy_delta")
    ks_d_min = cal(config, "ks_d_min")
    adjusted = _apply_fdr(raw, q, min_effect, ks_d_min)
    adjusted["no_signal"] = detect_no_signal(ctx, adjusted)
    gaps = sorted({g for r in adjusted.values() for g in r.data_gaps})
    return DetectorBundle(
        n_eligible=ctx.n_eligible,
        correction_method="benjamini_hochberg",
        fdr_q=q,
        alpha=alpha,
        min_effect_size=min_effect,
        results=adjusted,
        data_gaps=gaps,
    )


def run_detectors_on_dir(dataset_dir: str | Path, config: AppConfig | None = None) -> DetectorBundle:
    """Load agent-visible files only. Does not open hidden evaluation labels."""
    folder = Path(dataset_dir)
    cfg = config or load_config()
    da = folder / "die_attempts.csv"
    loaded = load_die_attempts(da, cfg)
    tests = []
    tr = folder / "test_results.csv"
    if tr.is_file():
        tests = load_test_results(tr, cfg).test_results
    parametric = []
    pm = folder / "parametric_measurements.csv"
    if pm.is_file():
        parametric = load_parametric_measurements(pm, cfg).parametric
    return run_detectors(loaded.attempts, cfg, test_results=tests, parametric=parametric)
