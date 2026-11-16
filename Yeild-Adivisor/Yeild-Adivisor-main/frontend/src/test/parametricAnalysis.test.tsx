import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ParametricAnalysisSection } from "../components/ParametricAnalysisSection";
import type { ParametricAnalysisReport } from "../types/api";

const mockReport: ParametricAnalysisReport = {
  dataset_id: "yi_synthetic_v2",
  generated_at: "2026-10-12T12:00:00Z",
  n_parameters_analyzed: 2,
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
      measurement_semantics: "Quiescent supply current",
      spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE",
      synthetic_reference_lower: null,
      synthetic_reference_upper: 40.0,
      spec_disclaimer: "Reference limit",
      target_failure_code: "LEAKAGE_HIGH",
      threshold_status: "INVESTIGATION_CANDIDATE_ONLY",
      missing_evidence: [],
      limitations: [],
      engineering_summary: "IDDQ shows strong separation.",
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
      overall_distribution: { count: 2500, available: true, mean: 25.4, median: 24.1, std: 8.2, min: 5.1, max: 78.4, iqr: 6.3, p05: 12.0, p25: 18.0, p75: 32.0, p95: 50.0 },
      pass_distribution: { count: 2249, available: true, mean: 23.5, median: 23.2, std: 4.1, min: 5.1, max: 37.8, iqr: 5.0, p05: 12.0, p25: 18.0, p75: 28.0, p95: 35.0 },
      fail_distribution: { count: 251, available: true, mean: 42.1, median: 40.5, std: 12.3, min: 18.2, max: 78.4, iqr: 15.2, p05: 22.0, p25: 30.0, p75: 52.0, p95: 70.0 },
      specific_failure_distribution: { count: 48, available: true, mean: 55.3, median: 54.0, std: 8.7, min: 38.2, max: 78.4, iqr: 11.0, p05: 40.0, p25: 48.0, p75: 62.0, p95: 75.0 },
      overall_separation: {
        mean_difference: 31.8,
        pooled_standard_deviation: 6.6,
        cohens_d: 4.82,
        abs_cohens_d: 4.82,
        distribution_overlap_description: "Very low overlap",
        large_effect_size_flag: true,
      },
      specific_failure_separation: null,
      candidate_threshold: {
        candidate_value: 38.03,
        direction: "UPPER_BOUND",
        status: "INVESTIGATION_CANDIDATE_ONLY",
        target_population_description: "LEAKAGE_HIGH",
        target_failure_code: "LEAKAGE_HIGH",
        selection_method: "F1_OPTIMAL",
        selection_objective: "MAX_F1",
        n_dies_flagged: 52,
        flagged_share_of_measured: 0.0208,
        flagged_share_of_all_eligible: 0.0208,
        uncertainty_notes: "Exploratory boundary only.",
        disclaimer: "Non-production boundary",
        training_confusion_matrix: {
          evaluated_population_description: "First-pass valid measurements",
          total_evaluated_count: 2500,
          true_positives: 48,
          false_positives: 4,
          false_negatives: 0,
          true_negatives: 2448,
          sensitivity: 1.0,
          specificity: 0.9984,
          precision: 0.923,
          recall: 1.0,
          youden_j: 0.9984,
        },
      },
      lot_validation: {
        evaluation_strategy: "LEAVE_ONE_LOT_OUT",
        generalization_assessment: "Generalizes across lots except L004 holdout",
        potential_lot_shifts_detected: false,
        performance_warning_lot_ids: [],
        folds: [],
      },
    },
    {
      parameter_name: "VMAX",
      source_field: "VMAX",
      unit: "V",
      measurement_semantics: "Maximum operating voltage",
      spec_provenance: "SYNTHETIC_GENERATOR_REFERENCE",
      synthetic_reference_lower: null,
      synthetic_reference_upper: 1.5,
      spec_disclaimer: "Reference limit",
      target_failure_code: "OVERVOLTAGE_FAIL",
      threshold_status: "NO_THRESHOLD_ESTABLISHED",
      missing_evidence: [],
      limitations: [],
      engineering_summary: "No target failures observed.",
      data_quality: {
        eligible_physical_dies: 2500,
        valid_first_pass_measurements: 2500,
        missing_measurements: 0,
        retest_measurements_excluded: 0,
        quarantined_attempts_count: 0,
        quarantined_dies_count: 0,
        first_pass_pass_count: 2249,
        first_pass_fail_count: 251,
        target_failure_code_count: 0,
        non_target_count: 2500,
        n_lots_covered: 5,
        n_wafers_covered: 5,
        data_quality_warnings: [],
      },
      overall_distribution: { count: 2500, available: true, mean: 1.35, median: 1.35, std: 0.05, min: 1.20, max: 1.50, iqr: 0.06, p05: 1.25, p25: 1.30, p75: 1.40, p95: 1.45 },
      pass_distribution: { count: 2249, available: true, mean: 1.35, median: 1.35, std: 0.05, min: 1.20, max: 1.50, iqr: 0.06, p05: 1.25, p25: 1.30, p75: 1.40, p95: 1.45 },
      fail_distribution: { count: 251, available: true, mean: 1.35, median: 1.35, std: 0.05, min: 1.20, max: 1.50, iqr: 0.06, p05: 1.25, p25: 1.30, p75: 1.40, p95: 1.45 },
      specific_failure_distribution: null,
      overall_separation: {
        mean_difference: 0.0,
        pooled_standard_deviation: 0.05,
        cohens_d: 0.0,
        abs_cohens_d: 0.0,
        distribution_overlap_description: "Full overlap",
        large_effect_size_flag: false,
      },
      specific_failure_separation: null,
      candidate_threshold: null,
      lot_validation: null,
    },
  ],
};

describe("ParametricAnalysisSection", () => {
  it("renders loading state properly", () => {
    render(<ParametricAnalysisSection loading={true} />);
    expect(screen.getByTestId("parametric-loading")).toBeDefined();
  });

  it("renders error state properly", () => {
    render(<ParametricAnalysisSection error="Failed to fetch parametric analysis" />);
    expect(screen.getByTestId("parametric-error")).toBeDefined();
    expect(screen.getByText("Failed to fetch parametric analysis")).toBeDefined();
  });

  it("renders empty state when no report is provided", () => {
    render(<ParametricAnalysisSection report={null} />);
    expect(screen.getByTestId("parametric-empty")).toBeDefined();
  });

  it("renders section header with only the title and removes badges/subtitles/banners", () => {
    render(<ParametricAnalysisSection report={mockReport} />);
    expect(screen.getByText("Parametric Threshold & Distribution Analysis")).toBeDefined();
    expect(screen.queryByText("INVESTIGATION_CANDIDATE_ONLY")).toBeNull();
    expect(screen.queryByText(/Automated empirical boundary exploration/i)).toBeNull();
    expect(screen.queryByTestId("badge-production-action")).toBeNull();
    expect(screen.queryByTestId("badge-production-authorized")).toBeNull();
    expect(screen.queryByTestId("badge-eligible-rate")).toBeNull();
    expect(screen.queryByText(/Engineering Advisory/i)).toBeNull();
  });

  it("renders simplified main parameter table with all parameters and clear statuses", () => {
    render(<ParametricAnalysisSection report={mockReport} />);
    
    // Check IDDQ row
    const iddqRow = screen.getByTestId("param-row-IDDQ");
    expect(iddqRow).toBeDefined();
    expect(iddqRow.textContent).toContain("IDDQ (uA)");
    expect(iddqRow.textContent).toContain("LEAKAGE_HIGH");
    expect(iddqRow.textContent).toContain("48 dies");
    expect(iddqRow.textContent).toContain("> 38.03 uA");
    expect(iddqRow.textContent).toContain("Investigate");

    // Check VMAX row
    const vmaxRow = screen.getByTestId("param-row-VMAX");
    expect(vmaxRow).toBeDefined();
    expect(vmaxRow.textContent).toContain("VMAX (V)");
    expect(vmaxRow.textContent).toContain("OVERVOLTAGE_FAIL");
    expect(vmaxRow.textContent).toContain("0 dies");
    expect(vmaxRow.textContent).toContain("No reliable candidate boundary identified.");
    expect(vmaxRow.textContent).toContain("More evidence needed");

    // Ensure removed columns are NOT in the table
    expect(screen.queryByText(/Effect Size/i)).toBeNull();
    expect(screen.queryByText(/Measured \/ Pop/i)).toBeNull();
    expect(screen.queryByText(/Cohen's d/i)).toBeNull();
  });

  it("renders simplified parameter detail view keeping only the 5 required elements", () => {
    render(<ParametricAnalysisSection report={mockReport} />);
    
    const detailSection = screen.getByTestId("param-detail-section");
    expect(detailSection).toBeDefined();

    // 1. Parameter name and unit
    expect(screen.getByTestId("selected-param-title").textContent).toBe("IDDQ (uA)");

    // 2. Candidate boundary (including direction and unit)
    expect(screen.getByTestId("detail-candidate-callout").textContent).toBe("> 38.03 uA");

    // 3. Passing-die statistics: mean, median, min, max
    expect(screen.getByTestId("pass-mean").textContent).toBe("23.5 uA");
    expect(screen.getByTestId("pass-median").textContent).toBe("23.2 uA");
    expect(screen.getByTestId("pass-min").textContent).toBe("5.1 uA");
    expect(screen.getByTestId("pass-max").textContent).toBe("37.8 uA");

    // 4. Boundary comparison (one short concise sentence)
    // 38.03 > 37.8 max -> above all observed passing measurements
    expect(screen.getByTestId("boundary-comparison-text").textContent).toBe(
      "The candidate boundary is above all observed passing measurements."
    );

    // 5. Recommended next steps (no more than 3 concise actions)
    const stepsCard = screen.getByTestId("recommended-steps-card");
    const stepItems = stepsCard.querySelectorAll("li");
    expect(stepItems.length).toBeLessThanOrEqual(3);
    expect(stepItems.length).toBeGreaterThan(0);
    expect(stepsCard.textContent).toContain("Verify test setup, probe card contact integrity");

    // Verify unnecessary warnings and panels were REMOVED from the detail view
    expect(detailSection.textContent).not.toContain("Investigation only");
    expect(detailSection.textContent).not.toContain("Do not change production limits");
    expect(detailSection.textContent).not.toContain("Production Limit Policy");
    expect(detailSection.textContent).not.toContain("Safety & Specification Governance");
    expect(detailSection.textContent).not.toContain("Engineering Interpretation");
  });

  it("displays dynamic boundary comparison when candidate boundary is within range", () => {
    // Test boundary inside range: candidate 30.0 uA with passing min 5.1 and max 37.8
    const reportWithInsideBoundary: ParametricAnalysisReport = {
      ...mockReport,
      results: [
        {
          ...mockReport.results[0],
          candidate_threshold: {
            ...mockReport.results[0].candidate_threshold!,
            candidate_value: 30.0,
          },
        },
      ],
    };

    render(<ParametricAnalysisSection report={reportWithInsideBoundary} />);
    expect(screen.getByTestId("boundary-comparison-text").textContent).toBe(
      "The candidate boundary falls within the observed passing-die range."
    );
  });

  it("displays dynamic boundary comparison when candidate boundary is below minimum", () => {
    // Test boundary below range: candidate 4.0 uA with passing min 5.1
    const reportWithBelowBoundary: ParametricAnalysisReport = {
      ...mockReport,
      results: [
        {
          ...mockReport.results[0],
          candidate_threshold: {
            ...mockReport.results[0].candidate_threshold!,
            candidate_value: 4.0,
          },
        },
      ],
    };

    render(<ParametricAnalysisSection report={reportWithBelowBoundary} />);
    expect(screen.getByTestId("boundary-comparison-text").textContent).toBe(
      "The candidate boundary is below all observed passing measurements."
    );
  });

  it("updates detail view when another parameter without candidate is inspected", () => {
    render(<ParametricAnalysisSection report={mockReport} />);

    // Click on VMAX row
    fireEvent.click(screen.getByTestId("param-row-VMAX"));

    expect(screen.getByTestId("selected-param-title").textContent).toBe("VMAX (V)");
    expect(screen.getByTestId("candidate-boundary-card").textContent).toContain(
      "No reliable candidate boundary identified."
    );
    expect(screen.getByTestId("boundary-comparison-text").textContent).toBe(
      "No candidate boundary identified to compare against passing distribution."
    );
  });

  it("completely removes LOO validation section and confusion matrix from the UI", () => {
    render(<ParametricAnalysisSection report={mockReport} />);

    // Check LOO section removed
    expect(screen.queryByTestId("loo-section")).toBeNull();
    expect(screen.queryByTestId("loo-table")).toBeNull();
    expect(screen.queryByText(/Leave-One-Lot-Out/i)).toBeNull();
    expect(screen.queryByText(/Generalization Validation/i)).toBeNull();
    expect(screen.queryByText(/Held-Out Lot/i)).toBeNull();

    // Check Confusion Matrix removed
    expect(screen.queryByTestId("confusion-matrix-box")).toBeNull();
    expect(screen.queryByTestId("cm-tp")).toBeNull();
    expect(screen.queryByTestId("cm-fp")).toBeNull();
    expect(screen.queryByTestId("cm-fn")).toBeNull();
    expect(screen.queryByTestId("cm-tn")).toBeNull();
    expect(screen.queryByText(/Confusion Matrix/i)).toBeNull();
    expect(screen.queryByText(/Sensitivity/i)).toBeNull();
    expect(screen.queryByText(/Specificity/i)).toBeNull();
  });
});
