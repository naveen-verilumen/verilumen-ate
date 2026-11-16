"""Traceability copied from upstream bundles. No new analytical identity."""

from __future__ import annotations

from yield_improvement.detectors.contract import DetectorBundle
from yield_improvement.hypotheses.contract import HypothesisBundle
from yield_improvement.opportunity.contract import OpportunityBundle
from yield_improvement.reporting.contract import ReportTraceability, ReportValidation
from yield_improvement.validation.contract import ValidationBundle


def build_traceability(
    *,
    report_id: str,
    dataset_id: str,
    generated_at: str,
    pipeline_version: str,
    detectors: DetectorBundle,
    hypotheses: HypothesisBundle,
    opportunities: OpportunityBundle,
    validation: ValidationBundle,
    validation_rows: list[ReportValidation],
) -> ReportTraceability:
    versions = dict(validation.config_versions)
    return ReportTraceability(
        report_id=report_id,
        analysis_id=hypotheses.analysis_id,
        dataset_id=dataset_id,
        pipeline_version=pipeline_version,
        generated_at=generated_at,
        fpy_policy_version=versions.get("fpy_policy", ""),
        calibration_version=versions.get("calibration", ""),
        safety_policy_version=versions.get("safety_policy", ""),
        config_versions=versions,
        hypothesis_ids=[h.hypothesis_id for h in hypotheses.hypotheses],
        opportunity_ids=[o.opportunity_id for o in opportunities.opportunities],
        validation_ids=[row.validation_id for row in validation_rows],
        detector_ids=sorted(detectors.results),
    )
