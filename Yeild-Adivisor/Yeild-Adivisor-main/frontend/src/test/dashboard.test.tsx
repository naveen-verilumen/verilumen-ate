import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardView } from "../components/DashboardView";
import { DashboardPage } from "../pages/DashboardPage";
import { toDashboardViewModel } from "../services/yieldImprovementViewModel";
import type { DashboardResponse, ReportHypothesis, WaferMapResponse } from "../types/api";
import {
  baseReport,
  dashboardFixture,
  missingDataFixture,
  mlDegradedFixture,
  noHypothesisFixture,
  s09Fixture,
  s15Fixture,
} from "./fixtures";
import {
  V2_DISPLAY_LABELS,
  V2_PRIMARY_PARETO_COUNTS,
  V2_TEST_CATALOG,
  WITHDRAWN_OVERLAY_NAMES,
} from "./v2TestCatalog";

function renderDashboard(payload = dashboardFixture(), waferMap: WaferMapResponse | null = null) {
  const model = toDashboardViewModel(payload);
  return render(<DashboardView model={model} waferMap={waferMap} />);
}

const MINIMAL_WAFER_MAP: WaferMapResponse = {
  dataset_id: "demo",
  n_dies: 1,
  n_pass: 1,
  n_fail: 0,
  lots: [{ lot_id: "L001", display_name: "LOT 001", wafers: ["W01"] }],
  dies: [
    {
      lot_id: "L001",
      wafer_id: "W01",
      die_id: "D001",
      x: 1,
      y: 1,
      first_pass_result: "PASS",
      failed_test_id: null,
      failure_code: null,
      is_first_fail: null,
      retest_available: false,
    },
  ],
  production_action: "FORBIDDEN",
  production_authorized: false,
};

describe("KPI rendering", () => {
  it("displays FPY, FPY loss, and eligible dies from the backend", () => {
    renderDashboard();
    const kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("82.40%")).toBeInTheDocument();
    expect(within(kpis).getByText("17.60%")).toBeInTheDocument();
    expect(within(kpis).getByText("7,842")).toBeInTheDocument();
    expect(screen.queryByText(/statistical signals/i)).not.toBeInTheDocument();
  });
});

describe("Pareto rendering", () => {
  it("shows backend primary-failure categories and die counts", () => {
    renderDashboard();
    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("Where is yield lost?")).toBeInTheDocument();
    expect(within(pareto).getByText("PRIMARY_FAILURE only. Values copied from the analysis output.")).toBeInTheDocument();
    expect(within(pareto).getByText("CONTACT_FAIL")).toBeInTheDocument();
    expect(within(pareto).getByText(/428 dies/)).toBeInTheDocument();
    expect(within(pareto).getByText("EDGE_FAIL")).toBeInTheDocument();
    expect(screen.queryByText(/ANY_FAIL Pareto/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not combined with PRIMARY_FAILURE/i)).not.toBeInTheDocument();
  });

  it("does not render ANY_FAIL Pareto when the API still returns any_fail rows", () => {
    const payload = dashboardFixture();
    payload.report.loss_summary.any_fail = [
      {
        attribution_mode: "ANY_FAIL",
        failure_key: "T004",
        family: "CONTACT",
        detail: "ANY",
        affected_die_count: 96,
        percentage_of_eligible: 0.0384,
        share_of_fails: 0.38,
        selection_rule: "any_fail",
        taxonomy_code: "CONTACT",
      },
      {
        attribution_mode: "ANY_FAIL",
        failure_key: "T006",
        family: "PARAMETRIC",
        detail: "ANY",
        affected_die_count: 53,
        percentage_of_eligible: 0.0212,
        share_of_fails: 0.21,
        selection_rule: "any_fail",
        taxonomy_code: "VMIN",
      },
    ];
    renderDashboard(payload);
    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("Where is yield lost?")).toBeInTheDocument();
    expect(within(pareto).getByText("PRIMARY_FAILURE only. Values copied from the analysis output.")).toBeInTheDocument();
    expect(within(pareto).getByText("CONTACT_FAIL")).toBeInTheDocument();
    expect(within(pareto).getByText(/428 dies/)).toBeInTheDocument();
    expect(within(pareto).getByText("EDGE_FAIL")).toBeInTheDocument();
    expect(within(pareto).getByText(/290 dies/)).toBeInTheDocument();
    expect(screen.queryByText(/ANY_FAIL Pareto/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not combined with PRIMARY_FAILURE/i)).not.toBeInTheDocument();
    expect(screen.queryByText("T004 — CONTACT")).not.toBeInTheDocument();
    expect(screen.queryByText("T006 — VMIN")).not.toBeInTheDocument();
    expect(screen.queryByText(/96 dies/)).not.toBeInTheDocument();
    expect(screen.queryByText(/53 dies/)).not.toBeInTheDocument();
  });

  it("maps V2 test ids to catalog display names without changing die counts", () => {
    const payload = dashboardFixture();
    payload.test_catalog = V2_TEST_CATALOG;
    const template = payload.report.loss_summary.primary_failure[0];
    const failTotal = V2_PRIMARY_PARETO_COUNTS.reduce((sum, [, count]) => sum + count, 0);
    payload.report.loss_summary.primary_failure = V2_PRIMARY_PARETO_COUNTS.map(([failure_key, affected_die_count]) => ({
      ...template,
      failure_key,
      affected_die_count,
      share_of_fails: affected_die_count / failTotal,
      percentage_of_eligible: affected_die_count / 2500,
    }));
    payload.report.hypotheses[0].statement = "Yield loss is associated with T005.";
    payload.report.hypotheses[0].affected_population = { test_id: "T004", n: 92 };
    payload.report.hypotheses[0].validation_steps = ["Review first-pass fails on T005"];
    payload.report.investigation_plan = [
      {
        hypothesis_id: "HYP-SPATIAL-EDGE",
        family: "SPATIAL",
        detail: "EDGE",
        recommendation: "INVESTIGATE",
        steps: ["Review first-pass fails on T005", "Compare affected lots"],
      },
    ];
    renderDashboard(payload);
    const pareto = screen.getByLabelText("Failure Pareto");
    for (const label of Object.values(V2_DISPLAY_LABELS)) {
      expect(within(pareto).getByText(label)).toBeInTheDocument();
    }
    for (const name of WITHDRAWN_OVERLAY_NAMES) {
      expect(within(pareto).queryByText(name)).not.toBeInTheDocument();
    }
    expect(within(pareto).getByText("PRIMARY_FAILURE only. Values copied from the analysis output.")).toBeInTheDocument();
    expect(within(pareto).queryByText(/ANY_FAIL Pareto/)).not.toBeInTheDocument();
    expect(within(pareto).queryByText(/^T004$/)).not.toBeInTheDocument();
    expect(within(pareto).queryByText(/UNCLASSIFIED/i)).not.toBeInTheDocument();
    expect(within(pareto).getByText(/92 dies/)).toBeInTheDocument();
    expect(within(pareto).getAllByText(/12 dies/)).toHaveLength(2);
    const expectedDetail = [
      "T004 — CONTACT · 92 dies · 36.65% of fails · 3.68% of eligible",
      "T006 — VMIN · 39 dies · 15.54% of fails · 1.56% of eligible",
      "T005 — IDDQ · 38 dies · 15.14% of fails · 1.52% of eligible",
      "T001 — CONTINUITY · 17 dies · 6.77% of fails · 0.68% of eligible",
      "T002 — OPENS · 13 dies · 5.18% of fails · 0.52% of eligible",
      "T007 — VMAX · 12 dies · 4.78% of fails · 0.48% of eligible",
      "T009 — FUNCTIONAL · 12 dies · 4.78% of fails · 0.48% of eligible",
      "T003 — SHORTS · 10 dies · 3.98% of fails · 0.40% of eligible",
      "T008 — LEAKAGE · 9 dies · 3.59% of fails · 0.36% of eligible",
      "T010 — SCAN · 9 dies · 3.59% of fails · 0.36% of eligible",
    ];
    expect(within(pareto).getAllByRole("listitem").map((item) => item.textContent)).toEqual(expectedDetail);
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).queryByText("T004 — CONTACT — 92 dies")).not.toBeInTheDocument();
    expect(screen.queryByText("T004 T004 CONTACT")).not.toBeInTheDocument();
    const investigation = screen.getByLabelText("Recommended next investigation");
    expect(within(investigation).getByText(/Wafer Edge:/)).toBeInTheDocument();
  });

  it("uses generator slot names on chart labels and detail rows without changing counts", () => {
    const payload = dashboardFixture();
    payload.test_catalog = {
      ...V2_TEST_CATALOG,
      tests: V2_TEST_CATALOG.tests.map((row, index) => ({
        ...row,
        test_name: WITHDRAWN_OVERLAY_NAMES[index % WITHDRAWN_OVERLAY_NAMES.length],
        display_label: `${row.test_id} — ${WITHDRAWN_OVERLAY_NAMES[index % WITHDRAWN_OVERLAY_NAMES.length]}`,
      })),
    };
    const template = payload.report.loss_summary.primary_failure[0];
    const screenshotCounts: Array<[string, number]> = [
      ["T006", 29],
      ["T005", 27],
      ["T002", 7],
      ["T004", 7],
      ["T010", 6],
      ["T003", 5],
      ["T007", 5],
      ["T009", 5],
      ["T001", 3],
      ["T008", 3],
    ];
    payload.report.loss_summary.primary_failure = screenshotCounts.map(([failure_key, affected_die_count], index, rows) => {
      const failTotal = rows.reduce((sum, [, count]) => sum + count, 0);
      return {
        ...template,
        failure_key,
        affected_die_count,
        share_of_fails: affected_die_count / failTotal,
        percentage_of_eligible: affected_die_count / 500,
      };
    });
    renderDashboard(payload);
    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T006 — VMIN")).toBeInTheDocument();
    expect(within(pareto).getByText("T005 — IDDQ")).toBeInTheDocument();
    expect(within(pareto).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(pareto).getByText("T010 — SCAN")).toBeInTheDocument();
    expect(within(pareto).getByText("T002 — OPENS")).toBeInTheDocument();
    expect(within(pareto).getByText(/29 dies/)).toBeInTheDocument();
    expect(within(pareto).getByText(/27 dies/)).toBeInTheDocument();
    expect(within(pareto).getByText("T002 — OPENS")).toBeInTheDocument();
    expect(within(pareto).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(pareto).getByText(/6 dies/)).toBeInTheDocument();
    for (const name of WITHDRAWN_OVERLAY_NAMES) {
      expect(within(pareto).queryByText(new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).not.toBeInTheDocument();
    }
  });
});

describe("investigation findings", () => {
  it("shows a simple finding without internal diagnostic labels", () => {
    renderDashboard();
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Wafer Edge")).toBeInTheDocument();
    expect(within(findings).getByText("Finding")).toBeInTheDocument();
    expect(within(findings).getByText("Yield loss is higher at the wafer edge.")).toBeInTheDocument();
    expect(within(findings).queryByText("Affected")).not.toBeInTheDocument();
    expect(within(findings).queryByText(/affected population/i)).not.toBeInTheDocument();
    expect(within(findings).queryByText(/^Population$/)).not.toBeInTheDocument();
    expect(within(findings).queryByText("edge — 120 dies")).not.toBeInTheDocument();
    expect(within(findings).getByText("Confidence")).toBeInTheDocument();
    expect(within(findings).getByText("High")).toBeInTheDocument();
    expect(within(findings).getByText("Next")).toBeInTheDocument();
    expect(within(findings).getByText("Confirm the map pattern on additional lots and wafers.")).toBeInTheDocument();
    expect(screen.queryByText("UNCONFIRMED")).not.toBeInTheDocument();
    expect(screen.queryByText("MODERATE_EVIDENCE")).not.toBeInTheDocument();
    expect(screen.queryByText("PRELIMINARY")).not.toBeInTheDocument();
    expect(screen.queryByText(/evidence score/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/supported by/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/counter-evidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/coverage/i)).not.toBeInTheDocument();
    expect(screen.queryByText("SPATIAL.EDGE")).not.toBeInTheDocument();
    expect(screen.queryByText("PROCESS.LOT_VARIATION")).not.toBeInTheDocument();
    expect(screen.queryByText("ROOT CAUSE")).not.toBeInTheDocument();
    expect(screen.queryByText(/the root cause is/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Leading investigation candidate")).not.toBeInTheDocument();
  });
});

describe("no-hypothesis / S16 rendering", () => {
  it("does not invent a recommendation when the backend has no confident hypothesis", () => {
    renderDashboard(noHypothesisFixture());
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("No strong systematic signal was detected.")).toBeInTheDocument();
    expect(screen.queryByText("1. SPATIAL.EDGE")).not.toBeInTheDocument();
    expect(screen.queryByText(/confirmed root cause/i)).not.toBeInTheDocument();
  });
});

describe("ML insight card", () => {
  it("is not rendered on the main dashboard", () => {
    renderDashboard();
    expect(screen.queryByLabelText("ML insight")).not.toBeInTheDocument();
    expect(screen.queryByText(/advanced ml metrics/i)).not.toBeInTheDocument();
    expect(screen.queryByText("SECONDARY_SUPPORT")).not.toBeInTheDocument();
  });

  it("keeps investigation hypotheses when ML is degraded", () => {
    renderDashboard(mlDegradedFixture());
    expect(screen.queryByLabelText("ML insight")).not.toBeInTheDocument();
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Yield loss is higher at the wafer edge.")).toBeInTheDocument();
  });
});

describe("opportunity rendering", () => {
  it("shows a simple opportunity table and overlap warning", () => {
    renderDashboard();
    const opportunity = screen.getByLabelText("Yield opportunity");
    expect(within(opportunity).getByText("Current FPY")).toBeInTheDocument();
    expect(within(opportunity).getByText("82.40%")).toBeInTheDocument();
    expect(within(opportunity).getByText("17.60%")).toBeInTheDocument();
    expect(within(opportunity).getByText("Wafer Edge")).toBeInTheDocument();
    expect(within(opportunity).getByText("3.70%")).toBeInTheDocument();
    expect(
      within(opportunity).getByText(
        "These opportunities may overlap and must not be added together. They are investigation estimates, not guaranteed yield recovery.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/union upper bound/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sum of individuals/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not estimable/i)).not.toBeInTheDocument();
    expect(screen.queryByText("OBSERVED")).not.toBeInTheDocument();
  });
});

describe("safety footer", () => {
  it("is not rendered on the main dashboard", () => {
    const { container } = renderDashboard();
    expect(screen.queryByLabelText("Safety footer")).not.toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.queryByText("Advisory analysis only · No production actions")).not.toBeInTheDocument();
    expect(screen.queryByText("Advisory analysis only")).not.toBeInTheDocument();
    expect(screen.queryByText("No production actions")).not.toBeInTheDocument();
    expect(screen.queryByText(/Production action: FORBIDDEN/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Production authorized: NO/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Safety-eligible production: 0/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Yield opportunity")).toBeInTheDocument();
    expect(screen.getByLabelText("Test reference")).toBeInTheDocument();
    const sections = container.querySelectorAll("section");
    expect(sections[sections.length - 1]).toHaveAttribute("aria-label", "Test reference");
  });
});

describe("missing data", () => {
  it("shows unavailable KPIs without internal validation-state badges", () => {
    renderDashboard(missingDataFixture());
    const kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("cannot_calculate_fpy")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Data quality")).not.toBeInTheDocument();
    expect(screen.queryByText("NEEDS_MORE_DATA")).not.toBeInTheDocument();
    expect(screen.queryByText("REVIEW")).not.toBeInTheDocument();
    expect(screen.queryByText("MONITOR")).not.toBeInTheDocument();
  });
});

describe("S09 rendering", () => {
  it("shows a near-limit finding and never recommends a limit change", () => {
    const { container } = renderDashboard(s09Fixture());
    expect(screen.queryByLabelText("Data quality")).not.toBeInTheDocument();
    expect(screen.queryByText(/Near-limit failure pattern detected/)).not.toBeInTheDocument();
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Test Limit Sensitivity")).toBeInTheDocument();
    expect(within(findings).getByText("Some failures occur close to a test limit.")).toBeInTheDocument();
    expect(screen.queryByText("TEST.LIMIT_SENSITIVITY")).not.toBeInTheDocument();
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).not.toContain("increase limit");
    expect(text.toLowerCase()).not.toContain("relax limit");
    expect(text.toLowerCase()).not.toContain("change test limit");
  });
});

describe("S15 separation", () => {
  it("keeps spatial EDGE and temporal DRIFT as separate hypotheses", () => {
    const { container } = renderDashboard(s15Fixture());
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Wafer Edge")).toBeInTheDocument();
    expect(within(findings).getByText("Process Drift")).toBeInTheDocument();
    expect(screen.queryByText("SPATIAL.EDGE")).not.toBeInTheDocument();
    expect(screen.queryByText("PROCESS.DRIFT")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "These opportunities may overlap and must not be added together. They are investigation estimates, not guaranteed yield recovery.",
      ),
    ).toBeInTheDocument();
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).not.toContain("edge + drift root cause");
    expect(text.toLowerCase()).not.toContain("edge_and_drift");
  });
});

describe("API failure", () => {
  it("shows an unavailable state when the API cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down"))),
    );
    render(<DashboardPage />);
    expect(await screen.findByText(/API unavailable/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("dataset selector", () => {
  it("loads yi_synthetic_v2 without a production dataset dropdown and shows IST analysis time", async () => {
    const payload = dashboardFixture({
      dataset_id: "yi_synthetic_v2",
      generated_at: "2026-09-30T05:48:07Z",
    });
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = String(input);
      if (url.includes("/wafer-map")) {
        return Promise.resolve(
          new Response(JSON.stringify({ dataset_id: "yi_synthetic_v2", n_dies: 0, n_pass: 0, n_fail: 0, lots: [], dies: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.includes("/api/datasets/") && url.includes("/dashboard")) {
        return Promise.resolve(
          new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }
      if (url.endsWith("/api/datasets") || url.endsWith("/api/datasets/")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              datasets: [
                {
                  dataset_id: "yi_synthetic_v2",
                  display_name: "Yield Improvement V2",
                  dataset_type: "SYNTHETIC",
                  path: "data/synthetic/agent_visible/yi_synthetic_v2",
                  has_die_attempts: true,
                  has_persisted_report: false,
                  has_health_report: false,
                  n_lots: 5,
                  n_wafers: 25,
                  n_dies: 2500,
                  die_count: 2500,
                  product_id: "DEV_A",
                  lots: [
                    { lot_id: "L001", display_name: "LOT 001" },
                    { lot_id: "L002", display_name: "LOT 002" },
                    { lot_id: "L003", display_name: "LOT 003" },
                    { lot_id: "L004", display_name: "LOT 004" },
                    { lot_id: "L005", display_name: "LOT 005" },
                  ],
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DashboardPage />);
    const header = screen.getByRole("banner");
    expect(await screen.findByLabelText("Lot")).toBeInTheDocument();
    expect(screen.queryByLabelText("Production Dataset")).not.toBeInTheDocument();
    expect(screen.queryByText("Production Dataset")).not.toBeInTheDocument();
    expect(within(header).queryByRole("combobox", { name: "Production Dataset" })).not.toBeInTheDocument();
    expect(within(header).queryByRole("option", { name: "Yield Improvement V2" })).not.toBeInTheDocument();
    expect(within(header).queryByText("Yield Improvement V2")).not.toBeInTheDocument();
    expect(within(header).getByText("Yield Advisor — Pre-Production")).toBeInTheDocument();
    expect(within(header).getByText("Last analysis: 30 Sep 2026, 11:18 AM IST")).toBeInTheDocument();
    expect(within(header).queryByText(/2026-09-30T05:48:07Z/)).not.toBeInTheDocument();
    expect(within(header).queryByText(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/)).not.toBeInTheDocument();
    expect(within(header).getByRole("option", { name: "LOT 001" })).toBeInTheDocument();
    expect(within(header).getByRole("option", { name: "LOT 005" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("Lot")).toHaveLength(1);
    expect(screen.queryByLabelText("Wafer map lot")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("/api/datasets/yi_synthetic_v2/dashboard"))).toBe(
      true,
    );
    vi.unstubAllGlobals();
  });
});

function cloneHypothesis(overrides: Partial<ReportHypothesis>): ReportHypothesis {
  return { ...dashboardFixture().report.hypotheses[0], ...overrides };
}

function lotScopedFixture(lotId: string, hypotheses: ReportHypothesis[], opportunityRates: number[]): DashboardResponse {
  const display = lotId === "L004" ? "LOT 004" : "LOT 001";
  const payload = dashboardFixture({
    selected_lot_id: lotId,
    selected_lot_display: display,
    lots: [
      { lot_id: "L001", display_name: "LOT 001" },
      { lot_id: "L004", display_name: "LOT 004" },
    ],
  });
  const template = payload.report.opportunities[0];
  payload.report = {
    ...payload.report,
    hypotheses,
    opportunities: hypotheses.map((item, index) => ({
      ...template,
      opportunity_id: `OPP-${lotId}-${index}`,
      hypothesis_id: item.hypothesis_id,
      family: item.family,
      detail: item.detail,
      observed_loss_rate: opportunityRates[index] ?? 0.02,
    })),
  };
  return payload;
}

const L004_FINDINGS: ReportHypothesis[] = [
  cloneHypothesis({
    rank: 1,
    hypothesis_id: "H-PROCESS.WAFER_VARIATION",
    family: "PROCESS",
    detail: "WAFER_VARIATION",
    statement: "Yield loss is associated with wafer identity (L004/W05).",
    evidence_tier: "MODERATE_EVIDENCE",
    affected_population: { group: "L004/W05", n: 100 },
    validation_steps: ["Check whether the same pattern appears on other wafers."],
  }),
  cloneHypothesis({
    rank: 2,
    hypothesis_id: "H-PARAMETRIC.SHIFT",
    family: "PARAMETRIC",
    detail: "SHIFT",
    statement: "Yield loss is associated with a parametric distribution shift.",
    evidence_tier: "MODERATE_EVIDENCE",
    affected_population: { comparison: "VMIN:L004", n: 500 },
    validation_steps: ["Verify VMIN measurement coverage."],
  }),
  cloneHypothesis({
    rank: 3,
    hypothesis_id: "H-TEST.LIMIT_SENSITIVITY",
    family: "TEST",
    detail: "LIMIT_SENSITIVITY",
    statement: "Yield loss is associated with measurements concentrating near a test limit.",
    evidence_tier: "MODERATE_EVIDENCE",
    affected_population: { n: 80 },
    validation_steps: ["Verify the relevant test-limit information."],
  }),
];

const L001_FINDINGS: ReportHypothesis[] = [
  cloneHypothesis({
    rank: 1,
    hypothesis_id: "H-PROCESS.WAFER_VARIATION",
    family: "PROCESS",
    detail: "WAFER_VARIATION",
    statement: "Yield loss is associated with wafer identity (L001/W01).",
    evidence_tier: "MODERATE_EVIDENCE",
    affected_population: { group: "L001/W01", n: 100 },
    validation_steps: ["Check whether the same pattern appears on other wafers."],
  }),
];

describe("lot-scoped investigation findings", () => {
  it("reuses selectedLot for Investigation Findings and Opportunity titles", () => {
    renderDashboard(lotScopedFixture("L004", L004_FINDINGS, [0.04, 0.03, 0.02]));
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Investigation Findings — LOT 004")).toBeInTheDocument();
    expect(within(findings).getByText("W05 has higher failure than the other wafers in LOT 004.")).toBeInTheDocument();
    expect(within(findings).queryByText("Affected")).not.toBeInTheDocument();
    expect(within(findings).queryByText("LOT 004 / W05 — 100 dies")).not.toBeInTheDocument();
    expect(within(findings).getByText("VMIN measurements are shifted in LOT 004.")).toBeInTheDocument();
    expect(within(findings).queryByText("LOT 004 / VMIN — 500 dies")).not.toBeInTheDocument();
    expect(within(findings).getByText("Some failures in LOT 004 occur close to a test limit.")).toBeInTheDocument();
    expect(within(findings).getAllByText("Confidence")).toHaveLength(3);
    expect(within(findings).getAllByText("Next")).toHaveLength(3);
    expect(within(findings).getAllByText("Moderate")).toHaveLength(3);
    expect(screen.queryByText("PROCESS.WAFER_VARIATION")).not.toBeInTheDocument();
    expect(screen.queryByText("PARAMETRIC.SHIFT")).not.toBeInTheDocument();
    expect(screen.queryByText("TEST.LIMIT_SENSITIVITY")).not.toBeInTheDocument();
    expect(screen.queryByText("UNCONFIRMED")).not.toBeInTheDocument();
    expect(screen.queryByText("MODERATE_EVIDENCE")).not.toBeInTheDocument();
    const opportunity = screen.getByLabelText("Yield opportunity");
    expect(within(opportunity).getByText("Yield Opportunity — LOT 004")).toBeInTheDocument();
    expect(within(opportunity).getByText("Wafer Variation")).toBeInTheDocument();
    expect(within(opportunity).getByText("Parametric Shift")).toBeInTheDocument();
    expect(within(opportunity).getByText("Test Limit Sensitivity")).toBeInTheDocument();
  });

  it("shows LOT 001 findings when LOT 001 is selected", () => {
    renderDashboard(lotScopedFixture("L001", L001_FINDINGS, [0.015]));
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).getByText("Investigation Findings — LOT 001")).toBeInTheDocument();
    expect(within(findings).getByText("W01 has higher failure than the other wafers in LOT 001.")).toBeInTheDocument();
    expect(within(findings).queryByText("Affected")).not.toBeInTheDocument();
    expect(within(findings).queryByText("LOT 001 / W01 — 100 dies")).not.toBeInTheDocument();
    expect(within(findings).queryByText(/W05/)).not.toBeInTheDocument();
    expect(within(findings).queryByText(/VMIN/)).not.toBeInTheDocument();
    const opportunity = screen.getByLabelText("Yield opportunity");
    expect(within(opportunity).getByText("Yield Opportunity — LOT 001")).toBeInTheDocument();
    expect(within(opportunity).queryByText("Parametric Shift")).not.toBeInTheDocument();
  });

  it("does not present findings that lack sufficient evidence", () => {
    const insufficient = cloneHypothesis({
      rank: 4,
      hypothesis_id: "H-PROCESS.LOT_VARIATION",
      family: "PROCESS",
      detail: "LOT_VARIATION",
      evidence_tier: "INSUFFICIENT_EVIDENCE",
      association_class: "INSUFFICIENT_EVIDENCE",
      statement: "Yield loss is associated with lot identity (L004).",
      affected_population: { group: "L004", n: 500 },
    });
    renderDashboard(lotScopedFixture("L004", [...L004_FINDINGS, insufficient], [0.04, 0.03, 0.02, 0.01]));
    const findings = screen.getByLabelText("Investigation findings");
    expect(within(findings).queryByText("Lot Variation")).not.toBeInTheDocument();
    expect(within(findings).queryByText("LOT 004 has higher yield loss than other lots.")).not.toBeInTheDocument();
    expect(screen.queryByText("INSUFFICIENT_EVIDENCE")).not.toBeInTheDocument();
  });

  it("keeps PRIMARY_FAILURE Pareto and does not reintroduce ANY_FAIL or ML Insight", () => {
    renderDashboard(lotScopedFixture("L004", L004_FINDINGS, [0.04, 0.03, 0.02]));
    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("CONTACT_FAIL")).toBeInTheDocument();
    expect(within(pareto).getByText(/428 dies/)).toBeInTheDocument();
    expect(screen.queryByText(/ANY_FAIL Pareto/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ML insight")).not.toBeInTheDocument();
  });
});

describe("dashboard lot selector is the single source of truth", () => {
  it("updates Investigation Findings when the existing lot selector changes", async () => {
    const allLots = dashboardFixture({
      selected_lot_id: null,
      lots: [
        { lot_id: "L001", display_name: "LOT 001" },
        { lot_id: "L004", display_name: "LOT 004" },
      ],
    });
    const l001 = lotScopedFixture("L001", L001_FINDINGS, [0.015]);
    const l004 = lotScopedFixture("L004", L004_FINDINGS, [0.04, 0.03, 0.02]);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo) => {
        const url = String(input);
        if (url.includes("/wafer-map")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                dataset_id: "yi_synthetic_v2",
                n_dies: 0,
                n_pass: 0,
                n_fail: 0,
                lots: [
                  { lot_id: "L001", display_name: "LOT 001", wafers: ["W01"] },
                  { lot_id: "L004", display_name: "LOT 004", wafers: ["W01", "W05"] },
                ],
                dies: [],
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (url.includes("/api/datasets/") && url.includes("/dashboard")) {
          const lotId = new URL(url, "http://local.test").searchParams.get("lot_id");
          const payload = lotId === "L004" ? l004 : lotId === "L001" ? l001 : allLots;
          return Promise.resolve(
            new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }),
          );
        }
        if (url.endsWith("/api/datasets") || url.endsWith("/api/datasets/")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                datasets: [
                  {
                    dataset_id: "yi_synthetic_v2",
                    display_name: "Yield Improvement V2",
                    dataset_type: "SYNTHETIC",
                    path: "data/synthetic/agent_visible/yi_synthetic_v2",
                    has_die_attempts: true,
                    has_persisted_report: false,
                    has_health_report: false,
                    n_lots: 5,
                    lots: [
                      { lot_id: "L001", display_name: "LOT 001" },
                      { lot_id: "L004", display_name: "LOT 004" },
                    ],
                  },
                ],
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        return Promise.reject(new Error(`unexpected fetch ${url}`));
      }),
    );
    render(<DashboardPage />);
    expect(await screen.findByLabelText("Investigation findings")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Lot")).toHaveLength(1);
    expect(screen.queryByLabelText("Wafer map lot")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Lot"), { target: { value: "L004" } });
    await waitFor(() => {
      expect(screen.getByText("Investigation Findings — LOT 004")).toBeInTheDocument();
    });
    expect(screen.getByText("W05 has higher failure than the other wafers in LOT 004.")).toBeInTheDocument();
    expect(screen.getByText("Yield Opportunity — LOT 004")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Lot"), { target: { value: "L001" } });
    await waitFor(() => {
      expect(screen.getByText("Investigation Findings — LOT 001")).toBeInTheDocument();
    });
    expect(screen.getByText("W01 has higher failure than the other wafers in LOT 001.")).toBeInTheDocument();
    expect(screen.queryByText("W05 has higher failure than the other wafers in LOT 004.")).not.toBeInTheDocument();
    expect(screen.getByText("Yield Opportunity — LOT 001")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("engineer-facing MVP layout", () => {
  it("keeps FPY, Pareto, wafer map, findings, and opportunity without data-quality or production-field footer", () => {
    const payload = dashboardFixture({
      report: {
        ...dashboardFixture().report,
        sequence_censoring_notice: "Sequence evidence is censored because later tests are not executed after first fail.",
        near_limit_notice: "Near-limit evidence requires engineering validation.",
        data_gaps: {
          required: ["cannot_calculate_fpy", "missing_x_y"],
          recommended: ["missing_parametric"],
          detector_specific: ["spatial_needs_xy"],
          ungrouped: [],
        },
      },
    });
    renderDashboard(payload, MINIMAL_WAFER_MAP);
    expect(screen.getByLabelText("KPI summary")).toBeInTheDocument();
    expect(within(screen.getByLabelText("KPI summary")).getByText("FPY")).toBeInTheDocument();
    expect(screen.getByLabelText("Failure Pareto")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Failure Pareto")).getByText(/PRIMARY_FAILURE only/)).toBeInTheDocument();
    expect(screen.getByLabelText("Wafer map")).toBeInTheDocument();
    expect(screen.getByLabelText("Investigation findings")).toBeInTheDocument();
    expect(screen.getByLabelText("Yield opportunity")).toBeInTheDocument();
    expect(screen.getByLabelText("Test reference")).toBeInTheDocument();
    expect(screen.queryByLabelText("Safety footer")).not.toBeInTheDocument();
    expect(screen.queryByText(/Required gaps/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Recommended and detector-specific gaps/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Detector-specific/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sequence evidence is censored/)).not.toBeInTheDocument();
    expect(screen.queryByText("cannot_calculate_fpy")).not.toBeInTheDocument();
    expect(screen.queryByText(/ANY_FAIL Pareto/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ML insight")).not.toBeInTheDocument();
    expect(screen.queryByText(/statistical signals/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Safety footer")).not.toBeInTheDocument();
    expect(screen.queryByText("Advisory analysis only · No production actions")).not.toBeInTheDocument();
    expect(screen.queryByText("Advisory analysis only")).not.toBeInTheDocument();
    expect(screen.queryByText("No production actions")).not.toBeInTheDocument();
    expect(screen.queryByText(/Production action: FORBIDDEN/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Production authorized: NO/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Safety-eligible production: 0/)).not.toBeInTheDocument();
    const sections = document.querySelectorAll("section");
    expect(sections[sections.length - 1]).toHaveAttribute("aria-label", "Test reference");
  });
});

describe("test reference", () => {
  const DESCRIPTIONS = [
    ["T001", "CONTINUITY", "Continuity check", "Whether an electrical path/pin connection is actually connected"],
    ["T002", "OPENS", "Open-circuit test", "Whether a required connection is broken/disconnected"],
    ["T003", "SHORTS", "Short-circuit test", "Whether two nodes that should be separate are unintentionally connected"],
    ["T004", "CONTACT", "Contact quality test", "Whether the probe/device contact is electrically good enough for reliable measurement"],
    ["T005", "IDDQ", "Quiescent supply current test", "Whether the chip draws abnormal current while in a quiescent state"],
    ["T006", "VMIN", "Minimum operating voltage test", "The lowest supply voltage at which the chip still operates correctly"],
    ["T007", "VMAX", "Maximum operating voltage test", "Whether the device operates correctly/safely at the specified upper voltage condition"],
    ["T008", "LEAKAGE", "Leakage-current test", "Whether unwanted current flows through/off the device when it should be very small"],
    ["T009", "FUNCTIONAL", "Functional test", "Whether the chip performs its intended logical/function behavior"],
    ["T010", "SCAN", "Scan test", "Whether internal scan chains/flip-flops can be shifted and observed correctly"],
  ] as const;

  it("renders the collapsed V2 slot table with all ten names and descriptions", () => {
    renderDashboard(dashboardFixture(), MINIMAL_WAFER_MAP);
    const section = screen.getByLabelText("Test reference");
    expect(within(section).getByText("Test Reference")).toBeInTheDocument();
    const disclosure = section.querySelector("details");
    expect(disclosure).not.toBeNull();
    expect(disclosure).not.toHaveAttribute("open");
    for (const [testId, slot, meaning, checks] of DESCRIPTIONS) {
      expect(within(section).getByText(testId)).toBeInTheDocument();
      expect(within(section).getByText(slot)).toBeInTheDocument();
      expect(within(section).getByText(meaning)).toBeInTheDocument();
      expect(within(section).getByText(checks)).toBeInTheDocument();
    }
    expect(
      within(section).getByText(
        "These are V2 synthetic test-slot definitions used for dashboard interpretation; they do not represent a complete real-world ATE test program.",
      ),
    ).toBeInTheDocument();
    for (const name of WITHDRAWN_OVERLAY_NAMES) {
      expect(within(section).queryByText(name)).not.toBeInTheDocument();
    }
    expect(screen.getByLabelText("Failure Pareto")).toBeInTheDocument();
    expect(screen.getByLabelText("Wafer map")).toBeInTheDocument();
    expect(screen.getByLabelText("Investigation findings")).toBeInTheDocument();
    expect(screen.getByLabelText("Yield opportunity")).toBeInTheDocument();
  });
});

describe("Engineering Recommendations with scope selector in DashboardView", () => {
  const recFixture = {
    dataset_id: "demo",
    recommendation_count: 1,
    ranking_policy: "Evidence-First",
    ranking_version: "v1",
    evidence_limitations_summary: [],
    ml_evidence_status: "NEEDS_MORE_DATA" as const,
    ml_evidence_summary: "Exploratory",
    safety_invariants: {
      production_action: "FORBIDDEN" as const,
      production_authorized: false as const,
      safety_eligible_production: 0,
    },
    production_action: "FORBIDDEN" as const,
    production_authorized: false as const,
    safety_eligible_production_rate: 0 as const,
    disclaimer: "Advisory",
    recommendations: [
      {
        recommendation_id: "REC-1",
        title: "Investigate L004 Thermal Variation",
        recommendation_category: "Lot investigation" as const,
        status: "PROPOSED" as const,
        scope: "LOT_SPECIFIC" as const,
        lot_id: "L004",
        priority_rank: 1,
        priority_tier: "HIGH" as const,
        confidence_tier: "HIGH" as const,
        ranking_score: 0.9,
        ranking_rationale: "High evidence",
        observed_pattern: "Loss pattern",
        target_population: "PROCESS L004",
        affected_die_count: 50,
        eligible_die_count: 1000,
        observed_failure_rate: 0.05,
        baseline_failure_rate: 0.02,
        supporting_detectors: ["lot"],
        hypothesis_confidence: "MODERATE",
        ml_evidence_status: "NEEDS_MORE_DATA" as const,
        ml_evidence_notes: "",
        missing_evidence: [],
        limitations: [],
        recommended_action: "Inspect chamber",
        reason: "Excess fail rate",
        expected_information: "",
        validation_method: "",
        success_criteria: "",
        required_data: [],
        risk_if_ignored: "",
        next_step_if_confirmed: "",
        next_step_if_rejected: "",
        validation_protocol: {
          protocol_id: "P1",
          steps: [],
          replication_check: "",
          downstream_reliability_risk: "",
          disclaimer: "",
        },
        observed_loss_rate: 0.05,
        safety_eligible_production_rate: 0 as const,
        opportunity_disclaimer: "",
        production_action: "FORBIDDEN" as const,
        production_authorized: false as const,
        not_a_root_cause: true as const,
        safety_statement: "",
      },
    ],
  };

  it("renders Engineering Recommendations with scope selector tabs in DashboardView", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: recFixture,
    };
    const model = toDashboardViewModel(payload);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L004" />);

    expect(screen.getByLabelText("Engineering Recommendations")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Global/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Lot-Level/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /All/i })).toBeInTheDocument();
    expect(screen.getByText("Investigate L004 Thermal Variation")).toBeInTheDocument();

    // Verify other dashboard sections continue working normally
    expect(screen.getByLabelText("KPI summary")).toBeInTheDocument();
    expect(screen.getByLabelText("Failure Pareto")).toBeInTheDocument();
    expect(screen.getByLabelText("Wafer map")).toBeInTheDocument();
    expect(screen.getByLabelText("Investigation findings")).toBeInTheDocument();
    expect(screen.getByLabelText("Yield opportunity")).toBeInTheDocument();
    expect(screen.getByLabelText("Test reference")).toBeInTheDocument();
  });

  it("allows switching between Global and Lot-Level recommendations in DashboardView", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: {
        ...recFixture,
        recommendation_count: 2,
        recommendations: [
          recFixture.recommendations[0],
          {
            ...recFixture.recommendations[0],
            recommendation_id: "REC-GLOBAL-BORDER",
            title: "Review Edge Ring Spatial Loss",
            scope: "GLOBAL" as const,
            lot_id: null,
            target_population: "BORDER",
          },
        ],
      },
    };
    const model = toDashboardViewModel(payload);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L004" />);

    // Click Global
    fireEvent.click(screen.getByRole("tab", { name: /Global/i }));
    expect(screen.getByText("Review Edge Ring Spatial Loss")).toBeInTheDocument();
    expect(screen.queryByText("Investigate L004 Thermal Variation")).not.toBeInTheDocument();

    // Click Lot-Level
    fireEvent.click(screen.getByRole("tab", { name: /Lot-Level/i }));
    expect(screen.getByText("Investigate L004 Thermal Variation")).toBeInTheDocument();
    expect(screen.queryByText("Review Edge Ring Spatial Loss")).not.toBeInTheDocument();
  });

  it("hides Engineering Recommendations entirely when All Lots is selected", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: recFixture,
    };
    const model = toDashboardViewModel(payload);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="" />);

    // Entire section hidden
    expect(screen.queryByLabelText("Engineering Recommendations")).not.toBeInTheDocument();
    expect(screen.queryByText("Engineering Recommendations")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Global/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Lot-Level/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Investigate L004 Thermal Variation")).not.toBeInTheDocument();

    // Other dashboard sections remain visible and functional
    expect(screen.getByLabelText("KPI summary")).toBeInTheDocument();
    expect(screen.getByLabelText("Failure Pareto")).toBeInTheDocument();
    expect(screen.getByLabelText("Wafer map")).toBeInTheDocument();
    expect(screen.getByLabelText("Investigation findings")).toBeInTheDocument();
    expect(screen.getByLabelText("Yield opportunity")).toBeInTheDocument();
    expect(screen.getByLabelText("Test reference")).toBeInTheDocument();
  });

  it("global recommendations do not bypass the visibility rule when All Lots is selected", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: {
        ...recFixture,
        recommendation_count: 1,
        recommendations: [
          {
            ...recFixture.recommendations[0],
            recommendation_id: "REC-GLOBAL-BORDER",
            title: "Review Edge Ring Spatial Loss",
            scope: "GLOBAL" as const,
            lot_id: null,
            target_population: "BORDER",
          },
        ],
      },
    };
    const model = toDashboardViewModel(payload);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="" />);

    expect(screen.queryByLabelText("Engineering Recommendations")).not.toBeInTheDocument();
    expect(screen.queryByText("Review Edge Ring Spatial Loss")).not.toBeInTheDocument();
  });

  it("immediately hides section when switching from a specific lot back to All Lots", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: recFixture,
    };
    const model = toDashboardViewModel(payload);
    const { rerender } = render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L004" />);

    expect(screen.getByLabelText("Engineering Recommendations")).toBeInTheDocument();
    expect(screen.getByText("Investigate L004 Thermal Variation")).toBeInTheDocument();

    // Switch to All Lots ("")
    rerender(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="" />);

    expect(screen.queryByLabelText("Engineering Recommendations")).not.toBeInTheDocument();
    expect(screen.queryByText("Investigate L004 Thermal Variation")).not.toBeInTheDocument();
  });

  it("updates recommendations when selecting another lot", () => {
    const payload = {
      ...dashboardFixture(),
      recommendations: {
        ...recFixture,
        recommendation_count: 2,
        recommendations: [
          recFixture.recommendations[0],
          {
            ...recFixture.recommendations[0],
            recommendation_id: "REC-PROCESS-L002",
            title: "Investigate L002 Excursion",
            scope: "LOT_SPECIFIC" as const,
            lot_id: "L002",
            target_population: "PROCESS L002",
          },
        ],
      },
    };
    const model = toDashboardViewModel(payload);
    const { rerender } = render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L004" />);

    expect(screen.getByText("Investigate L004 Thermal Variation")).toBeInTheDocument();
    expect(screen.queryByText("Investigate L002 Excursion")).not.toBeInTheDocument();

    // Select L002
    rerender(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L002" />);

    expect(screen.getByText("Investigate L002 Excursion")).toBeInTheDocument();
    expect(screen.queryByText("Investigate L004 Thermal Variation")).not.toBeInTheDocument();
  });
});

describe("Lot-specific dashboard metrics and Pareto rendering", () => {
  const globalFixture = dashboardFixture({
    dataset_id: "yi_synthetic_v2",
    selected_lot_id: null,
    selected_lot_display: null,
    report: baseReport({
      dataset_id: "yi_synthetic_v2",
      fpy_summary: {
        eligible_die_count: 2500,
        first_pass_pass_count: 2249,
        first_pass_fail_count: 251,
        excluded_count: 0,
        fpy: 0.8996,
        fpy_loss: 0.1004,
        fpy_policy_version: "yi_fpy_v1",
        abort_policy: "STOP_ON_FAIL",
        policy_notes: [],
      },
      loss_summary: {
        primary_failure: [
          {
            attribution_mode: "PRIMARY_FAILURE",
            failure_key: "T004",
            family: "CONTACT",
            detail: "CONTACT",
            affected_die_count: 92,
            percentage_of_eligible: 0.0368,
            share_of_fails: 0.3665,
            selection_rule: "first_fail",
            taxonomy_code: "CONTACT",
          },
          {
            attribution_mode: "PRIMARY_FAILURE",
            failure_key: "T006",
            family: "PARAMETRIC",
            detail: "VMIN",
            affected_die_count: 39,
            percentage_of_eligible: 0.0156,
            share_of_fails: 0.1554,
            selection_rule: "first_fail",
            taxonomy_code: "VMIN",
          },
        ],
        any_fail: [],
        primary_available: true,
        primary_unavailable_note: null,
        modes_not_combined: true,
      },
    }),
  });

  const l001Fixture = dashboardFixture({
    dataset_id: "yi_synthetic_v2",
    selected_lot_id: "L001",
    selected_lot_display: "LOT 001",
    report: baseReport({
      dataset_id: "yi_synthetic_v2",
      fpy_summary: {
        eligible_die_count: 500,
        first_pass_pass_count: 467,
        first_pass_fail_count: 33,
        excluded_count: 0,
        fpy: 0.934,
        fpy_loss: 0.066,
        fpy_policy_version: "yi_fpy_v1",
        abort_policy: "STOP_ON_FAIL",
        policy_notes: [],
      },
      loss_summary: {
        primary_failure: [
          {
            attribution_mode: "PRIMARY_FAILURE",
            failure_key: "T001",
            family: "CONTACT",
            detail: "CONTINUITY",
            affected_die_count: 5,
            percentage_of_eligible: 0.01,
            share_of_fails: 0.1515,
            selection_rule: "first_fail",
            taxonomy_code: "CONTACT.CONTINUITY",
          },
          {
            attribution_mode: "PRIMARY_FAILURE",
            failure_key: "T005",
            family: "PARAMETRIC",
            detail: "IDDQ",
            affected_die_count: 5,
            percentage_of_eligible: 0.01,
            share_of_fails: 0.1515,
            selection_rule: "first_fail",
            taxonomy_code: "IDDQ",
          },
        ],
        any_fail: [],
        primary_available: true,
        primary_unavailable_note: null,
        modes_not_combined: true,
      },
    }),
  });

  const l004Fixture = dashboardFixture({
    dataset_id: "yi_synthetic_v2",
    selected_lot_id: "L004",
    selected_lot_display: "LOT 004",
    report: baseReport({
      dataset_id: "yi_synthetic_v2",
      fpy_summary: {
        eligible_die_count: 500,
        first_pass_pass_count: 403,
        first_pass_fail_count: 97,
        excluded_count: 0,
        fpy: 0.806,
        fpy_loss: 0.194,
        fpy_policy_version: "yi_fpy_v1",
        abort_policy: "STOP_ON_FAIL",
        policy_notes: [],
      },
      loss_summary: {
        primary_failure: [
          {
            attribution_mode: "PRIMARY_FAILURE",
            failure_key: "T006",
            family: "PARAMETRIC",
            detail: "VMIN",
            affected_die_count: 45,
            percentage_of_eligible: 0.09,
            share_of_fails: 0.4639,
            selection_rule: "first_fail",
            taxonomy_code: "VMIN",
          },
        ],
        any_fail: [],
        primary_available: true,
        primary_unavailable_note: null,
        modes_not_combined: true,
      },
    }),
  });

  it("displays correct lot-specific KPIs and Pareto counts for LOT 001", () => {
    const model = toDashboardViewModel(l001Fixture);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L001" />);

    const kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("93.40%")).toBeInTheDocument();
    expect(within(kpis).getByText("6.60%")).toBeInTheDocument();
    expect(within(kpis).getByText("500")).toBeInTheDocument();
    expect(within(kpis).queryByText("2,500")).not.toBeInTheDocument();
    expect(within(kpis).queryByText("89.96%")).not.toBeInTheDocument();

    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T001 — CONTINUITY")).toBeInTheDocument();
    expect(within(pareto).getAllByText(/5 dies/)).toHaveLength(2);
    expect(within(pareto).queryByText(/92 dies/)).not.toBeInTheDocument();
  });

  it("displays correct lot-specific KPIs and Pareto counts for LOT 004", () => {
    const model = toDashboardViewModel(l004Fixture);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L004" />);

    const kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("80.60%")).toBeInTheDocument();
    expect(within(kpis).getByText("19.40%")).toBeInTheDocument();
    expect(within(kpis).getByText("500")).toBeInTheDocument();
    expect(within(kpis).queryByText("2,500")).not.toBeInTheDocument();

    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T006 — VMIN")).toBeInTheDocument();
    expect(within(pareto).getByText(/45 dies/)).toBeInTheDocument();
  });

  it("restores global KPIs and Pareto counts when All Lots is selected", () => {
    const model = toDashboardViewModel(globalFixture);
    render(<DashboardView model={model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="" />);

    const kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("89.96%")).toBeInTheDocument();
    expect(within(kpis).getByText("10.04%")).toBeInTheDocument();
    expect(within(kpis).getByText("2,500")).toBeInTheDocument();
    expect(within(kpis).queryByText("500")).not.toBeInTheDocument();

    const pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(pareto).getByText(/92 dies/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Engineering Recommendations")).not.toBeInTheDocument();
  });

  it("updates all dependent sections dynamically when switching between lots and All Lots", () => {
    const l001Model = toDashboardViewModel(l001Fixture);
    const globalModel = toDashboardViewModel(globalFixture);

    // Initial render: LOT 001
    const { rerender } = render(
      <DashboardView model={l001Model} waferMap={MINIMAL_WAFER_MAP} selectedLotId="L001" />
    );

    let kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("93.40%")).toBeInTheDocument();
    expect(within(kpis).getByText("500")).toBeInTheDocument();

    let pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T001 — CONTINUITY")).toBeInTheDocument();

    // Switch to All Lots
    rerender(
      <DashboardView model={globalModel} waferMap={MINIMAL_WAFER_MAP} selectedLotId="" />
    );

    kpis = screen.getByLabelText("KPI summary");
    expect(within(kpis).getByText("89.96%")).toBeInTheDocument();
    expect(within(kpis).getByText("2,500")).toBeInTheDocument();
    expect(within(kpis).queryByText("500")).not.toBeInTheDocument();

    pareto = screen.getByLabelText("Failure Pareto");
    expect(within(pareto).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(pareto).getByText(/92 dies/)).toBeInTheDocument();
    expect(within(pareto).queryByText("T001 — CONTINUITY")).not.toBeInTheDocument();
  });
});
