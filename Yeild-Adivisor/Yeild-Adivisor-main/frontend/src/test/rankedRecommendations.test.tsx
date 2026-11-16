import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RankedRecommendations } from "../components/RankedRecommendations";
import type { RecommendationBundle } from "../types/api";

const mockBundle: RecommendationBundle = {
  dataset_id: "yi_synthetic_v2",
  recommendation_count: 1,
  ranking_policy: "Evidence-First Engineering Priority Policy",
  ranking_version: "yi_rec_rank_v1",
  evidence_limitations_summary: [],
  ml_evidence_status: "NEEDS_MORE_DATA",
  ml_evidence_summary: "Exploratory signal only.",
  safety_invariants: {
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production: 0,
  },
  production_action: "FORBIDDEN",
  production_authorized: false,
  safety_eligible_production_rate: 0,
  disclaimer: "Advisory only.",
  recommendations: [
    {
      recommendation_id: "REC-PROCESS.LOT_VARIATION",
      hypothesis_id: "H-PROCESS.LOT_VARIATION",
      title: "Investigate Lot investigation: L004 Systematic Loss Pattern",
      recommendation_category: "Lot investigation",
      status: "PROPOSED",
      scope: "LOT_SPECIFIC",
      lot_id: "L004",
      priority_rank: 1,
      priority_tier: "HIGH",
      confidence_tier: "HIGH",
      ranking_score: 0.85,
      ranking_rationale: "Primary evidence association",
      observed_pattern: "Elevated failure rate in L004",
      target_population: "PROCESS L004",
      affected_die_count: 97,
      eligible_die_count: 2500,
      subgroup_die_count: 500,
      subgroup_failed_die_count: 97,
      observed_failure_rate: 0.194,
      baseline_failure_rate: 0.1004,
      supporting_detectors: ["lot", "wafer"],
      hypothesis_confidence: "MODERATE_EVIDENCE",
      ml_evidence_status: "NEEDS_MORE_DATA",
      ml_evidence_notes: "Exploratory signal only.",
      missing_evidence: [],
      limitations: [],
      summary: "First-pass testing shows elevated failure concentration in PROCESS L004 (19.4% vs 7.7% lot_excluded).",
      observed_facts: [
        "97 of 500 first-pass dies failed in PROCESS L004 (19.4% failure rate).",
        "Comparison baseline recorded 154 of 2,000 failures (7.7% failure rate).",
        "Observed rate difference: +11.7 percentage points relative to baseline.",
      ],
      evidence_strength: "STRONG",
      validation_status: "STATISTICAL_SIGNAL_VALIDATED",
      uncertainties: ["Statistical association does not establish physical causation."],
      data_gaps: ["Upstream MES chamber run parameters are unjoined."],
      recommended_next_steps: [
        "Audit Data Quality: Verify referential integrity for L004.",
        "Controlled Comparison: Stratify failure Pareto.",
      ],
      supporting_evidence: [
        {
          evidence_type: "FIRST_PASS_SUBGROUP_MEASUREMENT",
          evidence_classification: "OBSERVED_FACT",
          source_dataset: "yi_synthetic_v2",
          source_artifact: "die_attempts / report.fpy_summary",
          entity_scope: "PROCESS L004",
          numerator: 97,
          denominator: 500,
          observed_value: 0.194,
          baseline_value: 0.077,
          comparison_baseline: "Lot-excluded baseline: 154 / 2,000 dies (7.7%)",
          unit: "dies",
          time_scope: "FIRST_PASS",
          validation_state: "MEASURED_FIRST_PASS",
          limitations: ["Physical first-pass count. Retest attempts excluded."],
        },
      ],
      recommended_action: "Compare upstream chamber processing history for L004.",
      reason: "L004 exhibits 19.4% fail rate vs 10.0% baseline.",
      expected_information: "Identify chamber discrepancy.",
      validation_method: "Cross-stratify tool IDs.",
      success_criteria: "Chamber link identified.",
      required_data: ["MES logs"],
      risk_if_ignored: "Future lots may degrade.",
      next_step_if_confirmed: "Schedule chamber PM.",
      next_step_if_rejected: "Check incoming material.",
      observed_loss_rate: 0.0388,
      upper_bound_rate: 0.0388,
      upper_bound_count: 97,
      plausible_rate: 0.0232,
      plausible_count: 58,
      safety_eligible_production_rate: 0,
      opportunity_disclaimer: "Non-additive upper bound.",
      production_action: "FORBIDDEN",
      production_authorized: false,
      not_a_root_cause: true,
      safety_statement: "PRODUCTION ACTION: FORBIDDEN.",
      validation_protocol: {
        protocol_id: "PROTO-REC-PROCESS.LOT_VARIATION",
        target_hypothesis: "H-PROCESS.LOT_VARIATION",
        replication_check: "Check 3 subsequent lots",
        downstream_reliability_risk: "No risk",
        disclaimer: "Advisory protocol",
        steps: [
          {
            step_number: 1,
            step_id: "S1",
            title: "Audit Data Quality",
            investigation_action: "Verify physical die coordinates.",
            required_evidence: "die_attempts table",
            expected_measurement: "100% integrity",
            acceptance_criteria: "No missing coordinates",
            rejection_criteria: "Corrupted records",
            limitations_and_safety: "Advisory only",
          },
        ],
      },
    },
  ],
};

const multiLotBundle: RecommendationBundle = {
  ...mockBundle,
  recommendation_count: 3,
  recommendations: [
    mockBundle.recommendations[0],
    {
      ...mockBundle.recommendations[0],
      recommendation_id: "REC-PROCESS.L002_SPECIFIC",
      title: "Investigate L002 Specific Pattern",
      scope: "LOT_SPECIFIC",
      lot_id: "L002",
      target_population: "PROCESS L002",
      observed_pattern: "Thermal drift on L002",
      recommended_action: "Inspect heater block for L002.",
    },
    {
      ...mockBundle.recommendations[0],
      recommendation_id: "REC-SPATIAL.GLOBAL_BORDER",
      title: "Review Edge Ring Spatial Loss",
      scope: "GLOBAL",
      lot_id: null,
      target_population: "BORDER",
      observed_pattern: "Product-wide edge loss",
      recommended_action: "Inspect edge exclusion ring.",
    },
  ],
};

describe("RankedRecommendations Component", () => {
  it("renders scope selector with All, Global, and Lot-Level tabs", () => {
    render(<RankedRecommendations bundle={multiLotBundle} datasetId="yi_synthetic_v2" selectedLotId="L004" />);

    expect(screen.getByText("Engineering Recommendations")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /All/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Global/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Lot-Level/i })).toBeInTheDocument();
  });

  it("filters recommendations when switching between Global, Lot-Level, and All scopes", () => {
    render(<RankedRecommendations bundle={multiLotBundle} datasetId="yi_synthetic_v2" selectedLotId="L004" />);

    // Initially "All" is active for L004: both L004 and Global are visible
    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.getByText("Review Edge Ring Spatial Loss")).toBeInTheDocument();
    expect(screen.queryByText("Investigate L002 Specific Pattern")).not.toBeInTheDocument();

    // Click "Global" scope:
    fireEvent.click(screen.getByRole("tab", { name: /Global/i }));
    expect(screen.getByText("Review Edge Ring Spatial Loss")).toBeInTheDocument();
    expect(screen.queryByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).not.toBeInTheDocument();

    // Click "Lot-Level" scope:
    fireEvent.click(screen.getByRole("tab", { name: /Lot-Level/i }));
    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.queryByText("Review Edge Ring Spatial Loss")).not.toBeInTheDocument();

    // Click "All" scope:
    fireEvent.click(screen.getByRole("tab", { name: /All/i }));
    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.getByText("Review Edge Ring Spatial Loss")).toBeInTheDocument();
  });

  it("allows choosing Global vs Lot-Level recommendations when All Lots is selected", () => {
    render(<RankedRecommendations bundle={multiLotBundle} datasetId="yi_synthetic_v2" selectedLotId="" />);

    expect(screen.getByText("Engineering Recommendations")).toBeInTheDocument();

    // On All Lots, Global is selected by default:
    expect(screen.getByText("Review Edge Ring Spatial Loss")).toBeInTheDocument();
    expect(screen.queryByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).not.toBeInTheDocument();

    // When switching to Lot-Level on All Lots:
    fireEvent.click(screen.getByRole("tab", { name: /Lot-Level/i }));
    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.getByText("Investigate L002 Specific Pattern")).toBeInTheDocument();
    expect(screen.queryByText("Review Edge Ring Spatial Loss")).not.toBeInTheDocument();
  });

  it("renders recommendation card with title, priority, metrics, and next action", () => {
    render(<RankedRecommendations bundle={mockBundle} datasetId="yi_synthetic_v2" selectedLotId="L004" />);

    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText(/Priority: HIGH/i)).toBeInTheDocument();
    expect(screen.getByText(/Confidence: HIGH/i)).toBeInTheDocument();
    expect(screen.getAllByText(/PROCESS L004/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Affected Dies \(Overall\):/i)).toBeInTheDocument();
    expect(screen.getByText(/97 \/ 2,500 dies/i)).toBeInTheDocument();
    expect(screen.getByText(/Subgroup Failure Rate:/i)).toBeInTheDocument();
    expect(screen.getAllByText(/19.4%/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/97 \/ 500 dies/i)).toBeInTheDocument();
    expect(screen.getByText("Recommended Next Action")).toBeInTheDocument();
    expect(screen.getByText("Compare upstream chamber processing history for L004.")).toBeInTheDocument();
  });

  it("renders traceability sections: finding summary, observed facts, and expandable evidence quality", () => {
    render(<RankedRecommendations bundle={mockBundle} datasetId="yi_synthetic_v2" selectedLotId="L004" />);

    // Finding Summary
    expect(screen.getByText(/First-pass testing shows elevated failure concentration in PROCESS L004/i)).toBeInTheDocument();

    // Strength Badge
    expect(screen.getByText(/Strength: STRONG/i)).toBeInTheDocument();

    // Key Observed Facts
    expect(screen.getByText("Key Observed Facts:")).toBeInTheDocument();
    expect(screen.getByText(/97 of 500 first-pass dies failed in PROCESS L004/i)).toBeInTheDocument();
    expect(screen.getByText(/Comparison baseline recorded 154 of 2,000 failures/i)).toBeInTheDocument();

    // Expandable Evidence Quality & Traceability
    expect(screen.getByText(/Evidence Quality & Traceability/i)).toBeInTheDocument();
    expect(screen.getByText(/STATISTICAL_SIGNAL_VALIDATED/i)).toBeInTheDocument();
    expect(screen.getByText("Supporting Evidence Traceability:")).toBeInTheDocument();
    expect(screen.getByText("Uncertainties:")).toBeInTheDocument();
    expect(screen.getByText("Data Gaps:")).toBeInTheDocument();
    expect(screen.getByText(/Statistical association does not establish physical causation/i)).toBeInTheDocument();
    expect(screen.getByText(/Upstream MES chamber run parameters are unjoined/i)).toBeInTheDocument();

    // Recommended Next Action with advisory badge
    expect(screen.getByText("Recommended Next Action")).toBeInTheDocument();
    expect(screen.getByText(/Advisory suggestion — production action forbidden/i)).toBeInTheDocument();
  });

  it("handles recommendations with missing optional traceability fields gracefully without crashing", () => {
    const sparseBundle: RecommendationBundle = {
      ...mockBundle,
      recommendations: [
        {
          ...mockBundle.recommendations[0],
          recommendation_id: "REC-SPARSE",
          summary: undefined,
          observed_facts: undefined,
          supporting_evidence: undefined,
          evidence_strength: undefined,
          uncertainties: undefined,
          data_gaps: undefined,
          recommended_next_steps: undefined,
          validation_status: undefined,
        },
      ],
    };

    render(<RankedRecommendations bundle={sparseBundle} datasetId="yi_synthetic_v2" selectedLotId="L004" />);
    expect(screen.getByText("Investigate Lot investigation: L004 Systematic Loss Pattern")).toBeInTheDocument();
    expect(screen.getByText("Recommended Next Action")).toBeInTheDocument();
  });
});
