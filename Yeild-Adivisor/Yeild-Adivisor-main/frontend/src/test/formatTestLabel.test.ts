import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { formatTestLabel } from "../services/formatTestLabel";
import type { TestCatalogEntry } from "../types/api";
import { V2_DISPLAY_LABELS, V2_TEST_CATALOG_TESTS, WITHDRAWN_OVERLAY_NAMES } from "./v2TestCatalog";

function collectSourceFiles(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "test" || name === "node_modules") {
      continue;
    }
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      collectSourceFiles(path, acc);
      continue;
    }
    if (/\.(ts|tsx)$/.test(name)) {
      acc.push(path);
    }
  }
  return acc;
}

describe("formatTestLabel", () => {
  it("maps every V2 test id through the API catalog to the generator program slot", () => {
    for (const [testId, label] of Object.entries(V2_DISPLAY_LABELS)) {
      expect(formatTestLabel(testId, V2_TEST_CATALOG_TESTS)).toBe(label);
    }
  });

  it("maps all ten V2 ids to generator program slots even when catalog test_type is wrong", () => {
    const expected: Record<string, string> = {
      T001: "T001 — CONTINUITY",
      T002: "T002 — OPENS",
      T003: "T003 — SHORTS",
      T004: "T004 — CONTACT",
      T005: "T005 — IDDQ",
      T006: "T006 — VMIN",
      T007: "T007 — VMAX",
      T008: "T008 — LEAKAGE",
      T009: "T009 — FUNCTIONAL",
      T010: "T010 — SCAN",
    };
    const stale: TestCatalogEntry[] = [
      { test_id: "T001", test_name: "Continuity / Open-Short Test", test_type: "CONTINUITY_OPEN_SHORT", display_label: "T001 — Continuity / Open-Short Test" },
      { test_id: "T002", test_name: "DC Parametric Test", test_type: "DC_PARAMETRIC", display_label: "T002 — DC Parametric Test" },
      { test_id: "T003", test_name: "Leakage Test", test_type: "LEAKAGE", display_label: "T003 — Leakage Test" },
      { test_id: "T004", test_name: "Functional Test", test_type: "FUNCTIONAL", display_label: "T004 — Functional Test" },
      { test_id: "T005", test_name: "Timing / AC Test", test_type: "TIMING_AC", display_label: "T005 — Timing / AC Test" },
      { test_id: "T006", test_name: "Power / Thermal Test", test_type: "POWER_THERMAL", display_label: "T006 — Power / Thermal Test" },
      { test_id: "T007", test_name: "Unclassified V2 Test", test_type: "UNCLASSIFIED", display_label: "T007 — Unclassified V2 Test" },
      { test_id: "T008", test_name: "Unclassified V2 Test", test_type: "UNCLASSIFIED", display_label: "T008 — Unclassified V2 Test" },
      { test_id: "T009", test_name: "Unclassified V2 Test", test_type: "UNCLASSIFIED", display_label: "T009 — Unclassified V2 Test" },
      { test_id: "T010", test_name: "Unclassified V2 Test", test_type: "UNCLASSIFIED", display_label: "T010 — Unclassified V2 Test" },
    ];
    for (const [testId, label] of Object.entries(expected)) {
      expect(formatTestLabel(testId, stale)).toBe(label);
      expect(formatTestLabel(testId.toLowerCase(), stale)).toBe(label);
      expect(formatTestLabel(` ${testId} `, [])).toBe(label);
    }
    expect(formatTestLabel("T004", stale)).not.toBe("T004 — FUNCTIONAL");
    expect(formatTestLabel("T003", stale)).not.toBe("T003 — LEAKAGE");
    expect(formatTestLabel("T007", stale)).not.toMatch(/UNCLASSIFIED/i);
  });

  it("ignores withdrawn overlay catalog names for T001–T010", () => {
    const stale = V2_TEST_CATALOG_TESTS.map((row, index) => ({
      ...row,
      test_name: WITHDRAWN_OVERLAY_NAMES[index % WITHDRAWN_OVERLAY_NAMES.length],
      test_type: WITHDRAWN_OVERLAY_NAMES[index % WITHDRAWN_OVERLAY_NAMES.length],
      display_label: `${row.test_id} — ${WITHDRAWN_OVERLAY_NAMES[index % WITHDRAWN_OVERLAY_NAMES.length]}`,
    }));
    expect(formatTestLabel("T001", stale)).toBe("T001 — CONTINUITY");
    expect(formatTestLabel("T004", stale)).toBe("T004 — CONTACT");
    expect(formatTestLabel("T005", stale)).toBe("T005 — IDDQ");
    expect(formatTestLabel("T006", stale)).toBe("T006 — VMIN");
    expect(formatTestLabel("T010", stale)).toBe("T010 — SCAN");
  });

  it("does not invent Unclassified V2 Test when a Txxx id is missing from the catalog", () => {
    expect(formatTestLabel("T099", [])).toBe("T099 — No semantic test name defined in V2 source");
    expect(formatTestLabel("T099", [])).not.toMatch(/Unclassified V2 Test/);
  });

  it("leaves non-test keys unchanged", () => {
    expect(formatTestLabel("CONTACT_FAIL", V2_TEST_CATALOG_TESTS)).toBe("CONTACT_FAIL");
  });

  it("does not hard-code withdrawn overlay names or a second T00x map in production source", () => {
    const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
    const files = collectSourceFiles(srcRoot);
    const production = files.filter((path) => !path.includes(`${join("src", "test")}`) && !path.endsWith("v2TestCatalog.ts"));
    expect(production.length).toBeGreaterThan(0);
    let mappingCopies = 0;
    for (const path of production) {
      const text = readFileSync(path, "utf8");
      for (const name of WITHDRAWN_OVERLAY_NAMES) {
        expect(text, path).not.toContain(name);
      }
      if (text.includes("T001") && text.includes("CONTINUITY") && /T001\s*[:=].*CONTINUITY/.test(text)) {
        mappingCopies += 1;
      }
    }
    expect(mappingCopies).toBe(0);
    expect(readFileSync(join(srcRoot, "services", "formatTestLabel.ts"), "utf8")).toContain("formatTestLabel");
  });
});
