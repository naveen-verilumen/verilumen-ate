import type {
  DashboardResponse,
  EngineeringReport,
  HealthSnapshot,
  MlSnapshot,
  RegistrySnapshot,
  ReportHypothesis,
} from "../types/api";
import { V2_TEST_CATALOG } from "./v2TestCatalog";

const SAFETY =
  "PRODUCTION ACTION: FORBIDDEN. SAFETY-ELIGIBLE PRODUCTION: 0. PRODUCTION AUTHORIZED: NO. This analysis is advisory. No production change is authorized.";

function baseHypothesis(overrides: Partial<ReportHypothesis> = {}): ReportHypothesis {
  return {
    rank: 1,
    hypothesis_id: "HYP-SPATIAL-EDGE",
    family: "SPATIAL",
    detail: "EDGE",
    status: "UNCONFIRMED",
    statement: "Yield loss is associated with wafer-edge location.",
    explanation: "Spatial detector reported SIGNAL on edge dies.",
    why_it_exists: "Composed from supporting detectors: spatial.",
    association_class: "PRIMARY_EVIDENCE",
    evidence_tier: "STRONG_EVIDENCE",
    evidence_score: 0.82,
    score_status: "PRELIMINARY",
    supporting_detectors: ["spatial"],
    conflicting_detectors: [],
    statistical_evidence: [],
    effect_sizes: [],
    affected_population: { grain: "edge", n: 120 },
    data_coverage: { n_eligible: 7842, n_used: 7371, fraction: 0.94 },
    data_gaps: [],
    limitations: ["Associative only."],
    validation_required: ["Review edge-region fail map."],
    validation_steps: ["Examine edge-region failure distribution"],
    validation_recommendation: "INVESTIGATE",
    opportunity_id: "OPP-1",
    observed_loss_rate: 0.084,
    upper_bound_rate: 0.082,
    plausible_rate: null,
    plausible_unavailable: true,
    overlap_count: 0,
    exclusive_count: 120,
    union_count: 120,
    intersection_count: 0,
    not_a_root_cause: true,
    ...overrides,
  };
}

function baseReport(overrides: Partial<EngineeringReport> = {}): EngineeringReport {
  return {
    report_id: "RPT-demo",
    analysis_id: "demo",
    generated_at: "2026-09-24T08:00:00Z",
    dataset_id: "demo",
    fpy_summary: {
      eligible_die_count: 7842,
      first_pass_pass_count: 6462,
      first_pass_fail_count: 1380,
      excluded_count: 12,
      fpy: 0.824,
      fpy_loss: 0.176,
      fpy_policy_version: "yi_fpy_v1",
      abort_policy: "STOP_ON_FAIL",
      policy_notes: ["Retest passes do not count as first-pass passes."],
    },
    loss_summary: {
      primary_failure: [
        {
          attribution_mode: "PRIMARY_FAILURE",
          failure_key: "CONTACT_FAIL",
          family: "CONTACT",
          detail: "PROBE",
          affected_die_count: 428,
          percentage_of_eligible: 0.0546,
          share_of_fails: 0.31,
          selection_rule: "first_fail",
          taxonomy_code: "CONTACT.PROBE",
        },
        {
          attribution_mode: "PRIMARY_FAILURE",
          failure_key: "EDGE_FAIL",
          family: "SPATIAL",
          detail: "EDGE",
          affected_die_count: 290,
          percentage_of_eligible: 0.037,
          share_of_fails: 0.21,
          selection_rule: "first_fail",
          taxonomy_code: "SPATIAL.EDGE",
        },
      ],
      any_fail: [],
      primary_available: true,
      primary_unavailable_note: null,
      modes_not_combined: true,
    },
    evidence_findings: [
      {
        detector: "spatial",
        status: "SIGNAL",
        family: "SPATIAL",
        detail: "EDGE",
        method: "rate_difference",
        effect_size: 0.084,
        effect_size_metric: "fail_rate_difference",
        p_value: 0.001,
        adjusted_p_value: 0.01,
        sample_size: 7371,
        data_gaps: [],
        not_a_root_cause: true,
      },
    ],
    hypotheses: [baseHypothesis()],
    opportunities: [
      {
        opportunity_id: "OPP-1",
        hypothesis_id: "HYP-SPATIAL-EDGE",
        family: "SPATIAL",
        detail: "EDGE",
        attribution_mode: "PRIMARY_FAILURE",
        status: "OBSERVED",
        observed_loss_count: 290,
        observed_loss_rate: 0.037,
        upper_bound_count: 290,
        upper_bound_rate: 0.082,
        plausible_count: null,
        plausible_rate: null,
        plausible_unavailable: true,
        plausible_label: "Not estimable",
        calibration_status: "TO_BE_CALIBRATED",
        affected_population_count: 120,
        population_definition: "edge dies",
        included_in_union: true,
        overlap_count: 0,
        exclusive_count: 120,
        union_count: 120,
        intersection_count: 0,
        statement: "Observed associated loss among edge dies.",
        safety_eligible_production_rate: 0,
      },
    ],
    overlap: {
      sum_of_individual_upper_bounds_rate: 0.082,
      union_upper_bound_rate: 0.082,
      union_upper_bound_count: 290,
      intersection_fail_count: 0,
      sum_exceeds_observed: false,
      note: "Individual opportunities must not be summed when populations overlap.",
      individuals: [],
    },
    no_actionable_recommendation: false,
    investigation_plan: [
      {
        hypothesis_id: "HYP-SPATIAL-EDGE",
        family: "SPATIAL",
        detail: "EDGE",
        recommendation: "INVESTIGATE",
        steps: ["Examine edge-region failure distribution", "Compare affected lots"],
      },
    ],
    data_gaps: { required: [], recommended: [], detector_specific: [], ungrouped: [] },
    limitations: ["Advisory engineering report only."],
    safety_statement: SAFETY,
    near_limit_notice: null,
    sequence_censoring_notice: null,
    no_actionable_notice: null,
    evidence_score_notice: "Evidence score is a preliminary analytical score.",
    overlap_notice: "Individual opportunities must not be summed when populations overlap.",
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production_count: 0,
    safety_eligible_production_rate: 0,
    invoked_agents: [],
    disclaimer: "Advisory engineering report only.",
    pipeline_version: "0.1.0",
    ...overrides,
  };
}

const mlHealthy: MlSnapshot = {
  available: true,
  model_name: "logistic",
  model_version: "yi_ml_v1",
  split_strategy: "leave_one_lot_out",
  evidence_role: "SECONDARY_SUPPORT",
  independence: false,
  metrics: {
    roc_auc: 0.715,
    pr_auc: 0.438,
    brier: 0.17,
    failure_capture_at_top_10_percent: 0.198,
    failure_capture_at_top_20_percent: 0.372,
  },
  calibration: null,
  feature_names: ["edge_distance", "die_x"],
  feature_importance: [
    { feature: "edge_distance", importance: 0.12 },
    { feature: "radial_distance", importance: 0.08 },
  ],
  disclaimer: "ML output is a predictive association for first-pass failure.",
};

const healthHealthy: HealthSnapshot = {
  available: true,
  overall_status: "HEALTHY",
  reduced_ml_evidence: false,
  model_version: "yi_ml_v1",
  dimensions: {
    feature_drift: { dimension: "feature_drift", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
    prediction_drift: { dimension: "prediction_drift", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
    target_drift: { dimension: "target_drift", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
    calibration: { dimension: "calibration", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
    performance: { dimension: "performance", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
    data_quality: { dimension: "data_quality", status: "HEALTHY", availability: "AVAILABLE", notes: "" },
  },
  recommendations: ["CONTINUE_MONITORING"],
  triggers: [],
  disclaimer: "Model health is advisory.",
};

const registry: RegistrySnapshot = {
  available: true,
  active_version: "yi_ml_v1",
  state: "ACTIVE",
  architecture: "logistic_regression",
};

export function dashboardFixture(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    dataset_id: "demo",
    generated_at: "2026-09-24T08:00:00Z",
    report: baseReport(),
    ml: mlHealthy,
    health: healthHealthy,
    registry,
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production_count: 0,
    safety_eligible_production_rate: 0,
    invoked_agents: [],
    safety_statement: SAFETY,
    disclaimer: "Advisory engineering report only.",
    test_catalog: V2_TEST_CATALOG,
    ...overrides,
  };
}

export function noHypothesisFixture(): DashboardResponse {
  return dashboardFixture({
    dataset_id: "s16",
    report: baseReport({
      dataset_id: "s16",
      hypotheses: [],
      investigation_plan: [],
      no_actionable_recommendation: true,
      no_actionable_notice: "No actionable hypothesis identified.",
      evidence_findings: [
        {
          detector: "spatial",
          status: "NO_SIGNAL",
          family: "SPATIAL",
          detail: null,
          method: "rate_difference",
          effect_size: null,
          effect_size_metric: null,
          p_value: null,
          adjusted_p_value: null,
          sample_size: 784,
          data_gaps: [],
          not_a_root_cause: true,
        },
      ],
    }),
  });
}

export function s09Fixture(): DashboardResponse {
  const hyp = baseHypothesis({
    hypothesis_id: "HYP-TEST-LIMIT_SENSITIVITY",
    family: "TEST",
    detail: "LIMIT_SENSITIVITY",
    statement: "Yield loss is associated with measurements concentrating near a test limit.",
    supporting_detectors: ["near_limit"],
  });
  return dashboardFixture({
    dataset_id: "s09",
    report: baseReport({
      dataset_id: "s09",
      hypotheses: [hyp],
      near_limit_notice: "Near-limit evidence requires engineering validation. This system does not recommend or modify test limits.",
    }),
  });
}

export function s15Fixture(): DashboardResponse {
  const edge = baseHypothesis();
  const drift = baseHypothesis({
    rank: 2,
    hypothesis_id: "HYP-PROCESS-DRIFT",
    family: "PROCESS",
    detail: "DRIFT",
    statement: "Yield loss is associated with temporal process drift.",
    supporting_detectors: ["temporal"],
    overlap_count: 40,
  });
  return dashboardFixture({
    dataset_id: "s15",
    report: baseReport({
      dataset_id: "s15",
      hypotheses: [edge, drift],
      opportunities: [
        {
          opportunity_id: "OPP-1",
          hypothesis_id: "HYP-SPATIAL-EDGE",
          family: "SPATIAL",
          detail: "EDGE",
          attribution_mode: "PRIMARY_FAILURE",
          status: "OBSERVED",
          observed_loss_count: 200,
          observed_loss_rate: 0.05,
          upper_bound_count: 200,
          upper_bound_rate: 0.05,
          plausible_count: null,
          plausible_rate: null,
          plausible_unavailable: true,
          plausible_label: "Not estimable",
          calibration_status: "TO_BE_CALIBRATED",
          affected_population_count: 200,
          population_definition: "edge dies",
          included_in_union: true,
          overlap_count: 40,
          exclusive_count: 160,
          union_count: 280,
          intersection_count: 40,
          statement: "Observed associated loss among edge dies.",
          safety_eligible_production_rate: 0,
        },
        {
          opportunity_id: "OPP-2",
          hypothesis_id: "HYP-PROCESS-DRIFT",
          family: "PROCESS",
          detail: "DRIFT",
          attribution_mode: "PRIMARY_FAILURE",
          status: "OBSERVED",
          observed_loss_count: 180,
          observed_loss_rate: 0.04,
          upper_bound_count: 180,
          upper_bound_rate: 0.04,
          plausible_count: null,
          plausible_rate: null,
          plausible_unavailable: true,
          plausible_label: "Not estimable",
          calibration_status: "TO_BE_CALIBRATED",
          affected_population_count: 180,
          population_definition: "late lots",
          included_in_union: true,
          overlap_count: 40,
          exclusive_count: 140,
          union_count: 280,
          intersection_count: 40,
          statement: "Observed associated loss among temporally drifted lots.",
          safety_eligible_production_rate: 0,
        },
      ],
    }),
  });
}

export function missingDataFixture(): DashboardResponse {
  return dashboardFixture({
    report: baseReport({
      fpy_summary: {
        eligible_die_count: 0,
        first_pass_pass_count: 0,
        first_pass_fail_count: 0,
        excluded_count: 10,
        fpy: null,
        fpy_loss: null,
        fpy_policy_version: "yi_fpy_v1",
        abort_policy: "STOP_ON_FAIL",
        policy_notes: [],
      },
      data_gaps: {
        required: ["cannot_calculate_fpy", "missing_x_y"],
        recommended: ["missing_parametric"],
        detector_specific: [],
        ungrouped: [],
      },
      hypotheses: [],
      no_actionable_recommendation: true,
    }),
  });
}

export function mlDegradedFixture(): DashboardResponse {
  return dashboardFixture({
    health: {
      ...healthHealthy,
      overall_status: "DEGRADED",
      reduced_ml_evidence: true,
    },
  });
}

export { baseHypothesis, baseReport };
