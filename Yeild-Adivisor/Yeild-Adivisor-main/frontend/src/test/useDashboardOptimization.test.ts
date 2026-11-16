import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useDashboard } from "../hooks/useDashboard";
import * as api from "../services/yieldImprovementApi";
import type { DashboardResponse, DatasetListResponse, WaferMapResponse, ParametricAnalysisReport } from "../types/api";

const mockDatasets: DatasetListResponse = {
  datasets: [
    {
      dataset_id: "yi_synthetic_v2",
      display_name: "Yield Improvement V2",
      dataset_type: "SYNTHETIC",
      has_die_attempts: true,
      has_persisted_report: true,
      has_health_report: true,
      lots: [
        { lot_id: "L001", display_name: "LOT 001" },
        { lot_id: "L002", display_name: "LOT 002" },
      ],
    },
  ],
};

const mockDashboard = (lotId = ""): DashboardResponse => ({
  dataset_id: "yi_synthetic_v2",
  selected_lot_id: lotId || null,
  selected_lot_display: lotId ? `LOT ${lotId}` : null,
  lots: [{ lot_id: "L001", display_name: "LOT 001" }],
  generated_at: "2026-10-12T12:00:00Z",
  report: {
    report_id: "RPT-1",
    analysis_id: "yi_synthetic_v2",
    generated_at: "2026-10-12T12:00:00Z",
    dataset_id: "yi_synthetic_v2",
    executive_summary: { headline: "FPY 90%", key_findings: [], bottom_line: "Normal" },
    fpy_summary: {
      eligible_die_count: lotId ? 500 : 2500,
      first_pass_pass_count: lotId ? 467 : 2249,
      first_pass_fail_count: lotId ? 33 : 251,
      excluded_count: 0,
      fpy: 0.9,
      fpy_loss: 0.1,
      fpy_policy_version: "v1",
      abort_policy: "NONE",
      policy_notes: [],
    },
    loss_summary: { primary_failure: [], any_fail: [], primary_available: true, primary_unavailable_note: null, modes_not_combined: true },
    evidence_findings: [],
    hypotheses: [],
    opportunities: [],
    overlap: null,
    validation: [],
    no_actionable_recommendation: false,
    investigation_plan: [],
    data_gaps: [],
    limitations: [],
    safety_statement: "SAFE",
    near_limit_notice: null,
    sequence_censoring_notice: null,
    no_actionable_notice: null,
    traceability: {} as any,
    configuration_versions: {},
    production_action: "FORBIDDEN",
    production_authorized: false,
    safety_eligible_production_count: 0,
    safety_eligible_production_rate: 0,
    invoked_agents: [],
    disclaimer: "Disclaimer",
    pipeline_version: "0.1.0",
  },
  test_catalog: {},
  ml: { available: true, model_name: "yi_ml_v1", model_version: "v1", evidence_role: "SECONDARY", independence: false, metrics: null, calibration: null, feature_names: [], feature_importance: [], disclaimer: "", ml_support_status: "RELIABLE", ml_supported: true },
  health: { available: true, overall_status: "HEALTHY", reduced_ml_evidence: false, model_version: "v1", dimensions: null, recommendations: [], triggers: [], disclaimer: "" },
  registry: { available: true, active_version: "v1", state: "ACTIVE", architecture: "RF" },
  recommendations: {
    dataset_id: "yi_synthetic_v2",
    selected_lot_id: lotId || null,
    recommendation_count: 1,
    recommendations: [],
    disclaimer: "",
    production_action: "FORBIDDEN",
    production_authorized: false,
  },
  production_action: "FORBIDDEN",
  production_authorized: false,
  safety_eligible_production_count: 0,
  safety_eligible_production_rate: 0,
  invoked_agents: [],
  safety_statement: "SAFE",
  disclaimer: "Disclaimer",
});

const mockWaferMap: WaferMapResponse = {
  dataset_id: "yi_synthetic_v2",
  n_dies: 500,
  n_pass: 450,
  n_fail: 50,
  lots: [{ lot_id: "L001", display_name: "LOT 001", wafers: ["W01"] }],
  dies: [],
  production_action: "FORBIDDEN",
  production_authorized: false,
};

const mockParametric: ParametricAnalysisReport = {
  dataset_id: "yi_synthetic_v2",
  generated_at: "2026-10-12T12:00:00Z",
  n_parameters_analyzed: 1,
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
  results: [],
};

describe("useDashboard Optimizations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchDatasets").mockResolvedValue(mockDatasets);
    vi.spyOn(api, "fetchDashboard").mockImplementation((_, opts) =>
      Promise.resolve(mockDashboard(opts?.lotId || ""))
    );
    vi.spyOn(api, "fetchWaferMap").mockResolvedValue(mockWaferMap);
    vi.spyOn(api, "fetchParametricAnalysis").mockResolvedValue(mockParametric);
  });

  it("skips redundant fetchDatasets and fetchWaferMap calls on lot selection", async () => {
    const { result } = renderHook(() => useDashboard());

    // Wait for initial load to finish
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(api.fetchDatasets).toHaveBeenCalledTimes(1);
    expect(api.fetchWaferMap).toHaveBeenCalledTimes(1);
    expect(api.fetchDashboard).toHaveBeenCalledTimes(1);
    expect(api.fetchParametricAnalysis).toHaveBeenCalledTimes(1);

    // Select Lot L001
    await act(async () => {
      result.current.selectLot("L001");
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // fetchDatasets and fetchWaferMap should NOT have been called again!
    expect(api.fetchDatasets).toHaveBeenCalledTimes(1);
    expect(api.fetchWaferMap).toHaveBeenCalledTimes(1);

    // Dashboard and parametric analysis SHOULD be called for the new lot
    expect(api.fetchDashboard).toHaveBeenCalledTimes(2);
    expect(api.fetchParametricAnalysis).toHaveBeenCalledTimes(2);
    expect(result.current.selectedLotId).toBe("L001");
  });

  it("re-fetches datasets and waferMap when refreshAnalysis is explicitly triggered", async () => {
    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      result.current.refreshAnalysis();
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(api.fetchDatasets).toHaveBeenCalledTimes(2);
    expect(api.fetchWaferMap).toHaveBeenCalledTimes(2);
  });

  it("guards against out-of-order stale responses overwriting newer lot selections", async () => {
    let resolveL001: (val: DashboardResponse) => void = () => {};
    let resolveL002: (val: DashboardResponse) => void = () => {};

    const dashboardSpy = vi.spyOn(api, "fetchDashboard").mockImplementation((_, opts) => {
      if (opts?.lotId === "L001") {
        return new Promise<DashboardResponse>((resolve) => {
          resolveL001 = resolve;
        });
      }
      if (opts?.lotId === "L002") {
        return new Promise<DashboardResponse>((resolve) => {
          resolveL002 = resolve;
        });
      }
      return Promise.resolve(mockDashboard());
    });

    const { result } = renderHook(() => useDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // User rapidly switches: first L001, then L002
    act(() => {
      result.current.selectLot("L001");
    });
    act(() => {
      result.current.selectLot("L002");
    });

    // L002 (newer) finishes first
    await act(async () => {
      resolveL002(mockDashboard("L002"));
    });
    await waitFor(() => expect(result.current.selectedLotId).toBe("L002"));

    // L001 (older/stale) finishes late
    await act(async () => {
      resolveL001(mockDashboard("L001"));
    });

    // State MUST stay on L002 and not be corrupted by the stale L001 response
    expect(result.current.selectedLotId).toBe("L002");
  });
});
