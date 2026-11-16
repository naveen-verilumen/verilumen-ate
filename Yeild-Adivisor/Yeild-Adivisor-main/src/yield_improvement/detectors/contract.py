"""Shared detector evidence contract. Never a confirmed root cause."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DetectorStatus = Literal["SIGNAL", "NO_SIGNAL", "INSUFFICIENT_DATA"]
ConfidenceOrdinal = Literal["INSUFFICIENT", "LOW", "MEDIUM", "HIGH"]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: Any = None
    note: str | None = None


class DetectorHypothesis(BaseModel):
    """One statistical comparison. Used for FDR across a run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detector: str
    label: str
    family: str | None = None
    detail: str | None = None
    p_value: float | None = None
    effect_size: float | None = None
    effect_size_metric: str | None = None
    sample_size: int | None = None
    n_affected: int | None = None
    n_baseline: int | None = None
    rate_affected: float | None = None
    rate_baseline: float | None = None


class DetectorResult(BaseModel):
    """Evidence packet. `not_a_root_cause` is always true. No confirmed_root_cause field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detector: str
    status: DetectorStatus
    not_a_root_cause: Literal[True] = True
    hypothesis_family: str | None = None
    hypothesis_detail: str | None = None
    affected_population: dict[str, Any] | None = None
    baseline_population: dict[str, Any] | None = None
    effect_size: float | None = None
    effect_size_metric: str | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None
    correction_method: str | None = None
    confidence: ConfidenceOrdinal = "INSUFFICIENT"
    evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    sample_size: int | None = None
    method: str
    calibration_keys: list[str] = Field(default_factory=list)
    hypotheses: list[DetectorHypothesis] = Field(default_factory=list)


class DetectorBundle(BaseModel):
    """Collected detector outputs. Not ranked. Not a hypothesis engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_eligible: int
    correction_method: str
    fdr_q: float
    alpha: float
    min_effect_size: float
    results: dict[str, DetectorResult]
    data_gaps: list[str] = Field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        for item in payload.get("results", {}).values():
            item.pop("confirmed_root_cause", None)
            item["not_a_root_cause"] = True
        return payload
