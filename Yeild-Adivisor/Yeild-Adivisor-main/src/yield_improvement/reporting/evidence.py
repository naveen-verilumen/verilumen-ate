"""Copy detector findings for presentation. Does not re-run detectors."""

from __future__ import annotations

from yield_improvement.detectors.contract import DetectorBundle
from yield_improvement.reporting.contract import ReportEvidenceFinding


def build_evidence_findings(detectors: DetectorBundle) -> list[ReportEvidenceFinding]:
    rows: list[ReportEvidenceFinding] = []
    for name in sorted(detectors.results):
        res = detectors.results[name]
        rows.append(
            ReportEvidenceFinding(
                detector=name,
                status=res.status,
                family=res.hypothesis_family,
                detail=res.hypothesis_detail,
                method=res.method,
                effect_size=res.effect_size,
                effect_size_metric=res.effect_size_metric,
                p_value=res.p_value,
                adjusted_p_value=res.adjusted_p_value,
                sample_size=res.sample_size,
                data_gaps=list(res.data_gaps),
                not_a_root_cause=True,
            )
        )
    return rows
