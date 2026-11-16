"""Streamlit entry. Consumes EngineeringReport only; widgets do not call detectors."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yield_improvement.dashboard.components import (
    render_data_quality,
    render_evidence,
    render_fpy_loss,
    render_hypotheses,
    render_opportunity,
    render_overview,
    render_traceability,
    render_validation,
)
from yield_improvement.reporting.contract import EngineeringReport
from yield_improvement.reporting.renderer import load_report_json


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="yield_improvement dashboard")
    parser.add_argument("--report", help="Path to <dataset_id>_engineering_report.json")
    parser.add_argument("--dataset-dir", help="Agent-visible directory; builds a report then displays it")
    parser.add_argument("--config-dir")
    args, _unknown = parser.parse_known_args(argv)
    return args


def load_report(args: argparse.Namespace) -> EngineeringReport:
    if args.report:
        return load_report_json(args.report)
    if args.dataset_dir:
        from yield_improvement.config.loader import load_config
        from yield_improvement.reporting.adapter import build_report_from_dir

        cfg = load_config(Path(args.config_dir) if args.config_dir else None)
        return build_report_from_dir(args.dataset_dir, config=cfg)
    raise SystemExit("pass --report <json> or --dataset-dir <agent_visible_dir>")


def render_report(report: EngineeringReport) -> None:
    import streamlit as st

    st.set_page_config(page_title="Yield Improvement — Engineering Report", layout="wide")
    st.title("Yield Improvement Agent — Engineering Report")
    st.caption("Advisory presentation of Phase 1–6 results. Production action is forbidden.")
    page = st.sidebar.radio(
        "Section",
        [
            "Overview",
            "FPY Loss",
            "Evidence",
            "Hypotheses",
            "Opportunity",
            "Validation",
            "Data Quality",
            "Traceability",
        ],
    )
    if page == "Overview":
        render_overview(report)
    elif page == "FPY Loss":
        render_fpy_loss(report)
    elif page == "Evidence":
        render_evidence(report)
    elif page == "Hypotheses":
        render_hypotheses(report)
    elif page == "Opportunity":
        render_opportunity(report)
    elif page == "Validation":
        render_validation(report)
    elif page == "Data Quality":
        render_data_quality(report)
    else:
        render_traceability(report)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    report = load_report(args)
    render_report(report)


if __name__ == "__main__":
    main(sys.argv[1:])
