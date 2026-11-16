"""Unconfirmed hypothesis contracts. Never a confirmed root cause."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HypothesisStatus = Literal["UNCONFIRMED"]
EvidenceRole = Literal[
    "PRIMARY_EVIDENCE",
    "SECONDARY_SUPPORT",
    "CORRELATED_SUPPORT",
    "CONFLICTING_EVIDENCE",
]
EvidenceTier = Literal[
    "STRONG_EVIDENCE",
    "MODERATE_EVIDENCE",
    "WEAK_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
]
AssociationClass = Literal[
    "PRIMARY_EVIDENCE",
    "SECONDARY_ASSOCIATION",
    "WEAK_ASSOCIATION",
    "INSUFFICIENT_EVIDENCE",
]


class StatisticalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    detector: str
    method: str
    status: str
    role: EvidenceRole
    sample_size: int | None = None
    effect_size: float | None = None
    effect_size_metric: str | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None
    correction_method: str | None = None
    affected_population: dict[str, Any] | None = None
    baseline_population: dict[str, Any] | None = None
    scope: str | None = None


class Hypothesis(BaseModel):
    """Associative, unconfirmed explanation. `not_a_root_cause` is always true."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    family: str
    detail: str
    statement: str
    status: HypothesisStatus = "UNCONFIRMED"
    not_a_root_cause: Literal[True] = True
    association_class: AssociationClass
    evidence_tier: EvidenceTier
    evidence_score: float
    score_status: Literal["PRELIMINARY"] = "PRELIMINARY"
    confidence_level: Literal["INSUFFICIENT", "LOW", "MEDIUM", "HIGH"]
    rank: int
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list)
    supporting_detectors: list[str] = Field(default_factory=list)
    conflicting_detectors: list[str] = Field(default_factory=list)
    competing_hypothesis_ids: list[str] = Field(default_factory=list)
    statistical_evidence: list[StatisticalEvidence] = Field(default_factory=list)
    effect_sizes: list[dict[str, Any]] = Field(default_factory=list)
    affected_population: dict[str, Any] | None = None
    data_coverage: dict[str, Any] = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    validation_required: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    explanation: str = ""


class HypothesisBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str
    current_fpy: float | None = None
    n_eligible: int
    no_confident_hypothesis: bool
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    detector_summary: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    score_status: Literal["PRELIMINARY"] = "PRELIMINARY"

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("confirmed_root_cause", None)
        for hyp in payload.get("hypotheses", []):
            hyp.pop("confirmed_root_cause", None)
            hyp["not_a_root_cause"] = True
            hyp["status"] = "UNCONFIRMED"
        return payload
