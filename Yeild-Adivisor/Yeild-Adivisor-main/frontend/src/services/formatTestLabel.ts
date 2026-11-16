import type { TestCatalogEntry } from "../types/api";

const TEST_ID_RE = /^T\d{3}$/;
const TEST_ID_TOKEN_RE = /\bT\d{3}\b/gi;
const NO_SEMANTIC_NAME = "No semantic test name defined in V2 source";

/** Generator program-slot names from configs/synthetic_v2.yaml tests[].failure_code. */
const V2_GENERATOR_SLOTS = JSON.parse(
  '{"T001":"CONTINUITY","T002":"OPENS","T003":"SHORTS","T004":"CONTACT","T005":"IDDQ","T006":"VMIN","T007":"VMAX","T008":"LEAKAGE","T009":"FUNCTIONAL","T010":"SCAN"}',
) as Record<string, string>;

export function normalizeTestId(testId: string): string {
  const key = testId.trim().toUpperCase();
  return TEST_ID_RE.test(key) ? key : testId.trim();
}

export function catalogEntries(catalog: TestCatalogEntry[] | { tests?: TestCatalogEntry[] } | undefined | null): TestCatalogEntry[] {
  if (!catalog) {
    return [];
  }
  if (Array.isArray(catalog)) {
    return catalog;
  }
  if (Array.isArray(catalog.tests)) {
    return catalog.tests;
  }
  return [];
}

export function catalogById(catalog: TestCatalogEntry[] | undefined | null): Map<string, TestCatalogEntry> {
  const map = new Map<string, TestCatalogEntry>();
  for (const entry of catalog ?? []) {
    if (entry.test_id) {
      map.set(normalizeTestId(entry.test_id), entry);
    }
  }
  return map;
}

export function formatTestLabel(testId: string, catalog: TestCatalogEntry[] | undefined | null): string {
  const key = normalizeTestId(testId);
  const generatorSlot = V2_GENERATOR_SLOTS[key];
  if (generatorSlot) {
    return `${key} — ${generatorSlot}`;
  }
  const entry = catalogById(catalog).get(key);
  if (entry?.display_label) {
    const parts = entry.display_label.split("—");
    const name = parts.length > 1 ? parts[parts.length - 1].trim() : "";
    if (name && name !== "UNCLASSIFIED" && !/unclassified/i.test(name)) {
      return `${key} — ${name}`;
    }
  }
  if (entry?.test_name && entry.test_name !== "UNCLASSIFIED" && !/unclassified/i.test(entry.test_name)) {
    return `${entry.test_id} — ${entry.test_name}`;
  }
  if (TEST_ID_RE.test(key)) {
    return `${key} — ${NO_SEMANTIC_NAME}`;
  }
  return key;
}

export function extractAffectedTestId(population: Record<string, unknown> | null | undefined): string | null {
  if (!population) {
    return null;
  }
  for (const key of ["test_id", "affected_test", "failure_key", "grain", "group", "label"]) {
    const value = population[key];
    if (typeof value === "string" && TEST_ID_RE.test(normalizeTestId(value))) {
      return normalizeTestId(value);
    }
  }
  return null;
}

export function replaceTestIdsInText(text: string, catalog: TestCatalogEntry[] | undefined | null): string {
  return text.replace(TEST_ID_TOKEN_RE, (token) => formatTestLabel(token, catalog));
}
