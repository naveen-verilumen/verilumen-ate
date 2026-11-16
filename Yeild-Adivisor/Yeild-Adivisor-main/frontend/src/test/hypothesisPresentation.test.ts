import { describe, expect, it } from "vitest";
import {
  affectedPopulationLabel,
  confidenceLabel,
  findingText,
  hypothesisTitle,
  nextInvestigationStep,
} from "../services/hypothesisPresentation";

describe("hypothesis presentation", () => {
  it("uses plain-language titles instead of internal identity codes", () => {
    expect(hypothesisTitle("PROCESS", "LOT_VARIATION")).toBe("Lot Variation");
    expect(hypothesisTitle("PARAMETRIC", "SHIFT")).toBe("Parametric Shift");
    expect(hypothesisTitle("PROCESS", "WAFER_VARIATION")).toBe("Wafer Variation");
    expect(hypothesisTitle("TEST", "LIMIT_SENSITIVITY")).toBe("Test Limit Sensitivity");
  });

  it("maps evidence tiers to confidence without exposing internal codes", () => {
    expect(confidenceLabel("MODERATE_EVIDENCE")).toBe("Moderate");
    expect(confidenceLabel("STRONG_EVIDENCE")).toBe("High");
    expect(confidenceLabel("WEAK_EVIDENCE")).toBe("Low");
  });

  it("states findings from affected population without calling them a root cause", () => {
    expect(
      findingText("PROCESS", "LOT_VARIATION", "internal", { group: "L004", n: 500 }, []),
    ).toBe("LOT 004 has higher yield loss than other lots.");
    expect(
      findingText("PARAMETRIC", "SHIFT", "internal", { comparison: "VMIN:L004", n: 500 }, []),
    ).toBe("VMIN measurements are shifted in LOT 004.");
    expect(
      findingText("PARAMETRIC", "SHIFT", "internal", { label: "VMIN:L004", n: 500 }, []),
    ).toBe("VMIN measurements are shifted in LOT 004.");
    expect(
      findingText("PROCESS", "WAFER_VARIATION", "internal", { group: "L004/W05", n: 100 }, []),
    ).toBe("W05 has higher failure than the other wafers in LOT 004.");
    expect(findingText("TEST", "LIMIT_SENSITIVITY", "internal", { n: 299 }, [])).toBe(
      "Some failures occur close to a test limit.",
    );
    expect(
      findingText("TEST", "LIMIT_SENSITIVITY", "internal", { n: 299 }, [], "LOT 004"),
    ).toBe("Some failures in LOT 004 occur close to a test limit.");
  });

  it("formats affected populations as location plus die count", () => {
    expect(affectedPopulationLabel({ group: "L004", n: 500 }, [])).toBe("LOT 004 — 500 dies");
    expect(affectedPopulationLabel({ group: "L004/W05", n: 100 }, [])).toBe("LOT 004 / W05 — 100 dies");
    expect(affectedPopulationLabel({ comparison: "VMIN:L004", n: 500 }, [])).toBe("LOT 004 / VMIN — 500 dies");
    expect(affectedPopulationLabel({ label: "VMIN:L004", n: 500 }, [])).toBe("LOT 004 / VMIN — 500 dies");
    expect(affectedPopulationLabel({ n: 299 }, [])).toBe("299 dies");
    expect(affectedPopulationLabel({ n: 299 }, [], "LOT 004")).toBe("LOT 004 — 299 dies");
  });

  it("provides a simple next investigation step", () => {
    expect(nextInvestigationStep("PROCESS", "LOT_VARIATION", [], [])).toBe(
      "Check whether the same pattern appears in other lots.",
    );
    expect(nextInvestigationStep("PROCESS", "WAFER_VARIATION", [], [])).toBe(
      "Check whether the same pattern appears on other wafers.",
    );
    expect(
      nextInvestigationStep("PARAMETRIC", "SHIFT", [], [], { comparison: "VMIN:L004", n: 500 }),
    ).toBe("Verify VMIN measurement coverage.");
    expect(
      nextInvestigationStep("PARAMETRIC", "SHIFT", [], [], { label: "VMIN:L004", n: 500 }),
    ).toBe("Verify VMIN measurement coverage.");
  });
});
