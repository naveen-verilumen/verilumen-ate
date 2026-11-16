import type { TestCatalogEntry, TestCatalogPayload } from "../types/api";

/** API-shaped V2 catalog for tests. Production display still comes from GET test_catalog. */
const V2_SLOTS: ReadonlyArray<readonly [string, string]> = [
  ["T001", "CONTINUITY"],
  ["T002", "OPENS"],
  ["T003", "SHORTS"],
  ["T004", "CONTACT"],
  ["T005", "IDDQ"],
  ["T006", "VMIN"],
  ["T007", "VMAX"],
  ["T008", "LEAKAGE"],
  ["T009", "FUNCTIONAL"],
  ["T010", "SCAN"],
];

export const V2_TEST_CATALOG_TESTS: TestCatalogEntry[] = V2_SLOTS.map(([test_id, test_name]) => ({
  test_id,
  test_name,
  test_type: test_name,
  display_label: `${test_id} — ${test_name}`,
}));

export const V2_TEST_CATALOG: TestCatalogPayload = {
  catalog_id: "yi_v2_test_catalog",
  catalog_version: "yi_v2_test_catalog_v2",
  dataset_id: "yi_synthetic_v2",
  source: "SYNTHETIC_V2_GENERATOR_PROGRAM_SLOTS",
  tests: V2_TEST_CATALOG_TESTS,
};

export const V2_DISPLAY_LABELS: Record<string, string> = Object.fromEntries(
  V2_TEST_CATALOG_TESTS.map((row) => [row.test_id, row.display_label ?? `${row.test_id} — ${row.test_name}`]),
);

export const V2_PRIMARY_PARETO_COUNTS: Array<[string, number]> = [
  ["T004", 92],
  ["T006", 39],
  ["T005", 38],
  ["T001", 17],
  ["T002", 13],
  ["T007", 12],
  ["T009", 12],
  ["T003", 10],
  ["T008", 9],
  ["T010", 9],
];

export const WITHDRAWN_OVERLAY_NAMES = [
  "Unclassified V2 Test",
  "Functional Test",
  "Timing / AC Test",
  "Power / Thermal Test",
  "Continuity / Open-Short Test",
  "DC Parametric Test",
  "Leakage Test",
];
