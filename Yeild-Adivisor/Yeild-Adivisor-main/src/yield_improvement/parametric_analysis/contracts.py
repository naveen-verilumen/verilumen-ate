# Contracts - Stage 1.2
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from yield_improvement.reporting.contract import SAFETY_STATEMENT as REPORTING_SAFETY_STATEMENT

ThresholdDirection = Literal['UPPER_BOUND', 'LOWER_BOUND', 'BAND']
ThresholdStatus = Literal['INVESTIGATION_CANDIDATE_ONLY', 'INSUFFICIENT_EVIDENCE', 'NO_THRESHOLD_ESTABLISHED']
SpecProvenance = Literal['SYNTHETIC_GENERATOR_REFERENCE', 'AUTHORITATIVE_SPECIFICATION', 'UNAVAILABLE']

class ParameterSummaryStatistics(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    count: int = Field(ge=0)
    available: bool = True
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    p05: float | None = None
    p25: float | None = None
    p75: float | None = None
    p95: float | None = None
    iqr: float | None = None

class PopulationDataQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    eligible_physical_dies: int = Field(ge=0)
    valid_first_pass_measurements: int = Field(ge=0)
    missing_measurements: int = Field(ge=0)
    retest_measurements_excluded: int = Field(ge=0)
    quarantined_attempts_count: int = Field(ge=0, default=0)
    quarantined_dies_count: int = Field(ge=0, default=0)
    first_pass_pass_count: int = Field(ge=0)
    first_pass_fail_count: int = Field(ge=0)
    target_failure_code_count: int = Field(ge=0, default=0)
    non_target_count: int = Field(ge=0, default=0)
    n_lots_covered: int = Field(ge=0)
    n_wafers_covered: int = Field(ge=0)
    data_quality_warnings: list[str] = Field(default_factory=list)

class SeparationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    mean_difference: float | None = None
    pooled_standard_deviation: float | None = None
    cohens_d: float | None = None
    abs_cohens_d: float | None = None
    distribution_overlap_description: str
    large_effect_size_flag: bool

class ConfusionMatrix(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    evaluated_population_description: str
    total_evaluated_count: int = Field(ge=0)
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)
    specificity: float | None = Field(default=None, ge=0.0, le=1.0)
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    youden_j: float | None = Field(default=None, ge=-1.0, le=1.0)

class CandidateThreshold(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    candidate_value: float
    direction: ThresholdDirection
    status: Literal['INVESTIGATION_CANDIDATE_ONLY'] = 'INVESTIGATION_CANDIDATE_ONLY'
    target_population_description: str
    target_failure_code: str | None = None
    selection_method: str
    selection_objective: str
    n_dies_flagged: int = Field(ge=0)
    flagged_share_of_measured: float = Field(ge=0.0, le=1.0)
    flagged_share_of_all_eligible: float = Field(ge=0.0, le=1.0)
    training_confusion_matrix: ConfusionMatrix
    uncertainty_notes: str
    disclaimer: str = 'INVESTIGATION_CANDIDATE_ONLY. Not an approved production limit. Production action is FORBIDDEN. Safety-eligible production is 0.0%.'

class LotValidationFold(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    held_out_lot_id: str
    train_lot_ids: list[str]
    train_candidate_established: bool
    train_candidate_value: float | None = None
    train_target_fails: int = 0
    train_non_target_count: int = 0
    held_out_die_count: int
    held_out_target_fails: int
    held_out_non_target_count: int = 0
    held_out_true_positives: int = 0
    held_out_false_positives: int = 0
    held_out_false_negatives: int = 0
    held_out_true_negatives: int = 0
    held_out_sensitivity: float | None = None
    held_out_specificity: float | None = None
    fold_status: Literal['EVALUATED', 'INSUFFICIENT_TRAIN_DATA', 'NO_HELD_OUT_TARGET_FAILURES']

class LotValidationSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    evaluation_strategy: str = 'Leave-One-Out Lot Cross-Validation (5 folds)'
    folds: list[LotValidationFold]
    generalization_assessment: str
    potential_lot_shifts_detected: bool
    performance_warning_lot_ids: list[str] = Field(default_factory=list)

class ParametricAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    parameter_name: str
    source_field: str = 'measurement'
    unit: str
    measurement_semantics: str
    spec_provenance: SpecProvenance = 'SYNTHETIC_GENERATOR_REFERENCE'
    synthetic_reference_lower: float | None = None
    synthetic_reference_upper: float | None = None
    spec_disclaimer: str = 'No authoritative production specifications exist in repository. Reference limits shown are synthetic generator inputs only.'
    data_quality: PopulationDataQuality
    overall_distribution: ParameterSummaryStatistics
    pass_distribution: ParameterSummaryStatistics
    fail_distribution: ParameterSummaryStatistics
    specific_failure_distribution: ParameterSummaryStatistics | None = None
    target_failure_code: str | None = None
    overall_separation: SeparationMetrics
    specific_failure_separation: SeparationMetrics | None = None
    threshold_status: ThresholdStatus
    candidate_threshold: CandidateThreshold | None = None
    lot_validation: LotValidationSummary | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    engineering_summary: str

class ParametricAnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    dataset_id: str
    generated_at: str
    n_parameters_analyzed: int
    results: list[ParametricAnalysisResult]
    extraction_warnings: list[str] = Field(default_factory=list)
    quarantined_attempts_count: int = 0
    safety_invariants: dict[str, Any] = Field(
        default_factory=lambda: {
            'production_action': 'FORBIDDEN',
            'production_authorized': False,
            'safety_eligible_production': 0.0,
        }
    )
    production_action: Literal['FORBIDDEN'] = 'FORBIDDEN'
    production_authorized: Literal[False] = False
    safety_eligible_production_rate: Literal[0.0] = 0.0
    safety_statement: str = REPORTING_SAFETY_STATEMENT
