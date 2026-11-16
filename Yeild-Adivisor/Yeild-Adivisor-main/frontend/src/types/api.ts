export type DetectorStatus = "SIGNAL" | "NO_SIGNAL" | "INSUFFICIENT_DATA" | string;
export type HypothesisStatus = "UNCONFIRMED" | string;
export type EvidenceTier =
  | "STRONG_EVIDENCE"
  | "MODERATE_EVIDENCE"
  | "WEAK_EVIDENCE"
  | "INSUFFICIENT_EVIDENCE"
  | string;
export type HealthState =
  | "HEALTHY"
  | "MONITOR"
  | "REVIEW"
  | "DEGRADED"
  | "NEEDS_RETRAINING"
  | "INSUFFICIENT_DATA"
  | string;

export interface ReportParetoRow {
  attribution_mode: "PRIMARY_FAILURE" | "ANY_FAIL";
  failure_key: string;
  family: string | null;
  detail: string | null;
  affected_die_count: number;
  percentage_of_eligible: number;
  share_of_fails: number;
  selection_rule: string | null;
  taxonomy_code: string | null;
}

export interface ReportFpySummary {
  eligible_die_count: number;
  first_pass_pass_count: number;
  first_pass_fail_count: number;
  excluded_count: number;
  fpy: number | null;
  fpy_loss: number | null;
  fpy_policy_version: string;
  abort_policy: string;
  policy_notes: string[];
}

export interface ReportLossSummary {
  primary_failure: ReportParetoRow[];
  any_fail: ReportParetoRow[];
  primary_available: boolean;
  primary_unavailable_note: string | null;
  modes_not_combined: true;
}

export interface ReportEvidenceFinding {
  detector: string;
  status: DetectorStatus;
  family: string | null;
  detail: string | null;
  method: string;
  effect_size: number | null;
  effect_size_metric: string | null;
  p_value: number | null;
  adjusted_p_value: number | null;
  sample_size: number | null;
  data_gaps: string[];
  not_a_root_cause: true;
}

export interface ReportHypothesis {
  rank: number;
  hypothesis_id: string;
  family: string;
  detail: string;
  status: HypothesisStatus;
  statement: string;
  explanation: string;
  why_it_exists: string;
  association_class: string;
  evidence_tier: EvidenceTier;
  evidence_score: number;
  score_status: string;
  supporting_detectors: string[];
  conflicting_detectors: string[];
  statistical_evidence: Record<string, unknown>[];
  effect_sizes: Record<string, unknown>[];
  affected_population: Record<string, unknown> | null;
  data_coverage: Record<string, unknown>;
  data_gaps: string[];
  limitations: string[];
  validation_required: string[];
  validation_steps: string[];
  validation_recommendation: string | null;
  opportunity_id: string | null;
  observed_loss_rate: number | null;
  upper_bound_rate: number | null;
  plausible_rate: number | null;
  plausible_unavailable: boolean;
  overlap_count: number | null;
  exclusive_count: number | null;
  union_count: number | null;
  intersection_count: number | null;
  not_a_root_cause: true;
}

export interface ReportOpportunity {
  opportunity_id: string;
  hypothesis_id: string | null;
  family: string | null;
  detail: string | null;
  attribution_mode: string;
  status: string;
  observed_loss_count: number;
  observed_loss_rate: number;
  upper_bound_count: number | null;
  upper_bound_rate: number | null;
  plausible_count: number | null;
  plausible_rate: number | null;
  plausible_unavailable: boolean;
  plausible_label: string;
  calibration_status: string;
  affected_population_count: number;
  population_definition: string;
  included_in_union: boolean;
  overlap_count: number;
  exclusive_count: number | null;
  union_count: number | null;
  intersection_count: number;
  statement: string;
  safety_eligible_production_rate: 0;
}

export interface ReportOverlap {
  sum_of_individual_upper_bounds_rate: number | null;
  union_upper_bound_rate: number | null;
  union_upper_bound_count: number | null;
  intersection_fail_count: number | null;
  sum_exceeds_observed: boolean | null;
  note: string;
  individuals: Record<string, unknown>[];
}

export interface ReportInvestigationItem {
  hypothesis_id: string | null;
  family: string | null;
  detail: string | null;
  recommendation: string | null;
  steps: string[];
}

export interface ReportDataGaps {
  required: string[];
  recommended: string[];
  detector_specific: string[];
  ungrouped: string[];
}

export interface EngineeringReport {
  report_id: string;
  analysis_id: string;
  generated_at: string;
  dataset_id: string;
  fpy_summary: ReportFpySummary;
  loss_summary: ReportLossSummary;
  evidence_findings: ReportEvidenceFinding[];
  hypotheses: ReportHypothesis[];
  opportunities: ReportOpportunity[];
  overlap: ReportOverlap;
  no_actionable_recommendation: boolean;
  investigation_plan: ReportInvestigationItem[];
  data_gaps: ReportDataGaps;
  limitations: string[];
  safety_statement: string;
  near_limit_notice: string | null;
  sequence_censoring_notice: string | null;
  no_actionable_notice: string | null;
  evidence_score_notice: string;
  overlap_notice: string;
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_eligible_production_count: 0;
  safety_eligible_production_rate: 0;
  invoked_agents: string[];
  disclaimer: string;
  pipeline_version: string;
}

export interface MlMetrics {
  roc_auc: number | null;
  pr_auc: number | null;
  brier: number | null;
  failure_capture_at_top_10_percent: number | null;
  failure_capture_at_top_20_percent: number | null;
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  log_loss?: number | null;
  n_samples?: number;
  n_positives?: number;
}

export interface FeatureImportanceRow {
  feature: string;
  importance: number;
  std?: number;
  kind?: string;
  note?: string;
}

export interface MlSnapshot {
  available: boolean;
  model_name: string | null;
  model_version: string | null;
  feature_set_version?: string | null;
  split_strategy?: string | null;
  evidence_role: "SECONDARY_SUPPORT";
  independence: false;
  metrics: MlMetrics | null;
  calibration: Record<string, unknown> | null;
  feature_names: string[];
  feature_importance: FeatureImportanceRow[];
  disclaimer: string | null;
  note?: string;
  source?: string;
}

export interface HealthDimension {
  dimension: string | null;
  status: string | null;
  availability: string | null;
  notes: string;
}

export interface HealthSnapshot {
  available: boolean;
  overall_status: HealthState | null;
  reduced_ml_evidence: boolean;
  model_version: string | null;
  label_mode?: string | null;
  dimensions: {
    feature_drift: HealthDimension | null;
    prediction_drift: HealthDimension | null;
    target_drift: HealthDimension | null;
    calibration: HealthDimension | null;
    performance: HealthDimension | null;
    data_quality: HealthDimension | null;
  } | null;
  recommendations: string[];
  triggers: string[];
  disclaimer: string;
  note?: string;
  production_action?: "FORBIDDEN";
  production_authorized?: false;
  retrained?: false;
  model_replaced?: false;
}

export interface RegistrySnapshot {
  available: boolean;
  active_version: string | null;
  state: string | null;
  architecture: string | null;
  production_action?: "FORBIDDEN";
  production_authorized?: false;
  automatic_activation?: boolean;
  automatic_retraining?: boolean;
}

export interface DatasetLot {
  lot_id: string;
  display_name: string;
}

export interface DatasetListItem {
  dataset_id: string;
  display_name?: string;
  dataset_type?: string;
  path: string;
  has_die_attempts: boolean;
  has_persisted_report: boolean;
  has_health_report: boolean;
  n_lots?: number | null;
  n_wafers?: number | null;
  n_dies?: number | null;
  die_count: number | null;
  product_id: string | null;
  lots?: DatasetLot[];
}

export interface TestCatalogEntry {
  test_id: string;
  test_name: string;
  test_type: string;
  description?: string;
  sequence_index?: number | null;
  classified?: boolean;
  display_label?: string;
}

export interface TestCatalogPayload {
  catalog_id?: string;
  catalog_version?: string;
  dataset_id?: string;
  source?: string;
  note?: string;
  tests: TestCatalogEntry[];
}

export interface WaferMapDie {
  lot_id: string;
  wafer_id: string;
  die_id: string;
  x: number | null;
  y: number | null;
  first_pass_result: "PASS" | "FAIL" | string;
  failed_test_id: string | null;
  failure_code: string | null;
  is_first_fail: boolean | null;
  retest_available: boolean;
  measurements?: Record<string, number | null>;
}

export type DieRecommendationStatus =
  | "ACTIONABLE_CANDIDATE_COMPARISON"
  | "INSUFFICIENT_EVIDENCE"
  | "NON_PARAMETRIC_FAILURE"
  | "MISSING_MEASUREMENT"
  | "PASSING_DIE";

export interface DieRecommendation {
  status: DieRecommendationStatus;
  primary_failure_code: string | null;
  failed_test_id: string | null;
  parameter_name: string | null;
  unit: string | null;
  measurement_semantics?: string | null;
  actual_measured_value: number | null;
  candidate_boundary: number | null;
  candidate_direction: ThresholdDirection | null;
  candidate_status: ThresholdStatus | string | null;
  signed_difference: number | null;
  exceeds_candidate_boundary: boolean | null;
  approved_production_limit_status: string;
  recommended_investigation_steps: string[];
  evidence_limitations: string[];
  missing_evidence: string[];
  safety_banner: string;
}

export interface WaferMapLot {
  lot_id: string;
  display_name: string;
  wafers: string[];
}

export interface WaferMapResponse {
  dataset_id: string;
  source?: string;
  grain?: string;
  n_dies: number;
  n_pass: number;
  n_fail: number;
  lots: WaferMapLot[];
  dies: WaferMapDie[];
  production_action?: "FORBIDDEN";
  production_authorized?: false;
}

export interface DashboardResponse {
  dataset_id: string;
  selected_lot_id?: string | null;
  selected_lot_display?: string | null;
  lots?: DatasetLot[];
  generated_at: string;
  report: EngineeringReport;
  test_catalog?: TestCatalogPayload | null;
  ml: MlSnapshot;
  health: HealthSnapshot;
  registry: RegistrySnapshot;
  recommendations?: RecommendationBundle;
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_eligible_production_count: 0;
  safety_eligible_production_rate: 0;
  invoked_agents: string[];
  safety_statement: string;
  disclaimer: string;
}

export interface DatasetListResponse {
  datasets: DatasetListItem[];
}

export type RecommendationCategory =
  | "Lot investigation"
  | "Wafer investigation"
  | "Spatial investigation"
  | "Parametric investigation"
  | "Equipment investigation"
  | "Environmental investigation"
  | "Test measurement/repeatability investigation"
  | "Near-limit investigation"
  | "Data-quality investigation";

export type PriorityTier = "HIGH" | "MEDIUM" | "LOW";
export type ConfidenceTier = "HIGH" | "MODERATE" | "LOW" | "INSUFFICIENT";
export type MLEvidenceStatus = "SUPPORTED" | "NEEDS_MORE_DATA" | "NOT_AVAILABLE";

export type EvidenceClassification =
  | "OBSERVED_FACT"
  | "STATISTICAL_ASSOCIATION"
  | "UNCONFIRMED_HYPOTHESIS"
  | "INSUFFICIENT_EVIDENCE";

export type EvidenceStrength = "STRONG" | "MODERATE" | "WEAK" | "INSUFFICIENT";


export type FeedbackStatus =
  | "PROPOSED"
  | "ACCEPTED_FOR_INVESTIGATION"
  | "IN_PROGRESS"
  | "CONFIRMED"
  | "REJECTED"
  | "INCONCLUSIVE"
  | "VALIDATION_PENDING"
  | "CLOSED";

export interface ValidationStep {
  step_number: number;
  step_id: string;
  title: string;
  investigation_action: string;
  required_evidence: string;
  expected_measurement: string;
  acceptance_criteria: string;
  rejection_criteria: string;
  limitations_and_safety: string;
}

export interface ValidationProtocol {
  protocol_id: string;
  target_hypothesis?: string | null;
  steps: ValidationStep[];
  control_comparison?: string | null;
  replication_check: string;
  physical_fa_or_metrology?: string | null;
  split_lot_proposal?: string | null;
  downstream_reliability_risk: string;
  disclaimer: string;
}

export interface SupportingEvidenceItem {
  evidence_type: string;
  evidence_classification: EvidenceClassification;
  source_dataset: string;
  source_artifact: string;
  entity_scope: string;
  numerator?: number | null;
  denominator?: number | null;
  observed_value?: number | string | null;
  baseline_value?: number | string | null;
  comparison_baseline?: string | null;
  unit?: string | null;
  time_scope: string;
  validation_state: string;
  limitations: string[];
}

export interface EngineeringRecommendation {
  recommendation_id: string;
  hypothesis_id?: string | null;
  title: string;
  summary?: string;
  recommendation_category: RecommendationCategory;
  status: FeedbackStatus;
  scope?: "GLOBAL" | "LOT_SPECIFIC";
  lot_id?: string | null;
  priority_rank: number;

  priority_tier: PriorityTier;
  confidence_tier: ConfidenceTier;
  ranking_score: number;
  ranking_rationale: string;
  observed_pattern: string;
  target_population: string;
  affected_die_count: number;
  eligible_die_count: number;
  subgroup_die_count?: number | null;
  subgroup_failed_die_count?: number | null;
  observed_failure_rate: number;
  baseline_failure_rate: number;
  supporting_detectors: string[];
  hypothesis_confidence: string;
  ml_evidence_status: MLEvidenceStatus;
  ml_evidence_notes: string;
  missing_evidence: string[];
  limitations: string[];
  observed_facts?: string[];
  supporting_evidence?: SupportingEvidenceItem[];
  evidence_strength?: EvidenceStrength;
  uncertainties?: string[];
  data_gaps?: string[];
  recommended_next_steps?: string[];
  validation_status?: string;
  recommended_action: string;
  reason: string;
  expected_information: string;
  validation_method: string;
  success_criteria: string;
  required_data: string[];
  risk_if_ignored: string;
  next_step_if_confirmed: string;
  next_step_if_rejected: string;
  validation_protocol: ValidationProtocol;
  observed_loss_rate: number;
  upper_bound_rate?: number | null;
  upper_bound_count?: number | null;
  plausible_rate?: number | null;
  plausible_count?: number | null;
  safety_eligible_production_rate: 0;
  opportunity_disclaimer: string;
  production_action: "FORBIDDEN";
  production_authorized: false;
  not_a_root_cause: true;
  safety_statement: string;
  safety_status?: string;
}


export interface FailingDieMeasurement {
  parameter_name: string;
  value: number;
  unit: string;
  lower_limit: number | null;
  upper_limit: number | null;
  near_limit: boolean;
  proximity_ratio: number | null;
}

export interface FailingDieRecord {
  lot_id: string;
  wafer_id: string;
  die_id: string;
  x: number | null;
  y: number | null;
  first_pass_result: "FAIL" | string;
  primary_failure_code: string;
  failed_test_ids: string[];
  relevant_measurements: FailingDieMeasurement[];
}

export interface RecommendationFailingDiesCounts {
  subgroup_failing_dies: number;
  subgroup_eligible_dies: number;
  subgroup_failure_rate: number;
  lot_id: string | null;
  lot_display: string | null;
  lot_failing_dies: number | null;
  lot_eligible_dies: number | null;
  lot_failure_rate: number | null;
  dataset_failing_dies: number;
  dataset_eligible_dies: number;
  dataset_failure_rate: number;
  subgroup_failing_measurements: number | null;
  subgroup_eligible_measurements: number | null;
}

export interface RecommendationFailingDiesResponse {
  dataset_id: string;
  recommendation_id: string;
  lot_id: string | null;
  title: string;
  target_population: string;
  recommendation_category: string;
  subgroup_definition: string;
  counts: RecommendationFailingDiesCounts;
  failing_dies_count: number;
  failing_dies: FailingDieRecord[];
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_statement: string;
  disclaimer: string;
}

export interface FeedbackRecord {
  feedback_id: string;
  recommendation_id: string;
  dataset_id: string;
  previous_status: FeedbackStatus;
  new_status: FeedbackStatus;
  engineer: string;
  investigation_notes: string;
  evidence_collected: string[];
  timestamp: string;
  investigation_conclusion?: string | null;
  hypothesis_confirmed?: boolean | null;
  independent_validation_evidence?: string | null;
  validation_dataset?: string | null;
  pre_investigation_metrics?: Record<string, unknown> | null;
  post_investigation_metrics?: Record<string, unknown> | null;
  adverse_effects?: string | null;
  separately_authorized_corrective_action_ref?: string | null;
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_eligible_production_rate: 0;
}

export interface FeedbackCreateRequest {
  new_status: FeedbackStatus;
  engineer: string;
  investigation_notes: string;
  evidence_collected?: string[];
  investigation_conclusion?: string | null;
  hypothesis_confirmed?: boolean | null;
  independent_validation_evidence?: string | null;
  validation_dataset?: string | null;
  pre_investigation_metrics?: Record<string, unknown> | null;
  post_investigation_metrics?: Record<string, unknown> | null;
  adverse_effects?: string | null;
  separately_authorized_corrective_action_ref?: string | null;
}

export interface FeedbackHistoryResponse {
  recommendation_id: string;
  dataset_id: string;
  current_status: FeedbackStatus;
  history: FeedbackRecord[];
}

export interface RecommendationBundle {
  dataset_id: string;
  selected_lot_id?: string | null;
  lot_note?: string | null;
  recommendation_count: number;
  recommendations: EngineeringRecommendation[];

  ranking_policy: string;
  ranking_version: string;
  evidence_limitations_summary: string[];
  ml_evidence_status: MLEvidenceStatus;
  ml_evidence_summary: string;
  safety_invariants: {
    production_action: "FORBIDDEN";
    production_authorized: false;
    safety_eligible_production: 0;
  };
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_eligible_production_rate: 0;
  disclaimer: string;
}

export type ThresholdDirection = "UPPER_BOUND" | "LOWER_BOUND" | "BAND";
export type ThresholdStatus =
  | "INVESTIGATION_CANDIDATE_ONLY"
  | "INSUFFICIENT_EVIDENCE"
  | "NO_THRESHOLD_ESTABLISHED";
export type SpecProvenance =
  | "SYNTHETIC_GENERATOR_REFERENCE"
  | "AUTHORITATIVE_SPECIFICATION"
  | "UNAVAILABLE";
export type FoldStatus =
  | "EVALUATED"
  | "INSUFFICIENT_TRAIN_DATA"
  | "NO_HELD_OUT_TARGET_FAILURES";

export interface ParameterSummaryStatistics {
  count: number;
  available: boolean;
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  p05: number | null;
  p25: number | null;
  p75: number | null;
  p95: number | null;
  iqr: number | null;
}

export interface PopulationDataQuality {
  eligible_physical_dies: number;
  valid_first_pass_measurements: number;
  missing_measurements: number;
  retest_measurements_excluded: number;
  quarantined_attempts_count: number;
  quarantined_dies_count: number;
  first_pass_pass_count: number;
  first_pass_fail_count: number;
  target_failure_code_count: number;
  non_target_count: number;
  n_lots_covered: number;
  n_wafers_covered: number;
  data_quality_warnings: string[];
}

export interface SeparationMetrics {
  mean_difference: number | null;
  pooled_standard_deviation: number | null;
  cohens_d: number | null;
  abs_cohens_d: number | null;
  distribution_overlap_description: string;
  large_effect_size_flag: boolean;
}

export interface ConfusionMatrix {
  evaluated_population_description: string;
  total_evaluated_count: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
  sensitivity: number | null;
  specificity: number | null;
  precision: number | null;
  recall: number | null;
  youden_j: number | null;
}

export interface CandidateThreshold {
  candidate_value: number;
  direction: ThresholdDirection;
  status: "INVESTIGATION_CANDIDATE_ONLY";
  target_population_description: string;
  target_failure_code: string | null;
  selection_method: string;
  selection_objective: string;
  n_dies_flagged: number;
  flagged_share_of_measured: number;
  flagged_share_of_all_eligible: number;
  training_confusion_matrix: ConfusionMatrix;
  uncertainty_notes: string;
  disclaimer: string;
}

export interface LotValidationFold {
  held_out_lot_id: string;
  train_lot_ids: string[];
  train_candidate_established: boolean;
  train_candidate_value: number | null;
  train_target_fails: number;
  train_non_target_count: number;
  held_out_die_count: number;
  held_out_target_fails: number;
  held_out_non_target_count: number;
  held_out_true_positives: number;
  held_out_false_positives: number;
  held_out_false_negatives: number;
  held_out_true_negatives: number;
  held_out_sensitivity: number | null;
  held_out_specificity: number | null;
  fold_status: FoldStatus;
}

export interface LotValidationSummary {
  evaluation_strategy: string;
  folds: LotValidationFold[];
  generalization_assessment: string;
  potential_lot_shifts_detected: boolean;
  performance_warning_lot_ids: string[];
}

export interface ParametricAnalysisResult {
  parameter_name: string;
  source_field: string;
  unit: string;
  measurement_semantics: string;
  spec_provenance: SpecProvenance;
  synthetic_reference_lower: number | null;
  synthetic_reference_upper: number | null;
  spec_disclaimer: string;
  data_quality: PopulationDataQuality;
  overall_distribution: ParameterSummaryStatistics;
  pass_distribution: ParameterSummaryStatistics;
  fail_distribution: ParameterSummaryStatistics;
  specific_failure_distribution: ParameterSummaryStatistics | null;
  target_failure_code: string | null;
  overall_separation: SeparationMetrics;
  specific_failure_separation: SeparationMetrics | null;
  threshold_status: ThresholdStatus;
  candidate_threshold: CandidateThreshold | null;
  lot_validation: LotValidationSummary | null;
  missing_evidence: string[];
  limitations: string[];
  engineering_summary: string;
}

export interface ParametricAnalysisReport {
  dataset_id: string;
  generated_at: string;
  n_parameters_analyzed: number;
  results: ParametricAnalysisResult[];
  extraction_warnings: string[];
  quarantined_attempts_count: number;
  safety_invariants: {
    production_action: "FORBIDDEN";
    production_authorized: false;
    safety_eligible_production: number;
  };
  production_action: "FORBIDDEN";
  production_authorized: false;
  safety_eligible_production_rate: 0;
}


