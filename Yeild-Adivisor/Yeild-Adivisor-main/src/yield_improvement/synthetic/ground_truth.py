"""Hidden ground-truth schema. Never written next to agent-visible CSVs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrueCause(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    family: str
    detail: str

    def code(self) -> str:
        return f"{self.family}.{self.detail}"


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    dataset_id: str
    generator_version: str
    seed: int
    profile: str
    true_causes: list[TrueCause]
    injected_parameters: dict[str, Any] = Field(default_factory=dict)
    affected_population: dict[str, Any] = Field(default_factory=dict)
    expected_signal: str
    confounders: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    notes: str | None = None


AGENT_MANIFEST_FORBIDDEN = (
    "scenario_id",
    "true_cause",
    "true_causes",
    "ground_truth",
    "injected_effect",
    "injected_parameters",
    "expected_hypothesis",
    "expected_signal",
    "generator_seed",
    "difficulty",
    "planted_cause",
    "planted_causes",
    "true_root_cause",
)
