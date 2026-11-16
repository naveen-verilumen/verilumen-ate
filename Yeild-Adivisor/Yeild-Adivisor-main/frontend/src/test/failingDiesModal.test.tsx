import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FailingDiesModal } from "../components/FailingDiesModal";
import { RankedRecommendations } from "../components/RankedRecommendations";
import type { EngineeringRecommendation, RecommendationBundle, RecommendationFailingDiesResponse } from "../types/api";
import * as api from "../services/yieldImprovementApi";

const mockFailingDiesResponse: RecommendationFailingDiesResponse = {
  dataset_id: "yi_synthetic_v2",
  recommendation_id: "REC-TEST.LIMIT_SENSITIVITY",
  lot_id: "L001",
  title: "Investigate Near-limit investigation: TEST near_vs_far Systematic Loss Pattern",
  target_population: "TEST near_vs_far",
  recommendation_category: "Near-limit investigation",
  subgroup_definition: "Physical dies with first-pass parametric measurements within 5.0% of test limits",
  counts: {
    subgroup_failing_dies: 59,
    subgroup_eligible_dies: 277,
    subgroup_failure_rate: 0.213,
    lot_id: "L001",
    lot_display: "LOT 001",
    lot_failing_dies: 97,
    lot_eligible_dies: 500,
    lot_failure_rate: 0.194,
    dataset_failing_dies: 251,
    dataset_eligible_dies: 2500,
    dataset_failure_rate: 0.1004,
    subgroup_failing_measurements: 67,
    subgroup_eligible_measurements: 299,
  },
  failing_dies_count: 2,
  failing_dies: [
    {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D066",
      x: 6,
      y: 7,
      first_pass_result: "FAIL",
      primary_failure_code: "IDDQ",
      failed_test_ids: ["T005"],
      relevant_measurements: [
        {
          parameter_name: "IDDQ",
          value: 50.2034,
          unit: "uA",
          lower_limit: null,
          upper_limit: 50.0,
          near_limit: true,
          proximity_ratio: 0.0041,
        },
      ],
    },
    {
      lot_id: "L001",
      wafer_id: "W02",
      die_id: "D042",
      x: 3,
      y: 4,
      first_pass_result: "FAIL",
      primary_failure_code: "VMIN",
      failed_test_ids: ["T012"],
      relevant_measurements: [
        {
          parameter_name: "VMIN",
          value: 0.81,
          unit: "V",
          lower_limit: null,
          upper_limit: 0.80,
          near_limit: true,
          proximity_ratio: 0.0125,
        },
      ],
    },
  ],
  production_action: "FORBIDDEN",
  production_authorized: false,
  safety_statement: "Investigation only — production action forbidden.",
  disclaimer: "Advisory only.",
};

const mockRec: EngineeringRecommendation = {
  recommendation_id: "REC-TEST.LIMIT_SENSITIVITY",
  title: "Investigate Near-limit investigation: TEST near_vs_far Systematic Loss Pattern",
  recommendation_category: "Near-limit investigation",
  status: "PROPOSED",
  scope: "LOT_SPECIFIC",
  lot_id: "L001",
  priority_rank: 1,
  priority_tier: "HIGH",
  confidence_tier: "HIGH",
  ranking_score: 0.88,
  ranking_rationale: "Near limit sensitivity",
  observed_pattern: "Concentrated failures near limits",
  target_population: "TEST near_vs_far",
  affected_die_count: 67,
  eligible_die_count: 2500,
  subgroup_die_count: 299,
  subgroup_failed_die_count: 67,
  observed_failure_rate: 0.224,
  baseline_failure_rate: 0.1004,
  supporting_detectors: ["near_limit"],
  hypothesis_confidence: "STRONG_EVIDENCE",
  ml_evidence_status: "NEEDS_MORE_DATA",
  ml_evidence_notes: "Exploratory signal only.",
  missing_evidence: [],
  limitations: [],
  recommended_action: "Characterize near-limit distribution.",
  reason: "Elevated near-limit failure rate.",
  expected_information: "Repeatability checks.",
  validation_method: "Retest analysis.",
  success_criteria: "Repeatability confirmed.",
  required_data: ["raw parametric logs"],
  risk_if_ignored: "Unaddressed loss.",
  next_step_if_confirmed: "Probe card maintenance.",
  next_step_if_rejected: "Review DFM margins.",
  observed_loss_rate: 0.0268,
  safety_eligible_production_rate: 0,
  opportunity_disclaimer: "Advisory.",
  production_action: "FORBIDDEN",
  production_authorized: false,
  not_a_root_cause: true,
  safety_statement: "Advisory statement.",
  validation_protocol: {
    protocol_id: "PROTO-1",
    replication_check: "Check lots",
    downstream_reliability_risk: "None",
    disclaimer: "Advisory.",
    steps: [],
  },
};

const mockBundle: RecommendationBundle = {
  dataset_id: "yi_synthetic_v2",
  recommendation_count: 1,
  ranking_policy: "Evidence-First",
  ranking_version: "v1",
  evidence_limitations_summary: [],
  ml_evidence_status: "NEEDS_MORE_DATA",
  ml_evidence_summary: "Exploratory",
  safety_invariants: {
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production: 0,
  },
  production_action: "FORBIDDEN",
  production_authorized: false,
  safety_eligible_production_rate: 0,
  disclaimer: "Advisory.",
  recommendations: [mockRec],
};

describe("FailingDiesModal Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders modal with explicit denominators and die records when open", async () => {
    vi.spyOn(api, "fetchRecommendationFailingDies").mockResolvedValue(mockFailingDiesResponse);

    render(
      <FailingDiesModal
        isOpen={true}
        onClose={vi.fn()}
        datasetId="yi_synthetic_v2"
        recommendation={mockRec}
        lotId="L001"
      />
    );

    // Header
    expect(screen.getByText("Failing Dies Drill-Down")).toBeInTheDocument();
    expect(
      screen.queryByText(/Investigation only — production action forbidden/i)
    ).not.toBeInTheDocument();

    // Denominators
    await waitFor(() => {
      expect(screen.getByText(/1\. Recommendation Subgroup/i)).toBeInTheDocument();
      expect(screen.getByText("59")).toBeInTheDocument();
      expect(screen.getByText("/ 277 dies")).toBeInTheDocument();
      expect(screen.getByText(/21\.3% Failure Rate/i)).toBeInTheDocument();

      // Selected Lot
      expect(screen.getByText(/2\. Selected Lot/i)).toBeInTheDocument();
      expect(screen.getByText("97")).toBeInTheDocument();
      expect(screen.getByText("/ 500 dies")).toBeInTheDocument();
      expect(screen.getByText(/19\.4% Lot Failure Rate/i)).toBeInTheDocument();

      // Dataset
      expect(screen.getByText(/3\. Overall Dataset Baseline/i)).toBeInTheDocument();
      expect(screen.getByText("251")).toBeInTheDocument();
      expect(screen.getByText("/ 2,500 dies")).toBeInTheDocument();
      expect(screen.getByText(/10\.0% Dataset Failure Rate/i)).toBeInTheDocument();
    });

    // Die Identity: Lot / Wafer / Die
    expect(screen.getByText("L001 / W01 / D066")).toBeInTheDocument();
    expect(screen.getByText("L001 / W02 / D042")).toBeInTheDocument();

    // Primary failure codes
    expect(screen.getByText("IDDQ")).toBeInTheDocument();
    expect(screen.getByText("VMIN")).toBeInTheDocument();

    // Near limit badge
    expect(screen.getAllByText("Near Limit").length).toBeGreaterThan(0);
  });

  it("filters dies by search input", async () => {
    vi.spyOn(api, "fetchRecommendationFailingDies").mockResolvedValue(mockFailingDiesResponse);

    render(
      <FailingDiesModal
        isOpen={true}
        onClose={vi.fn()}
        datasetId="yi_synthetic_v2"
        recommendation={mockRec}
        lotId="L001"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("L001 / W01 / D066")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search die, wafer, or failure.../i);
    fireEvent.change(searchInput, { target: { value: "D042" } });

    expect(screen.queryByText("L001 / W01 / D066")).not.toBeInTheDocument();
    expect(screen.getByText("L001 / W02 / D042")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", async () => {
    vi.spyOn(api, "fetchRecommendationFailingDies").mockResolvedValue(mockFailingDiesResponse);
    const onClose = vi.fn();

    render(
      <FailingDiesModal
        isOpen={true}
        onClose={onClose}
        datasetId="yi_synthetic_v2"
        recommendation={mockRec}
        lotId="L001"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("L001 / W01 / D066")).toBeInTheDocument();
    });

    const closeBtn = screen.getByLabelText("Close failing dies dialog");
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("RankedRecommendations 'View failing dies' Integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders 'View failing dies' button on recommendation card and opens modal", async () => {
    vi.spyOn(api, "fetchRecommendationFailingDies").mockResolvedValue(mockFailingDiesResponse);

    render(
      <RankedRecommendations
        bundle={mockBundle}
        datasetId="yi_synthetic_v2"
        selectedLotId="L001"
      />
    );

    // Button should be visible with count
    const viewButton = screen.getByRole("button", { name: /View failing dies for/i });
    expect(viewButton).toBeInTheDocument();
    expect(viewButton).toHaveTextContent("View failing dies (67)");

    // Click to open modal
    fireEvent.click(viewButton);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Failing Dies Drill-Down")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("L001 / W01 / D066")).toBeInTheDocument();
    });
  });
});
