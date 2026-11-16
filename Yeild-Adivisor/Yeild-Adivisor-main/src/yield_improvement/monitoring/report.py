"""Markdown/JSON writers for ModelHealthReport. Advisory only."""

from __future__ import annotations

import json
from pathlib import Path

from yield_improvement.monitoring.contracts import ModelHealthReport
from yield_improvement.utils.paths import repo_root


def default_output_dir() -> Path:
    folder = repo_root() / "evaluation" / "monitoring"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_health_json(report: ModelHealthReport, path: Path | None = None) -> Path:
    out = path or (default_output_dir() / f"{report.current_dataset_id}_model_health.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_public_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def render_markdown(report: ModelHealthReport) -> str:
    lines = [
        f"# Model health — {report.current_dataset_id}",
        "",
        report.disclaimer,
        "",
        f"- overall_status: **{report.overall_status}**",
        f"- label_mode: {report.label_mode}",
        f"- model_version: {report.model_version}",
        f"- feature_version: {report.feature_version}",
        f"- calibration_version: {report.calibration_version}",
        f"- reference_version: {report.reference_version}",
        f"- reference_dataset_id: {report.reference_dataset_id}",
        f"- lots/wafers/dies: {report.n_lots} / {report.n_wafers} / {report.n_dies}",
        f"- recommendations: {', '.join(report.recommendations)}",
        f"- triggers: {', '.join(report.triggers) or 'none'}",
        f"- production_authorized: {report.production_authorized}",
        f"- retrained: {report.retrained}",
        "",
        "## Dimensions",
        "",
        f"| Dimension | Status | Availability |",
        f"|---|---|---|",
        f"| feature_drift | {report.feature_drift.status} | {report.feature_drift.availability} |",
        f"| prediction_drift | {report.prediction_drift.status} | {report.prediction_drift.availability} |",
        f"| target_drift | {report.target_drift.status} | {report.target_drift.availability} |",
        f"| calibration | {report.calibration.status} | {report.calibration.availability} |",
        f"| performance | {report.performance.status} | {report.performance.availability} |",
        f"| data_quality | {report.data_quality.status} | {report.data_quality.availability} |",
        "",
        "Prediction drift is not model failure. Feature importance is not causal.",
        "",
        "## Limitations",
        "",
    ]
    for item in report.limitations:
        lines.append(f"- {item}")
    if report.overall_status == "NEEDS_RETRAINING":
        lines.extend(
            [
                "",
                "## Retraining recommendation (advisory)",
                "",
                "Model retraining should be considered. This report did not train, replace, or deploy a model.",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_health_markdown(report: ModelHealthReport, path: Path | None = None) -> Path:
    out = path or (default_output_dir() / f"{report.current_dataset_id}_model_health.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="utf-8")
    return out


def write_health_outputs(report: ModelHealthReport, directory: Path | None = None) -> tuple[Path, Path]:
    folder = directory or default_output_dir()
    json_path = write_health_json(report, folder / f"{report.current_dataset_id}_model_health.json")
    md_path = write_health_markdown(report, folder / f"{report.current_dataset_id}_model_health.md")
    return json_path, md_path
