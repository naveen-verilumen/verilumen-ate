import type { TestCatalogEntry } from "../types/api";
import { formatCount } from "./format";
import { formatTestLabel, replaceTestIdsInText } from "./formatTestLabel";

const TITLES: Record<string, string> = {
  "PROCESS.LOT_VARIATION": "Lot Variation",
  "PARAMETRIC.SHIFT": "Parametric Shift",
  "PROCESS.WAFER_VARIATION": "Wafer Variation",
  "TEST.LIMIT_SENSITIVITY": "Test Limit Sensitivity",
  "SPATIAL.EDGE": "Wafer Edge",
  "SPATIAL.CENTER": "Wafer Center",
  "SPATIAL.BORDER": "Wafer Border",
  "SPATIAL.INNER": "Wafer Interior",
  "SPATIAL.RING": "Radial Ring",
  "PROCESS.DRIFT": "Process Drift",
  "EQUIPMENT.DEGRADATION": "Equipment Variation",
  "ENVIRONMENT.TEMPERATURE": "Temperature",
  "TEST.SEQUENCE": "Test Sequence",
  "CONTACT.PROBE": "Probe Contact",
  "CORRELATED.FAILURES": "Correlated Failures",
};

const NEXT_STEPS: Record<string, string> = {
  "PROCESS.LOT_VARIATION": "Check whether the same pattern appears in other lots.",
  "PARAMETRIC.SHIFT": "Verify the shifted parameter's measurement coverage.",
  "PROCESS.WAFER_VARIATION": "Check whether the same pattern appears on other wafers.",
  "TEST.LIMIT_SENSITIVITY": "Verify the relevant test-limit information.",
  "SPATIAL.EDGE": "Confirm the map pattern on additional lots and wafers.",
  "SPATIAL.CENTER": "Confirm the map pattern on additional lots and wafers.",
  "SPATIAL.BORDER": "Confirm the map pattern on additional lots and wafers.",
  "SPATIAL.INNER": "Confirm the map pattern on additional lots and wafers.",
  "SPATIAL.RING": "Confirm the map pattern on additional lots and wafers.",
  "PROCESS.DRIFT": "Check process or recipe changes near the time window.",
  "EQUIPMENT.DEGRADATION": "Compare matched lots run on the associated equipment versus controls.",
  "ENVIRONMENT.TEMPERATURE": "Repeat under matched temperature conditions across lots and equipment.",
  "TEST.SEQUENCE": "Confirm the sequence pattern under controlled execution.",
  "CONTACT.PROBE": "Compare probe cards / contact hardware on matched lots.",
  "CORRELATED.FAILURES": "Confirm co-occurrence on an independent sample.",
};

function identityKey(family: string, detail: string): string {
  return `${family}.${detail}`;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function titleCaseWords(raw: string): string {
  return raw
    .toLowerCase()
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function displayLotName(lotId: string): string {
  const text = lotId.trim();
  if (/^[Ll]\d+$/.test(text)) {
    return `LOT ${String(Number(text.slice(1))).padStart(3, "0")}`;
  }
  return text;
}

function formatLotToken(raw: string): string {
  if (raw.includes("/")) {
    const [lotRaw, waferId] = raw.split("/", 2);
    const parts = [formatLotToken(lotRaw)];
    if (waferId) {
      parts.push(waferId);
    }
    return parts.join(" / ");
  }
  return displayLotName(raw);
}

export function hypothesisTitle(family: string, detail: string): string {
  const known = TITLES[identityKey(family, detail)];
  if (known) {
    return known;
  }
  return titleCaseWords(detail || family);
}

export function confidenceLabel(evidenceTier: string): string {
  if (evidenceTier === "STRONG_EVIDENCE") {
    return "High";
  }
  if (evidenceTier === "MODERATE_EVIDENCE") {
    return "Moderate";
  }
  if (evidenceTier === "WEAK_EVIDENCE" || evidenceTier === "INSUFFICIENT_EVIDENCE") {
    return "Low";
  }
  return "Moderate";
}

function populationComparison(value: Record<string, unknown> | null): string | null {
  if (!value) {
    return null;
  }
  const comparison = asString(value.comparison);
  if (comparison?.includes(":")) {
    return comparison;
  }
  const label = asString(value.label);
  if (label?.includes(":")) {
    return label;
  }
  return comparison;
}

function populationGroup(value: Record<string, unknown> | null): string | null {
  if (!value) {
    return null;
  }
  const comparison = populationComparison(value);
  if (comparison?.includes(":")) {
    return comparison.split(":").slice(1).join(":");
  }
  return asString(value.group) ?? asString(value.label) ?? asString(value.grain) ?? comparison;
}

function populationParameter(value: Record<string, unknown> | null): string | null {
  if (!value) {
    return null;
  }
  const comparison = populationComparison(value);
  if (comparison?.includes(":")) {
    return comparison.split(":")[0] ?? null;
  }
  return asString(value.parameter) ?? asString(value.parameter_name);
}

function populationWafer(group: string | null): string | null {
  if (!group?.includes("/")) {
    return null;
  }
  return group.split("/")[1] ?? null;
}

function scopeParts(
  value: Record<string, unknown> | null,
  catalog: TestCatalogEntry[] | undefined,
  lotDisplay: string | null | undefined,
): string[] {
  const parts: string[] = [];
  if (lotDisplay) {
    parts.push(lotDisplay);
  }
  const group = populationGroup(value);
  const parameter = populationParameter(value);
  const wafer = populationWafer(group);
  if (wafer) {
    if (!lotDisplay && group) {
      return [formatLotToken(group)];
    }
    parts.push(wafer);
  } else if (parameter) {
    if (!lotDisplay && group) {
      parts.push(formatLotToken(group));
    }
    parts.push(parameter);
  } else if (group && !lotDisplay) {
    if (group === "edge" || group === "center" || group === "border" || group === "inner" || group === "ring") {
      parts.push(group);
    } else if (looksLikeLotId(group) || group.includes("/")) {
      parts.push(formatLotToken(group));
    }
  }
  const testId = asString(value?.test_id) ?? asString(value?.affected_test) ?? asString(value?.failure_key);
  if (testId && testId !== group && testId !== parameter && !parts.includes(testId)) {
    parts.push(formatTestLabel(testId, catalog));
  }
  return parts;
}

export function affectedPopulationLabel(
  value: Record<string, unknown> | null,
  catalog: TestCatalogEntry[] | undefined,
  lotDisplay?: string | null,
): string {
  if (!value && !lotDisplay) {
    return "Unavailable";
  }
  const n = value ? (asNumber(value.n) ?? asNumber(value.count) ?? asNumber(value.n_dies)) : null;
  const parts = scopeParts(value, catalog, lotDisplay);
  if (n !== null) {
    if (parts.length > 0) {
      return `${parts.join(" / ")} — ${formatCount(n)} dies`;
    }
    return `${formatCount(n)} dies`;
  }
  if (parts.length > 0) {
    return parts.join(" / ");
  }
  if (!value) {
    return lotDisplay ?? "Unavailable";
  }
  try {
    return replaceTestIdsInText(JSON.stringify(value), catalog);
  } catch {
    return "Unavailable";
  }
}

function looksLikeLotId(raw: string | null): boolean {
  if (!raw) {
    return false;
  }
  const lotPart = raw.includes("/") ? (raw.split("/")[0] ?? "") : raw;
  return /^[Ll]\d+$/.test(lotPart);
}

export function findingText(
  family: string,
  detail: string,
  statement: string,
  affected: Record<string, unknown> | null,
  catalog: TestCatalogEntry[] | undefined,
  lotDisplay?: string | null,
): string {
  const key = identityKey(family, detail);
  const group = populationGroup(affected);
  const parameter = populationParameter(affected);
  const wafer = populationWafer(group);
  const lotFromGroup = group && !wafer && !parameter && looksLikeLotId(group) ? formatLotToken(group) : null;
  const lotFromWaferGroup = group?.includes("/") && looksLikeLotId(group) ? formatLotToken(group.split("/")[0] ?? "") : null;
  const scopedLot = lotDisplay ?? (parameter && group && looksLikeLotId(group) ? formatLotToken(group) : null) ?? lotFromWaferGroup ?? lotFromGroup;

  if (key === "PROCESS.LOT_VARIATION" && scopedLot) {
    return `${scopedLot} has higher yield loss than other lots.`;
  }
  if (key === "PROCESS.WAFER_VARIATION" && (wafer || group)) {
    const waferLabel = wafer ?? group;
    if (scopedLot) {
      return `${waferLabel} has higher failure than the other wafers in ${scopedLot}.`;
    }
    return `${group} has higher yield loss than other wafers.`;
  }
  if (key === "PARAMETRIC.SHIFT" && parameter && scopedLot) {
    return `${parameter} measurements are shifted in ${scopedLot}.`;
  }
  if (key === "PARAMETRIC.SHIFT" && parameter) {
    return `${parameter} measurements are shifted.`;
  }
  if (key === "TEST.LIMIT_SENSITIVITY") {
    if (lotDisplay || (scopedLot && looksLikeLotId(group))) {
      return `Some failures in ${lotDisplay ?? scopedLot} occur close to a test limit.`;
    }
    return "Some failures occur close to a test limit.";
  }
  if (key === "SPATIAL.EDGE") {
    return "Yield loss is higher at the wafer edge.";
  }
  if (key === "PROCESS.DRIFT") {
    return "Yield loss increased over time.";
  }
  if (key === "EQUIPMENT.DEGRADATION" && group) {
    return `${group} has higher yield loss than other equipment.`;
  }
  return replaceTestIdsInText(statement, catalog);
}

export function nextInvestigationStep(
  family: string,
  detail: string,
  validationSteps: string[],
  catalog: TestCatalogEntry[] | undefined,
  affected?: Record<string, unknown> | null,
): string {
  const key = identityKey(family, detail);
  if (key === "PARAMETRIC.SHIFT") {
    const parameter = populationParameter(affected ?? null);
    if (parameter) {
      return `Verify ${parameter} measurement coverage.`;
    }
  }
  const mapped = NEXT_STEPS[key];
  if (mapped) {
    return mapped;
  }
  if (validationSteps[0]) {
    return replaceTestIdsInText(validationSteps[0], catalog);
  }
  return "Additional data or investigation is required.";
}
