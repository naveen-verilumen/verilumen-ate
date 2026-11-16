"""CLI: Phase 1 FPY analyze, synthetic generate, detectors, hypothesis compose."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from yield_improvement.pipeline import run_fixture_dir, run_pipeline
from yield_improvement.utils.errors import YieldImprovementError
from yield_improvement.utils.paths import fixtures_fpy_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yield_improvement",
        description="Phase 1 FPY engine — advisory diagnosis foundation. No ATE writes.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Fixture directory (contains die_attempts.csv) or die_attempts CSV/Parquet",
    )
    parser.add_argument("--die-attempts", dest="die_attempts", help="die_attempts file")
    parser.add_argument("--test-results", dest="test_results", help="optional test_results file")
    parser.add_argument("--config-dir", dest="config_dir", help="directory of YAML configs")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _generate_main(argv: list[str]) -> int:
    from yield_improvement.synthetic.generator import generate_core_scenarios, generate_dataset
    from yield_improvement.synthetic.scenarios import CORE_SCENARIOS

    parser = argparse.ArgumentParser(
        prog="yield_improvement generate",
        description="Synthetic yield datasets with hidden ground truth. Advisory data only.",
    )
    parser.add_argument("--scenario", action="append", dest="scenarios", help="Scenario id (repeatable)")
    parser.add_argument("--all-core", action="store_true", help="Generate S01–S16")
    parser.add_argument("--v2", action="store_true", help="Generate Yield Improvement synthetic V2 (5 lots × 5 wafers × 100 dies)")
    parser.add_argument("--monitoring", action="store_true", help="Generate M01–M10 monitoring currents (does not modify S01–S16)")
    parser.add_argument("--profile", help="small | medium | large")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--agent-root", help="Agent-visible output directory")
    parser.add_argument("--gt-root", help="Hidden ground-truth output directory")
    args = parser.parse_args(argv)
    if args.v2:
        from yield_improvement.synthetic.v2_generator import generate_v2

        summary = generate_v2(write=True, seed=args.seed)
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        return 0
    if args.monitoring:
        from yield_improvement.synthetic.monitoring_scenarios import generate_monitoring_scenarios

        rows = generate_monitoring_scenarios(seed=args.seed or 7)
        print(json.dumps({"generated_monitoring": rows}, indent=2, default=str))
        return 0
    scenario_ids = list(CORE_SCENARIOS) if args.all_core else (args.scenarios or [])
    if not scenario_ids:
        parser.error("pass --v2, --all-core, --scenario, or --monitoring")
    agent_root = Path(args.agent_root) if args.agent_root else None
    gt_root = Path(args.gt_root) if args.gt_root else None
    summaries = []
    if args.all_core and agent_root is None and gt_root is None:
        bundles = generate_core_scenarios(seed=args.seed, profile_name=args.profile, write=True)
    else:
        bundles = [
            generate_dataset(
                sid,
                seed=args.seed,
                profile_name=args.profile,
                write=True,
                agent_root=agent_root,
                gt_root=gt_root,
            )
            for sid in scenario_ids
        ]
    for bundle in bundles:
        summaries.append(
            {
                "dataset_id": bundle.dataset_id,
                "scenario_id": bundle.scenario_id,
                "die_count": bundle.agent_manifest["die_count"],
                "attempt_count": bundle.agent_manifest["attempt_count"],
                "first_pass_fpy": bundle.agent_manifest["first_pass_fpy"],
                "validation": bundle.validation_report["status"],
                "agent_dir": str(bundle.agent_dir) if bundle.agent_dir else None,
            }
        )
    print(json.dumps({"generated": summaries}, indent=2, sort_keys=True))
    return 0 if all(s["validation"] == "PASSED" for s in summaries) else 1


def _detect_main(argv: list[str]) -> int:
    from yield_improvement.detectors.runner import run_detectors_on_dir

    parser = argparse.ArgumentParser(
        prog="yield_improvement detect",
        description="Statistical detectors. Evidence only — not a confirmed root cause.",
    )
    parser.add_argument("dataset_dir", help="Agent-visible dataset directory")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    from yield_improvement.config.loader import load_config

    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    bundle = run_detectors_on_dir(args.dataset_dir, config=cfg)
    print(json.dumps(bundle.to_public_dict(), indent=2, sort_keys=True))
    return 0


def _hypothesize_main(argv: list[str]) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.hypotheses.composer import compose_from_dir

    parser = argparse.ArgumentParser(
        prog="yield_improvement hypothesize",
        description="Compose UNCONFIRMED hypotheses from detectors. Not a root cause.",
    )
    parser.add_argument("dataset_dir", help="Agent-visible dataset directory")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    bundle = compose_from_dir(args.dataset_dir, config=cfg)
    print(json.dumps(bundle.to_public_dict(), indent=2, sort_keys=True))
    return 0


def _opportunity_main(argv: list[str]) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.opportunity.engine import estimate_from_dir

    parser = argparse.ArgumentParser(
        prog="yield_improvement opportunity",
        description="Yield opportunity estimates. Not a predicted FPY gain. Production eligibility is 0.",
    )
    parser.add_argument("dataset_dir", help="Agent-visible dataset directory")
    parser.add_argument("--config-dir", dest="config_dir")
    parser.add_argument(
        "--attribution",
        choices=["PRIMARY_FAILURE", "ANY_FAIL"],
        default="PRIMARY_FAILURE",
        help="Attribution mode. Default PRIMARY_FAILURE. Modes are not mixed silently.",
    )
    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    bundle = estimate_from_dir(args.dataset_dir, config=cfg, attribution_mode=args.attribution)
    print(json.dumps(bundle.to_public_dict(), indent=2, sort_keys=True))
    return 0


def _validate_main(argv: list[str]) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.validation.validator import validate_from_dir

    parser = argparse.ArgumentParser(
        prog="yield_improvement validate",
        description="Safety and validation layer. Advisory investigation only. Production is forbidden.",
    )
    parser.add_argument("dataset_dir", help="Agent-visible dataset directory")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    bundle = validate_from_dir(args.dataset_dir, config=cfg)
    print(json.dumps(bundle.to_public_dict(), indent=2, sort_keys=True))
    return 0


def _report_main(argv: list[str]) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.reporting.adapter import build_report_from_dir
    from yield_improvement.reporting.renderer import write_reports
    from yield_improvement.utils.paths import repo_root

    parser = argparse.ArgumentParser(
        prog="yield_improvement report",
        description="Engineering report from Phase 1–6 results. Advisory only. Production is forbidden.",
    )
    parser.add_argument("dataset_dir", help="Agent-visible dataset directory")
    parser.add_argument("--config-dir", dest="config_dir")
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        help="Directory for JSON and Markdown (default: <repo>/reports)",
    )
    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    report = build_report_from_dir(args.dataset_dir, config=cfg)
    out = Path(args.out_dir) if args.out_dir else (repo_root() / "reports")
    json_path, md_path = write_reports(report, out)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "report_id": report.report_id}, indent=2))
    return 0


def _dashboard_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="yield_improvement dashboard",
        description="Streamlit dashboard for an EngineeringReport. Widgets do not recalculate analysis.",
    )
    parser.add_argument("--report", help="Path to generated engineering report JSON")
    parser.add_argument("--dataset-dir", help="Agent-visible directory (builds report, then displays)")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    if not args.report and not args.dataset_dir:
        parser.error("pass --report or --dataset-dir")
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("Streamlit is not installed. pip install streamlit")
        return 1
    app = Path(__file__).resolve().parent / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--"]
    if args.report:
        cmd.extend(["--report", args.report])
    if args.dataset_dir:
        cmd.extend(["--dataset-dir", args.dataset_dir])
    if args.config_dir:
        cmd.extend(["--config-dir", args.config_dir])
    import subprocess

    return int(subprocess.call(cmd))


def _ml_main(argv: list[str]) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.ml.pipeline import predict_dir, run_ml, run_ml_and_compose

    parser = argparse.ArgumentParser(
        prog="yield_improvement ml",
        description="First-pass-failure ML. Predictive evidence only. Production remains forbidden.",
    )
    parser.add_argument("action", choices=["train", "predict", "evaluate", "run", "explain-data"])
    parser.add_argument("dataset_dir")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    if args.action == "explain-data":
        from yield_improvement.ml.data_explainer import explain_dataset, render_text, write_audit
        from yield_improvement.utils.paths import repo_root

        payload = explain_dataset(args.dataset_dir)
        out = repo_root() / "evaluation" / "results" / "ml_data_split_audit.json"
        write_audit(payload, out)
        print(render_text(payload))
        print(json.dumps({"audit_json": str(out), "leakage_audit": payload["leakage_audit"], "production_authorized": False}, indent=2))
        return 0
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    if args.action == "train":
        result = run_ml(args.dataset_dir, config=cfg, persist=True)
        print(json.dumps({"model": result.model_name, "metrics": result.metrics.model_dump(), "n_evidence": len(result.evidence)}, indent=2))
        return 0
    if args.action == "predict":
        rows = predict_dir(args.dataset_dir, config=cfg)
        print(json.dumps([r.model_dump(mode="json") for r in rows[:50]], indent=2))
        print(json.dumps({"n_predictions": len(rows), "shown": min(50, len(rows))}))
        return 0
    if args.action == "evaluate":
        from yield_improvement.evaluation.ml import evaluate_dataset_ml
        from yield_improvement.utils.paths import repo_root

        summary = json.loads((repo_root() / "evaluation" / "ground_truth" / "synthetic" / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
        scenario = next((s["scenario_id"] for s in summary["scenarios"] if s["dataset_id"] == Path(args.dataset_dir).name), "UNKNOWN")
        payload = evaluate_dataset_ml(Path(args.dataset_dir).name, scenario, Path(args.dataset_dir), cfg)
        print(json.dumps(payload, indent=2, default=str))
        return 0
    ml_result, hyps = run_ml_and_compose(args.dataset_dir, config=cfg, persist=True)
    print(
        json.dumps(
            {
                "model": ml_result.model_name,
                "metrics": ml_result.metrics.model_dump(),
                "n_ml_evidence": len(ml_result.evidence),
                "n_hypotheses": len(hyps.hypotheses),
                "no_confident_hypothesis": hyps.no_confident_hypothesis,
                "ml_reached_hypotheses": any(
                    any(isinstance(e, dict) and e.get("source") == "ml" for e in h.evidence) for h in hyps.hypotheses
                ),
                "production_authorized": False,
            },
            indent=2,
        )
    )
    return 0


def _monitor_main(argv: list[str], write: bool = True) -> int:
    from yield_improvement.config.loader import load_config
    from yield_improvement.monitoring.monitor import run_monitor
    from yield_improvement.monitoring.report import write_health_outputs

    parser = argparse.ArgumentParser(
        prog="yield_improvement monitor",
        description="Advisory model health on new lots. Never retrains. Production remains forbidden.",
    )
    parser.add_argument("current_dataset")
    parser.add_argument("--reference", required=True, help="Frozen reference population directory")
    parser.add_argument("--config-dir", dest="config_dir")
    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config_dir) if args.config_dir else None)
    report = run_monitor(args.current_dataset, args.reference, config=cfg, overwrite_reference=False)
    paths = write_health_outputs(report) if write else (None, None)
    print(
        json.dumps(
            {
                "overall_status": report.overall_status,
                "label_mode": report.label_mode,
                "recommendations": list(report.recommendations),
                "production_authorized": False,
                "retrained": False,
                "json": str(paths[0]) if paths[0] else None,
                "markdown": str(paths[1]) if paths[1] else None,
            },
            indent=2,
        )
    )
    return 0


def _retrain_main(argv: list[str]) -> int:
    from yield_improvement.model_lifecycle.commands import compare_candidate, evaluate_version, prepare_candidate, train_candidate
    from yield_improvement.model_lifecycle.states import LifecycleError

    parser = argparse.ArgumentParser(
        prog="yield_improvement retrain",
        description="Manual candidate retraining. Never overwrites yi_ml_v1. Never activates.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("dataset_dir")
    p_train = sub.add_parser("train")
    p_train.add_argument("candidate_version")
    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("candidate_version")
    p_eval.add_argument("--dataset-dir", dest="dataset_dir")
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--candidate", required=True)
    p_cmp.add_argument("--champion", default="yi_ml_v1")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            payload = prepare_candidate(args.dataset_dir)
        elif args.action == "train":
            payload = train_candidate(args.candidate_version)
        elif args.action == "evaluate":
            payload = evaluate_version(args.candidate_version, dataset_dir=args.dataset_dir)
        else:
            payload = compare_candidate(args.candidate, args.champion)
    except LifecycleError as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)], "production_authorized": False}, indent=2))
        return 1
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _model_main(argv: list[str]) -> int:
    from yield_improvement.model_lifecycle.commands import (
        activate_candidate,
        approve_candidate,
        inspect_model,
        list_models,
        rollback_to,
        validate_candidate,
        verify_registry,
    )
    from yield_improvement.model_lifecycle.states import LifecycleError

    parser = argparse.ArgumentParser(
        prog="yield_improvement model",
        description="Model registry. Human approval required. Activation is a separate command.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    p_ins = sub.add_parser("inspect")
    p_ins.add_argument("--version", required=True)
    sub.add_parser("verify")
    p_val = sub.add_parser("validate")
    p_val.add_argument("--candidate", required=True)
    p_ap = sub.add_parser("approve")
    p_ap.add_argument("--candidate", required=True)
    p_ap.add_argument("--approved-by", required=True)
    p_act = sub.add_parser("activate")
    p_act.add_argument("--candidate", required=True)
    p_act.add_argument("--activated-by", required=True)
    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("--target", required=True)
    p_rb.add_argument("--rolled-back-by", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "list":
            payload = list_models()
        elif args.action == "inspect":
            payload = inspect_model(args.version)
        elif args.action == "verify":
            payload = verify_registry()
        elif args.action == "validate":
            payload = validate_candidate(args.candidate)
        elif args.action == "approve":
            payload = approve_candidate(args.candidate, approved_by=args.approved_by)
        elif args.action == "activate":
            payload = activate_candidate(args.candidate, activated_by=args.activated_by)
        else:
            payload = rollback_to(args.target, rolled_back_by=args.rolled_back_by)
    except LifecycleError as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)], "production_authorized": False}, indent=2))
        return 1
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _serve_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="yield_improvement serve",
        description="Read-only FastAPI adapter for the Node.js dashboard. GET only. Production remains forbidden.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print("FastAPI/uvicorn is not installed. pip install 'yield-improvement[api]'")
        return 1
    from yield_improvement.api.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "generate":
        return _generate_main(argv_list[1:])
    if argv_list and argv_list[0] == "detect":
        return _detect_main(argv_list[1:])
    if argv_list and argv_list[0] in {"hypothesize", "compose"}:
        return _hypothesize_main(argv_list[1:])
    if argv_list and argv_list[0] == "opportunity":
        return _opportunity_main(argv_list[1:])
    if argv_list and argv_list[0] == "validate":
        return _validate_main(argv_list[1:])
    if argv_list and argv_list[0] == "report":
        return _report_main(argv_list[1:])
    if argv_list and argv_list[0] == "dashboard":
        return _dashboard_main(argv_list[1:])
    if argv_list and argv_list[0] == "ml":
        return _ml_main(argv_list[1:])
    if argv_list and argv_list[0] in {"monitor", "monitor-report"}:
        return _monitor_main(argv_list[1:], write=True)
    if argv_list and argv_list[0] == "retrain":
        return _retrain_main(argv_list[1:])
    if argv_list and argv_list[0] == "model":
        return _model_main(argv_list[1:])
    if argv_list and argv_list[0] == "serve":
        return _serve_main(argv_list[1:])
    parser = _build_parser()
    args = parser.parse_args(argv_list)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    target = args.die_attempts or args.path
    if not target:
        parser.print_help()
        return 2
    path = Path(target)
    try:
        if path.is_dir():
            result = run_fixture_dir(path)
        elif path.name.startswith("case_") and (fixtures_fpy_dir() / path.name).is_dir():
            result = run_fixture_dir(fixtures_fpy_dir() / path.name)
        else:
            result = run_pipeline(path, args.test_results, config_dir=args.config_dir)
    except YieldImprovementError as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)]}, indent=2))
        return 1
    print(json.dumps(result.to_public_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
