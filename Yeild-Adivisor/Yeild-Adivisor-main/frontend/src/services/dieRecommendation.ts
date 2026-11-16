import type {
  DieRecommendation,
  ParametricAnalysisReport,
  TestCatalogEntry,
  WaferMapDie,
} from "../types/api";

const SAFETY_BANNER = "INVESTIGATION ONLY — PRODUCTION ACTION FORBIDDEN";
const PRODUCTION_LIMIT_UNAVAILABLE =
  "Approved production limit: Unavailable — authoritative specification not provided.";

/**
 * Authoritative mapping from primary failure code to parametric measurement name.
 */
export const FAILURE_CODE_TO_PARAMETER: Record<string, string> = {
  IDDQ: "IDDQ",
  VMIN: "VMIN",
  CONTACT: "CONTACT_RESISTANCE",
  LEAKAGE: "SUPPLY_CURRENT",
  VMAX: "VMAX",
};

/**
 * Authoritative units per parameter when not reported by parametric analysis.
 */
export const PARAMETER_DEFAULT_UNITS: Record<string, string> = {
  IDDQ: "µA",
  VMIN: "V",
  VMAX: "V",
  VDD: "V",
  SUPPLY_CURRENT: "mA",
  CONTACT_RESISTANCE: "ohm",
  INTERCONNECT_RESISTANCE: "ohm",
  ON_RESISTANCE: "ohm",
};

/**
 * Evaluates whether an actual measurement crosses the candidate boundary.
 * - UPPER_BOUND: Exceeds when measured > boundary
 * - LOWER_BOUND: Exceeds when measured < boundary
 * - BAND: Not typically single-directional candidate; evaluates difference
 */
export function evaluateBoundaryCrossing(
  measured: number,
  boundary: number,
  direction: string | null | undefined
): boolean {
  if (direction === "LOWER_BOUND") {
    return measured < boundary;
  }
  // Default and UPPER_BOUND:
  return measured > boundary;
}

/**
 * Pure function to generate a die-specific engineering investigation recommendation.
 */
export function generateDieRecommendation(
  die: WaferMapDie | null | undefined,
  parametricReport?: ParametricAnalysisReport | null,
  catalog?: TestCatalogEntry[]
): DieRecommendation | null {
  if (!die) {
    return null;
  }

  // 1. If passing die, no failure recommendation panel is displayed
  if (die.first_pass_result === "PASS") {
    return {
      status: "PASSING_DIE",
      primary_failure_code: null,
      failed_test_id: null,
      parameter_name: null,
      unit: null,
      actual_measured_value: null,
      candidate_boundary: null,
      candidate_direction: null,
      candidate_status: null,
      signed_difference: null,
      exceeds_candidate_boundary: null,
      approved_production_limit_status: "Nominal first-pass pass.",
      recommended_investigation_steps: [],
      evidence_limitations: [],
      missing_evidence: [],
      safety_banner: SAFETY_BANNER,
    };
  }

  const failureCode = die.failure_code ? die.failure_code.trim() : null;
  const failedTestId = die.failed_test_id ?? null;

  // 2. Identify mapped parameter from registry
  const paramName = failureCode ? FAILURE_CODE_TO_PARAMETER[failureCode] : null;

  // 3. Handle non-parametric failures (e.g. CONTINUITY, OPENS, SHORTS, SCAN, FUNCTIONAL)
  if (!failureCode || !paramName) {
    return {
      status: "NON_PARAMETRIC_FAILURE",
      primary_failure_code: failureCode,
      failed_test_id: failedTestId,
      parameter_name: null,
      unit: null,
      actual_measured_value: null,
      candidate_boundary: null,
      candidate_direction: null,
      candidate_status: null,
      signed_difference: null,
      exceeds_candidate_boundary: null,
      approved_production_limit_status: PRODUCTION_LIMIT_UNAVAILABLE,
      recommended_investigation_steps: [
        `Failure mode ${failureCode || "UNKNOWN"} does not map to a continuous parametric measurement rail.`,
        "Inspect test hardware setup, probe card contact resistance, and fixture alignment.",
        "Review vector sequence execution logs and scan chain diagnostic traces.",
      ],
      evidence_limitations: [
        "Continuous parametric distribution analysis is not applicable for structural/functional vector failures.",
      ],
      missing_evidence: [
        `No continuous parametric measurement mapped for failure code '${failureCode || "UNKNOWN"}'.`,
      ],
      safety_banner: SAFETY_BANNER,
    };
  }

  // 4. Retrieve actual measured value for the selected physical die
  const measurements = die.measurements ?? {};
  const hasMeasurementEntry = Object.prototype.hasOwnProperty.call(measurements, paramName);
  const actualValue = measurements[paramName];

  // If measurement record is missing or null, fail closed
  if (!hasMeasurementEntry || actualValue === null || actualValue === undefined || isNaN(actualValue)) {
    return {
      status: "MISSING_MEASUREMENT",
      primary_failure_code: failureCode,
      failed_test_id: failedTestId,
      parameter_name: paramName,
      unit: null,
      actual_measured_value: null,
      candidate_boundary: null,
      candidate_direction: null,
      candidate_status: null,
      signed_difference: null,
      exceeds_candidate_boundary: null,
      approved_production_limit_status: PRODUCTION_LIMIT_UNAVAILABLE,
      recommended_investigation_steps: [
        `Verify ATE test datalog integrity for physical die ${die.die_id} on wafer ${die.wafer_id}.`,
        "Check whether sequence abort or test timeout prevented logging of parametric value.",
      ],
      evidence_limitations: [
        "Missing empirical measurement on selected physical die record.",
      ],
      missing_evidence: [
        `Die ${die.die_id} has no valid measurement recorded for parameter '${paramName}'.`,
      ],
      safety_banner: SAFETY_BANNER,
    };
  }

  // 5. Look up parameter result from existing parametric analysis report
  const paramResult = parametricReport?.results?.find(
    (r) => r.parameter_name === paramName
  );

  let rawUnit = paramResult?.unit || PARAMETER_DEFAULT_UNITS[paramName] || "";
  if (rawUnit === "uA") {
    rawUnit = "µA";
  }
  const unit = rawUnit;
  const candidate = paramResult?.candidate_threshold;
  const candidateStatus = paramResult?.threshold_status ?? "NO_THRESHOLD_ESTABLISHED";

  // 6. Handle case where parameter has no established candidate threshold (e.g. VMAX, SUPPLY_CURRENT)
  if (!candidate || candidateStatus !== "INVESTIGATION_CANDIDATE_ONLY" || candidate.candidate_value === null) {
    return {
      status: "INSUFFICIENT_EVIDENCE",
      primary_failure_code: failureCode,
      failed_test_id: failedTestId,
      parameter_name: paramName,
      unit,
      measurement_semantics: paramResult?.measurement_semantics,
      actual_measured_value: actualValue,
      candidate_boundary: null,
      candidate_direction: null,
      candidate_status: "INSUFFICIENT_EVIDENCE",
      signed_difference: null,
      exceeds_candidate_boundary: null,
      approved_production_limit_status: PRODUCTION_LIMIT_UNAVAILABLE,
      recommended_investigation_steps: [
        `Selected physical die recorded actual ${paramName} = ${actualValue} ${unit}.`,
        "No statistically valid candidate investigation boundary established (INSUFFICIENT_EVIDENCE).",
        "Investigate failure against approved engineering test specification and ATE hardware limits.",
        "Check probe interface and bias stability under test execution.",
      ],
      evidence_limitations: [
        "Distribution separation for this parameter did not meet statistical criteria for establishing an empirical candidate threshold.",
        "Candidate boundary cannot be inferred or fabricated.",
      ],
      missing_evidence: [
        `No established candidate threshold for parameter '${paramName}'.`,
      ],
      safety_banner: SAFETY_BANNER,
    };
  }

  // 7. Full actionable comparison with candidate boundary
  const candidateVal = candidate.candidate_value;
  const direction = candidate.direction;
  const signedDiff = actualValue - candidateVal;
  const exceeds = evaluateBoundaryCrossing(actualValue, candidateVal, direction);

  const directionLabel = direction === "LOWER_BOUND" ? "lower candidate boundary (<)" : "upper candidate boundary (>)";
  const comparisonText = exceeds
    ? `Measurement lies beyond the ${directionLabel} by ${Math.abs(signedDiff).toFixed(4)} ${unit}.`
    : `Measurement is within the ${directionLabel} by ${Math.abs(signedDiff).toFixed(4)} ${unit}.`;

  const steps = [
    `Verify physical die ${die.die_id} measurement validity (${actualValue} ${unit}).`,
    `Compare with empirical boundary (${candidateVal} ${unit}): ${comparisonText}`,
    "Inspect ATE test conditions, pin contact integrity, and temperature stability during test execution.",
    "Investigate underlying semiconductor electrical root cause (e.g., bridging, gate oxide leakage, subthreshold shift).",
    "Review approved production specification before considering any disposition or test program changes.",
  ];

  const limitations = [
    "Association with an exploratory candidate boundary does not establish root cause.",
    "Candidate boundaries are exploratory statistical artifacts derived from first-pass test logs.",
    "Candidate boundary must never be treated as an approved production limit.",
    "Do not alter production limits to force a failing die to pass.",
  ];

  return {
    status: "ACTIONABLE_CANDIDATE_COMPARISON",
    primary_failure_code: failureCode,
    failed_test_id: failedTestId,
    parameter_name: paramName,
    unit,
    measurement_semantics: paramResult.measurement_semantics,
    actual_measured_value: actualValue,
    candidate_boundary: candidateVal,
    candidate_direction: direction,
    candidate_status: "INVESTIGATION_CANDIDATE_ONLY",
    signed_difference: signedDiff,
    exceeds_candidate_boundary: exceeds,
    approved_production_limit_status: PRODUCTION_LIMIT_UNAVAILABLE,
    recommended_investigation_steps: steps,
    evidence_limitations: limitations,
    missing_evidence: [],
    safety_banner: SAFETY_BANNER,
  };
}
