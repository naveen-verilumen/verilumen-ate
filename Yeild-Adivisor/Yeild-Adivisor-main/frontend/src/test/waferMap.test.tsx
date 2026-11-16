import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardView } from "../components/DashboardView";
import { WaferMap } from "../components/WaferMap";
import { toDashboardViewModel } from "../services/yieldImprovementViewModel";
import type { WaferMapDie, WaferMapResponse } from "../types/api";
import { dashboardFixture } from "./fixtures";
import { V2_TEST_CATALOG_TESTS, WITHDRAWN_OVERLAY_NAMES } from "./v2TestCatalog";

const CATALOG = V2_TEST_CATALOG_TESTS;

function makeDie(
  lotId: string,
  waferId: string,
  x: number,
  y: number,
  overrides: Partial<WaferMapDie> = {},
): WaferMapDie {
  const n = (y - 1) * 10 + x;
  const dieId = `D${String(n).padStart(3, "0")}`;
  return {
    lot_id: lotId,
    wafer_id: waferId,
    die_id: dieId,
    x,
    y,
    first_pass_result: "PASS",
    failed_test_id: null,
    failure_code: null,
    is_first_fail: null,
    retest_available: false,
    ...overrides,
  };
}

function makeWafer(lotId: string, waferId: string, fails: Record<string, Partial<WaferMapDie>>): WaferMapDie[] {
  const dies: WaferMapDie[] = [];
  for (let y = 1; y <= 10; y += 1) {
    for (let x = 1; x <= 10; x += 1) {
      const n = (y - 1) * 10 + x;
      const dieId = `D${String(n).padStart(3, "0")}`;
      dies.push(makeDie(lotId, waferId, x, y, fails[dieId]));
    }
  }
  return dies;
}

function waferMapFixture(): WaferMapResponse {
  const l001w01 = makeWafer("L001", "W01", {
    D049: {
      first_pass_result: "FAIL",
      failed_test_id: "T004",
      failure_code: "CONTACT",
      is_first_fail: true,
      retest_available: true,
    },
    D007: {
      first_pass_result: "FAIL",
      failed_test_id: "T007",
      failure_code: "VMAX",
      is_first_fail: true,
      retest_available: false,
    },
    D016: {
      first_pass_result: "FAIL",
      failed_test_id: "T006",
      failure_code: "VMIN",
      is_first_fail: true,
      retest_available: false,
    },
  });
  const l001w02 = makeWafer("L001", "W02", {
    D001: {
      first_pass_result: "FAIL",
      failed_test_id: "T001",
      failure_code: "CONTINUITY",
      is_first_fail: true,
    },
  });
  const l001w03 = makeWafer("L001", "W03", {
    D010: {
      first_pass_result: "FAIL",
      failed_test_id: "T001",
      failure_code: "CONTINUITY",
      is_first_fail: true,
    },
    D020: {
      first_pass_result: "FAIL",
      failed_test_id: "T001",
      failure_code: "CONTINUITY",
      is_first_fail: true,
    },
  });
  const l001w04 = makeWafer("L001", "W04", {});
  const l001w05 = makeWafer("L001", "W05", {});
  const l002w01 = makeWafer("L002", "W01", {});
  const dies = [...l001w01, ...l001w02, ...l001w03, ...l001w04, ...l001w05, ...l002w01];
  return {
    dataset_id: "yi_synthetic_v2",
    grain: "lot_id+wafer_id+die_id",
    n_dies: dies.length,
    n_pass: dies.filter((die) => die.first_pass_result === "PASS").length,
    n_fail: dies.filter((die) => die.first_pass_result === "FAIL").length,
    lots: [
      { lot_id: "L001", display_name: "LOT 001", wafers: ["W01", "W02", "W03", "W04", "W05"] },
      { lot_id: "L002", display_name: "LOT 002", wafers: ["W01"] },
    ],
    dies,
    production_action: "FORBIDDEN",
    production_authorized: false,
  };
}

function renderMap(data: WaferMapResponse = waferMapFixture()) {
  return render(<WaferMap data={data} catalog={CATALOG} />);
}

describe("wafer map", () => {
  it("renders the selected dashboard lot without a second lot selector", () => {
    renderMap();
    const section = screen.getByLabelText("Wafer map");
    expect(within(section).queryByLabelText("Wafer map lot")).not.toBeInTheDocument();
    expect(within(section).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(section).getAllByText("LOT 001").length).toBeGreaterThan(0);
    const wafers = within(section).getByLabelText("Wafer map wafer");
    expect(within(wafers).getByRole("button", { name: "Wafer W01" })).toHaveAttribute("aria-pressed", "true");
    expect(within(wafers).getByRole("button", { name: "Wafer W02" })).toBeInTheDocument();
    expect(within(wafers).getByRole("button", { name: "Wafer W03" })).toBeInTheDocument();
    expect(within(wafers).getByRole("button", { name: "Wafer W04" })).toBeInTheDocument();
    expect(within(wafers).getByRole("button", { name: "Wafer W05" })).toBeInTheDocument();
    expect(wafers.tagName).not.toBe("SELECT");
  });

  it("shows W01 first and switches to a single W03 map", () => {
    renderMap();
    const section = screen.getByLabelText("Wafer map");
    expect(within(section).getByText("LOT 001 · WAFER W01")).toBeInTheDocument();
    expect(within(section).getByLabelText("Wafer die map").querySelectorAll("button")).toHaveLength(100);
    expect(screen.getByLabelText("Die D049 FAIL X 9 Y 5")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Wafer W03" }));
    expect(within(section).getByText("LOT 001 · WAFER W03")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Wafer W03" })).toHaveAttribute("aria-pressed", "true");
    expect(within(section).getByLabelText("Wafer die map").querySelectorAll("button")).toHaveLength(100);
    expect(screen.getByLabelText("Die D049 PASS X 9 Y 5")).toBeInTheDocument();
    expect(screen.getByLabelText("Die D010 FAIL X 10 Y 1")).toBeInTheDocument();
    const summary = screen.getByText("First-pass failure summary").parentElement as HTMLElement;
    expect(within(summary).getByText("T001 — CONTINUITY")).toBeInTheDocument();
    expect(within(summary).getByText("CONTINUITY")).toBeInTheDocument();
    expect(within(summary).getByText("2 dies")).toBeInTheDocument();
    expect(within(summary).queryByText("T004 — CONTACT")).not.toBeInTheDocument();
    expect(within(summary).queryByText("CONTACT")).not.toBeInTheDocument();
  });

  it("shows PASS details when a passing die is selected", () => {
    renderMap();
    fireEvent.click(screen.getByLabelText("Die D002 PASS X 2 Y 1"));
    const details = screen.getByText("Selected die").parentElement as HTMLElement;
    expect(within(details).getByText("D002")).toBeInTheDocument();
    expect(within(details).getByText(/X: 2/)).toBeInTheDocument();
    expect(within(details).getByText(/Y: 1/)).toBeInTheDocument();
    expect(within(details).getByText("Passed")).toBeInTheDocument();
    expect(within(details).getByText("Passed all tests")).toBeInTheDocument();
  });

  it("shows first-pass fail test, catalog name, and failure reason", () => {
    renderMap();
    fireEvent.click(screen.getByLabelText("Die D049 FAIL X 9 Y 5"));
    const details = screen.getByText("Selected die").parentElement as HTMLElement;
    expect(within(details).getAllByText("Failed").length).toBeGreaterThan(0);
    expect(within(details).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(details).getByText("CONTACT")).toBeInTheDocument();
    expect(within(details).getByText("Retest available")).toBeInTheDocument();
    expect(within(details).queryByText("Passed")).not.toBeInTheDocument();
    expect(within(details).queryByText("Passed all tests")).not.toBeInTheDocument();
  });

  it("labels T007 with the generator program slot and counts first-pass failures only", () => {
    renderMap();
    fireEvent.click(screen.getByLabelText("Die D007 FAIL X 7 Y 1"));
    const details = screen.getByText("Selected die").parentElement as HTMLElement;
    expect(within(details).getByText("T007 — VMAX")).toBeInTheDocument();
    expect(within(details).getByText("VMAX")).toBeInTheDocument();
    const summary = screen.getByText("First-pass failure summary").parentElement as HTMLElement;
    expect(within(summary).getByText("T004 — CONTACT")).toBeInTheDocument();
    expect(within(summary).getByText("T006 — VMIN")).toBeInTheDocument();
    expect(within(summary).getByText("T007 — VMAX")).toBeInTheDocument();
    expect(within(summary).queryByText(/Unclassified V2 Test/)).not.toBeInTheDocument();
    for (const name of WITHDRAWN_OVERLAY_NAMES) {
      expect(within(summary).queryByText(name)).not.toBeInTheDocument();
    }
    expect(within(summary).getAllByText("1 dies")).toHaveLength(3);
  });

  it("updates wafer choices when the dashboard selected lot changes", () => {
    const data = waferMapFixture();
    const { rerender } = render(<WaferMap data={data} catalog={CATALOG} selectedLotId="L001" />);
    expect(screen.getByText("LOT 001 · WAFER W01")).toBeInTheDocument();
    rerender(<WaferMap data={data} catalog={CATALOG} selectedLotId="L002" />);
    const wafers = screen.getByLabelText("Wafer map wafer");
    expect(within(wafers).getByRole("button", { name: "Wafer W01" })).toBeInTheDocument();
    expect(within(wafers).queryByRole("button", { name: "Wafer W02" })).not.toBeInTheDocument();
    expect(within(wafers).queryByRole("button", { name: "Wafer W03" })).not.toBeInTheDocument();
    expect(screen.getByText("LOT 002 · WAFER W01")).toBeInTheDocument();
    expect(screen.getByLabelText("Die D049 PASS X 9 Y 5")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Die D049 PASS X 9 Y 5"));
    const details = screen.getByText("Selected die").parentElement as HTMLElement;
    expect(within(details).getByText("Passed all tests")).toBeInTheDocument();
  });

  it("shows lot-level first-pass context without changing wafer FPY for a retest fail", () => {
    renderMap();
    const section = screen.getByLabelText("Wafer map");
    expect(within(section).getByText("Selected wafer: W01")).toBeInTheDocument();
    expect(within(section).getAllByText("LOT 001").length).toBeGreaterThan(0);
    expect(within(section).getByText("500")).toBeInTheDocument();
    expect(within(section).getByText("100")).toBeInTheDocument();
    expect(within(section).getByText("97.00%")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Die D049 FAIL X 9 Y 5"));
    const details = screen.getByText("Selected die").parentElement as HTMLElement;
    expect(within(details).getByText("Retest available")).toBeInTheDocument();
    expect(within(section).getByText("97.00%")).toBeInTheDocument();
  });
});

describe("dashboard without statistical signals", () => {
  it("does not render the statistical signals table", () => {
    const model = toDashboardViewModel(dashboardFixture());
    render(<DashboardView model={model} waferMap={waferMapFixture()} />);
    expect(screen.queryByText(/statistical signals/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Statistical evidence")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Wafer map")).toBeInTheDocument();
  });
});

describe("WaferMap die selection", () => {
  it("does not render die investigation recommendation panel when selecting a failed die", () => {
    const data = waferMapFixture();
    render(<WaferMap data={data} catalog={CATALOG} selectedLotId="L001" />);

    // Click on D049 FAIL
    fireEvent.click(screen.getByLabelText("Die D049 FAIL X 9 Y 5"));
    expect(screen.queryByTestId("die-recommendation-panel")).not.toBeInTheDocument();
  });
});
