import { describe, expect, it } from "vitest";
import {
  generateDieRecommendation,
  evaluateBoundaryCrossing,
  FAILURE_CODE_TO_PARAMETER,
} from "../services/dieRecommendation";
import type { ParametricAnalysisReport, WaferMapDie } from "../types/api";

const mockParametricReport: ParametricAnalysisReport = {
  dataset_id: "yi_synthetic_v2",
  generated_at: "2026-10-12T12:00:00Z",
  n_parameters_analyzed: 3,
  quarantined_attempts_count: 0,
  extraction_warnings: [],
  production_action: "FORBIDDEN",
  production_authorized: false,
  safety_eligible_production_rate: 0,
  safety_invariants: {
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production: 0,
  },
  results: [
    {
      parameter_name: "IDDQ",
      source_field: "IDDQ",
      unit: "uA",
      measurement_semantics: "Quiescent supply current leakage",
      spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE",
      synthetic_reference_lower: null,
      synthetic_reference_upper: 50.0,
      spec_disclaimer: "Non-production reference",
      target_failure_code: "IDDQ",
      threshold_status: "INVESTIGATION_CANDIDATE_ONLY",
      missing_evidence: [],
      limitations: [],
      engineering_summary: "Strong separation",
      data_quality: {
        eligible_physical_dies: 2500,
        valid_first_pass_measurements: 2500,
        missing_measurements: 0,
        retest_measurements_excluded: 0,
        quarantined_attempts_count: 0,
        quarantined_dies_count: 0,
        first_pass_pass_count: 2249,
        first_pass_fail_count: 251,
        target_failure_code_count: 48,
        non_target_count: 2452,
        n_lots_covered: 5,
        n_wafers_covered: 5,
        data_quality_warnings: [],
      },
      overall_distribution: { count: 2500, available: true, mean: 25.4, median: 24.1, std: 8.2, min: 5.1, max: 78.4, iqr: 6.3, p05: null, p25: null, p75: null, p95: null },
      pass_distribution: { count: 2249, available: true, mean: 23.5, median: 23.2, std: 4.1, min: 5.1, max: 37.8, iqr: 5.0, p05: null, p25: null, p75: null, p95: null },
      fail_distribution: { count: 251, available: true, mean: 42.1, median: 40.5, std: 12.3, min: 18.2, max: 78.4, iqr: 15.2, p05: null, p25: null, p75: null, p95: null },
      specific_failure_distribution: null,
      overall_separation: { mean_difference: 31.8, pooled_standard_deviation: 6.6, cohens_d: 4.82, abs_cohens_d: 4.82, distribution_overlap_description: "Low", large_effect_size_flag: true },
      specific_failure_separation: null,
      candidate_threshold: {
        candidate_value: 48.61,
        direction: "UPPER_BOUND",
        status: "INVESTIGATION_CANDIDATE_ONLY",
        target_population_description: "IDDQ",
        target_failure_code: "IDDQ",
        selection_method: "F1_OPTIMAL",
        selection_objective: "MAX_F1",
        n_dies_flagged: 52,
        flagged_share_of_measured: 0.02,
        flagged_share_of_all_eligible: 0.02,
        uncertainty_notes: "Exploratory boundary only.",
        disclaimer: "Non-production boundary",
        training_confusion_matrix: {
          evaluated_population_description: "All valid",
          total_evaluated_count: 2500,
          true_positives: 48,
          false_positives: 4,
          false_negatives: 0,
          true_negatives: 2448,
          sensitivity: 1.0,
          specificity: 0.998,
          precision: 0.92,
          recall: 1.0,
          youden_j: 0.998,
        },
      },
      lot_validation: null,
    },
    {
      parameter_name: "VMIN",
      source_field: "VMIN",
      unit: "V",
      measurement_semantics: "Minimum operating voltage",
      spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE",
      synthetic_reference_lower: null,
      synthetic_reference_upper: 0.85,
      spec_disclaimer: "Non-production reference",
      target_failure_code: "VMIN",
      threshold_status: "INVESTIGATION_CANDIDATE_ONLY",
      missing_evidence: [],
      limitations: [],
      engineering_summary: "High VMIN",
      data_quality: {
        eligible_physical_dies: 2500,
        valid_first_pass_measurements: 2500,
        missing_measurements: 0,
        retest_measurements_excluded: 0,
        quarantined_attempts_count: 0,
        quarantined_dies_count: 0,
        first_pass_pass_count: 2249,
        first_pass_fail_count: 251,
        target_failure_code_count: 53,
        non_target_count: 2447,
        n_lots_covered: 5,
        n_wafers_covered: 5,
        data_quality_warnings: [],
      },
      overall_distribution: { count: 2500, available: true, mean: 0.65, median: 0.65, std: 0.05, min: 0.50, max: 0.95, iqr: 0.05, p05: null, p25: null, p75: null, p95: null },
      pass_distribution: { count: 2249, available: true, mean: 0.64, median: 0.64, std: 0.03, min: 0.50, max: 0.75, iqr: 0.04, p05: null, p25: null, p75: null, p95: null },
      fail_distribution: { count: 251, available: true, mean: 0.82, median: 0.82, std: 0.08, min: 0.60, max: 0.95, iqr: 0.08, p05: null, p25: null, p75: null, p95: null },
      specific_failure_distribution: null,
      overall_separation: { mean_difference: 0.18, pooled_standard_deviation: 0.04, cohens_d: 3.5, abs_cohens_d: 3.5, distribution_overlap_description: "Low", large_effect_size_flag: true },
      specific_failure_separation: null,
      candidate_threshold: {
        candidate_value: 0.784,
        direction: "UPPER_BOUND",
        status: "INVESTIGATION_CANDIDATE_ONLY",
        target_population_description: "VMIN",
        target_failure_code: "VMIN",
        selection_method: "F1_OPTIMAL",
        selection_objective: "MAX_F1",
        n_dies_flagged: 55,
        flagged_share_of_measured: 0.022,
        flagged_share_of_all_eligible: 0.022,
        uncertainty_notes: "Exploratory boundary only.",
        disclaimer: "Non-production boundary",
        training_confusion_matrix: {
          evaluated_population_description: "All valid",
          total_evaluated_count: 2500,
          true_positives: 50,
          false_positives: 5,
          false_negatives: 3,
          true_negatives: 2442,
          sensitivity: 0.943,
          specificity: 0.998,
          precision: 0.909,
          recall: 0.943,
          youden_j: 0.941,
        },
      },
      lot_validation: null,
    },
    {
      parameter_name: "VMAX",
      source_field: "VMAX",
      unit: "V",
      measurement_semantics: "Maximum operating voltage",
      spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE",
      synthetic_reference_lower: 1.05,
      synthetic_reference_upper: null,
      spec_disclaimer: "Non-production reference",
      target_failure_code: "VMAX",
      threshold_status: "INSUFFICIENT_EVIDENCE",
      missing_evidence: ["Distribution overlap too high"],
      limitations: [],
      engineering_summary: "No candidate established",
      data_quality: {
        eligible_physical_dies: 2500,
        valid_first_pass_measurements: 2500,
        missing_measurements: 0,
        retest_measurements_excluded: 0,
        quarantined_attempts_count: 0,
        quarantined_dies_count: 0,
        first_pass_pass_count: 2249,
        first_pass_fail_count: 251,
        target_failure_code_count: 22,
        non_target_count: 2478,
        n_lots_covered: 5,
        n_wafers_covered: 5,
        data_quality_warnings: [],
      },
      overall_distribution: { count: 2500, available: true, mean: 1.25, median: 1.25, std: 0.05, min: 1.0, max: 1.4, iqr: 0.05, p05: null, p25: null, p75: null, p95: null },
      pass_distribution: { count: 2249, available: true, mean: 1.25, median: 1.25, std: 0.05, min: 1.0, max: 1.4, iqr: 0.05, p05: null, p25: null, p75: null, p95: null },
      fail_distribution: { count: 251, available: true, mean: 1.25, median: 1.25, std: 0.05, min: 1.0, max: 1.4, iqr: 0.05, p05: null, p25: null, p75: null, p95: null },
      specific_failure_distribution: null,
      overall_separation: null,
      specific_failure_separation: null,
      candidate_threshold: null,
      lot_validation: null,
    },
  ],
};

describe("dieRecommendation service", () => {
  it("1. IDDQ failure with a valid candidate boundary evaluates signed distance and crossing", () => {
    const iddqDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D066",
      x: 6,
      y: 7,
      first_pass_result: "FAIL",
      failed_test_id: "T005",
      failure_code: "IDDQ",
      is_first_fail: true,
      retest_available: false,
      measurements: {
        IDDQ: 50.2034,
        VMIN: 0.5925,
      },
    };

    const rec = generateDieRecommendation(iddqDie, mockParametricReport);
    expect(rec).not.toBeNull();
    expect(rec?.status).toBe("ACTIONABLE_CANDIDATE_COMPARISON");
    expect(rec?.parameter_name).toBe("IDDQ");
    expect(rec?.primary_failure_code).toBe("IDDQ");
    expect(rec?.actual_measured_value).toBe(50.2034);
    expect(rec?.candidate_boundary).toBe(48.61);
    expect(rec?.candidate_direction).toBe("UPPER_BOUND");
    expect(rec?.signed_difference).toBeCloseTo(1.5934, 4);
    expect(rec?.exceeds_candidate_boundary).toBe(true);
    expect(rec?.safety_banner).toBe("INVESTIGATION ONLY — PRODUCTION ACTION FORBIDDEN");
    expect(rec?.approved_production_limit_status).toContain("Unavailable — authoritative specification not provided");
    expect(rec?.recommended_investigation_steps.length).toBeGreaterThan(0);
  });

  it("2. VMIN failure with correct upper-bound comparison", () => {
    const vminDie: WaferMapDie = {
      lot_id: "L004",
      wafer_id: "W01",
      die_id: "D012",
      x: 2,
      y: 2,
      first_pass_result: "FAIL",
      failed_test_id: "T006",
      failure_code: "VMIN",
      is_first_fail: true,
      retest_available: false,
      measurements: {
        VMIN: 0.825,
      },
    };

    const rec = generateDieRecommendation(vminDie, mockParametricReport);
    expect(rec?.status).toBe("ACTIONABLE_CANDIDATE_COMPARISON");
    expect(rec?.parameter_name).toBe("VMIN");
    expect(rec?.actual_measured_value).toBe(0.825);
    expect(rec?.candidate_boundary).toBe(0.784);
    expect(rec?.signed_difference).toBeCloseTo(0.041, 4);
    expect(rec?.exceeds_candidate_boundary).toBe(true);
  });

  it("3. Correct lower-bound comparison behavior", () => {
    expect(evaluateBoundaryCrossing(0.95, 1.05, "LOWER_BOUND")).toBe(true); // 0.95 < 1.05 -> exceeds lower bound
    expect(evaluateBoundaryCrossing(1.10, 1.05, "LOWER_BOUND")).toBe(false); // 1.10 not < 1.05 -> within bound
  });

  it("4. VMAX or parameter with no candidate returns INSUFFICIENT_EVIDENCE", () => {
    const vmaxDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D065",
      x: 5,
      y: 7,
      first_pass_result: "FAIL",
      failed_test_id: "T007",
      failure_code: "VMAX",
      is_first_fail: true,
      retest_available: false,
      measurements: {
        VMAX: 1.02,
      },
    };

    const rec = generateDieRecommendation(vmaxDie, mockParametricReport);
    expect(rec?.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(rec?.parameter_name).toBe("VMAX");
    expect(rec?.actual_measured_value).toBe(1.02);
    expect(rec?.candidate_boundary).toBeNull();
    expect(rec?.missing_evidence).toContain("No established candidate threshold for parameter 'VMAX'.");
  });

  it("5. Missing measurement fails closed with MISSING_MEASUREMENT", () => {
    const missingDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D099",
      x: 9,
      y: 10,
      first_pass_result: "FAIL",
      failed_test_id: "T005",
      failure_code: "IDDQ",
      is_first_fail: true,
      retest_available: false,
      measurements: {
        // IDDQ omitted or null
        IDDQ: null,
      },
    };

    const rec = generateDieRecommendation(missingDie, mockParametricReport);
    expect(rec?.status).toBe("MISSING_MEASUREMENT");
    expect(rec?.actual_measured_value).toBeNull();
    expect(rec?.missing_evidence.length).toBeGreaterThan(0);
    expect(rec?.missing_evidence[0]).toContain("Die D099 has no valid measurement recorded");
  });

  it("6. Unmapped failure code such as CONTINUITY returns NON_PARAMETRIC_FAILURE", () => {
    const contDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D049",
      x: 9,
      y: 5,
      first_pass_result: "FAIL",
      failed_test_id: "T001",
      failure_code: "CONTINUITY",
      is_first_fail: true,
      retest_available: true,
      measurements: {
        IDDQ: 24.5,
      },
    };

    const rec = generateDieRecommendation(contDie, mockParametricReport);
    expect(rec?.status).toBe("NON_PARAMETRIC_FAILURE");
    expect(rec?.parameter_name).toBeNull();
    expect(rec?.primary_failure_code).toBe("CONTINUITY");
    expect(rec?.recommended_investigation_steps[0]).toContain("CONTINUITY");
  });

  it("7. Missing or ambiguous failure mapping handled safely", () => {
    const unkDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D003",
      x: 3,
      y: 1,
      first_pass_result: "FAIL",
      failed_test_id: "T999",
      failure_code: null,
      is_first_fail: true,
      retest_available: false,
      measurements: {},
    };

    const rec = generateDieRecommendation(unkDie, mockParametricReport);
    expect(rec?.status).toBe("NON_PARAMETRIC_FAILURE");
    expect(rec?.actual_measured_value).toBeNull();
  });

  it("8. Missing authoritative production specification is explicitly declared", () => {
    const iddqDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D066",
      x: 6,
      y: 7,
      first_pass_result: "FAIL",
      failed_test_id: "T005",
      failure_code: "IDDQ",
      is_first_fail: true,
      retest_available: false,
      measurements: { IDDQ: 50.2 },
    };

    const rec = generateDieRecommendation(iddqDie, mockParametricReport);
    expect(rec?.approved_production_limit_status).toBe(
      "Approved production limit: Unavailable — authoritative specification not provided."
    );
  });

  it("9. Passing die returns PASSING_DIE status with no failure recommendation", () => {
    const passDie: WaferMapDie = {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D002",
      x: 2,
      y: 1,
      first_pass_result: "PASS",
      failed_test_id: null,
      failure_code: null,
      is_first_fail: null,
      retest_available: false,
      measurements: { IDDQ: 22.1 },
    };

    const rec = generateDieRecommendation(passDie, mockParametricReport);
    expect(rec?.status).toBe("PASSING_DIE");
    expect(rec?.actual_measured_value).toBeNull();
  });
});
