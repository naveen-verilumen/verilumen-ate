import type {
  DashboardResponse,
  RecommendationBundle,
  ReportEvidenceFinding,
  ReportHypothesis,
  ReportInvestigationItem,
  ReportOpportunity,
  ReportParetoRow,
  TestCatalogEntry,
} from "../types/api";

import { formatCount, formatRate, formatSignedRate } from "./format";
import { catalogEntries, formatTestLabel, replaceTestIdsInText } from "./formatTestLabel";
import {
  affectedPopulationLabel,
  confidenceLabel,
  displayLotName,
  findingText,
  hypothesisTitle,
  nextInvestigationStep,
} from "./hypothesisPresentation";

export type AnalysisStatus =
  | "COMPLETE"
  | "NEEDS_MORE_DATA"
  | "INSUFFICIENT_DATA"
  | "ML_DEGRADED"
  | "NO_CONFIDENT_HYPOTHESIS";

export type DataQualityState = "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "NEEDS_MORE_DATA";

export interface ParetoDisplayRow {
  failureKey: string;
  displayLabel: string;
  family: string | null;
  detail: string | null;
  affectedDies: number;
  affectedDiesLabel: string;
  percentageOfEligibleLabel: string;
  shareOfFailsLabel: string;
  shareOfFailsPct: number;
  taxonomyCode: string | null;
}

export interface EvidenceDisplayRow {
  signal: string;
  detector: string;
  population: string;
  effect: string;
  status: string;
  sampleSize: string;
  method: string;
  pValue: string;
  adjustedPValue: string;
  dataGaps: string[];
}

export interface HypothesisCardModel {
  rank: number;
  hypothesisId: string;
  title: string;
  finding: string;
  affectedPopulation: string;
  confidence: string;
  nextStep: string;
  family: string;
  detail: string;
}

export interface OpportunityDisplayRow {
  id: string;
  title: string;
  potential: string;
}

export interface DashboardViewModel {
  datasetId: string;
  selectedLotId: string | null;
  selectedLotDisplay: string | null;
  findingsTitle: string;
  opportunityTitle: string;
  generatedAt: string;
  analysisStatus: AnalysisStatus;
  kpis: {
    fpy: string;
    fpyLoss: string;
    eligibleDies: string;
    firstPassPass: string;
    firstPassFail: string;
  };
  leadingCandidate: HypothesisCardModel | null;
  noConfidentHypothesis: boolean;
  noSignalHeadline: string | null;
  noActionableNotice: string | null;
  primaryFailureLabel: string | null;
  pareto: ParetoDisplayRow[];
  primaryUnavailableNote: string | null;
  evidence: EvidenceDisplayRow[];
  hypotheses: HypothesisCardModel[];
  investigationSteps: string[];
  investigationItems: ReportInvestigationItem[];
  opportunity: {
    fpy: string;
    fpyLoss: string;
    rows: OpportunityDisplayRow[];
    overlapNote: string;
  };
  dataQuality: {
    state: DataQualityState;
    required: string[];
    recommended: string[];
    detectorSpecific: string[];
  };
  notices: {
    nearLimit: string | null;
    sequenceCensoring: string | null;
  };
  safety: {
    productionAction: "FORBIDDEN";
    productionAuthorized: "NO";
    safetyEligible: "0";
    statement: string;
  };
  testCatalog: TestCatalogEntry[];
  recommendations?: RecommendationBundle | null;
}


const NO_SIGNAL = "No strong systematic signal was detected.";
const NEAR_LIMIT_HEADLINE = "Near-limit failure pattern detected.";

function labeledStrings(values: string[], catalog: TestCatalogEntry[] | undefined): string[] {
  return values.map((item) => replaceTestIdsInText(item, catalog));
}

function paretoRow(row: ReportParetoRow, catalog: TestCatalogEntry[] | undefined): ParetoDisplayRow {
  return {
    failureKey: row.failure_key,
    displayLabel: formatTestLabel(row.failure_key, catalog),
    family: row.family,
    detail: row.detail,
    affectedDies: row.affected_die_count,
    affectedDiesLabel: formatCount(row.affected_die_count),
    percentageOfEligibleLabel: formatRate(row.percentage_of_eligible),
    shareOfFailsLabel: formatRate(row.share_of_fails),
    shareOfFailsPct: row.share_of_fails * 100,
    taxonomyCode: row.taxonomy_code,
  };
}

function evidenceRow(item: ReportEvidenceFinding): EvidenceDisplayRow {
  const identity = item.family ? `${item.family}${item.detail ? `.${item.detail}` : ""}` : item.detector;
  const effect =
    item.effect_size === null
      ? "Unavailable"
      : `${formatSignedRate(item.effect_size)}${item.effect_size_metric ? ` (${item.effect_size_metric})` : ""}`;
  return {
    signal: identity,
    detector: item.detector,
    population: item.family ?? item.detector,
    effect,
    status: item.status,
    sampleSize: formatCount(item.sample_size),
    method: item.method,
    pValue: item.p_value === null ? "Unavailable" : String(item.p_value),
    adjustedPValue: item.adjusted_p_value === null ? "Unavailable" : String(item.adjusted_p_value),
    dataGaps: item.data_gaps,
  };
}

function isActionableFinding(item: ReportHypothesis): boolean {
  return item.evidence_tier !== "INSUFFICIENT_EVIDENCE" && item.association_class !== "INSUFFICIENT_EVIDENCE";
}

function hypothesisCard(
  item: ReportHypothesis,
  catalog: TestCatalogEntry[] | undefined,
  lotDisplay: string | null,
): HypothesisCardModel {
  return {
    rank: item.rank,
    hypothesisId: item.hypothesis_id,
    title: hypothesisTitle(item.family, item.detail),
    finding: findingText(item.family, item.detail, item.statement, item.affected_population, catalog, lotDisplay),
    affectedPopulation: affectedPopulationLabel(item.affected_population, catalog, lotDisplay),
    confidence: confidenceLabel(item.evidence_tier),
    nextStep: nextInvestigationStep(item.family, item.detail, item.validation_steps, catalog, item.affected_population),
    family: item.family,
    detail: item.detail,
  };
}

function opportunityRow(item: ReportOpportunity): OpportunityDisplayRow {
  const rate = item.observed_loss_rate ?? item.upper_bound_rate;
  return {
    id: item.opportunity_id,
    title: hypothesisTitle(item.family ?? "", item.detail ?? ""),
    potential: formatRate(rate),
  };
}

function dataQualityState(required: string[], recommended: string[], detectorSpecific: string[]): DataQualityState {
  if (required.length > 0) {
    return "NEEDS_MORE_DATA";
  }
  if (recommended.length > 0 || detectorSpecific.length > 0) {
    return "PARTIAL";
  }
  return "AVAILABLE";
}

function analysisStatus(payload: DashboardResponse): AnalysisStatus {
  const report = payload.report;
  if (report.fpy_summary.fpy === null) {
    return "INSUFFICIENT_DATA";
  }
  if (report.no_actionable_recommendation || report.hypotheses.length === 0) {
    return "NO_CONFIDENT_HYPOTHESIS";
  }
  if (report.data_gaps.required.length > 0) {
    return "NEEDS_MORE_DATA";
  }
  if (payload.health.reduced_ml_evidence) {
    return "ML_DEGRADED";
  }
  return "COMPLETE";
}

export function toDashboardViewModel(payload: DashboardResponse): DashboardViewModel {
  const report = payload.report;
  const catalog = catalogEntries(payload.test_catalog);
  const selectedLotId = payload.selected_lot_id?.trim() ? payload.selected_lot_id.trim() : null;
  const selectedLotDisplay = selectedLotId
    ? (payload.lots?.find((lot) => lot.lot_id === selectedLotId)?.display_name ??
      payload.selected_lot_display ??
      displayLotName(selectedLotId))
    : null;
  const hypotheses = [...report.hypotheses]
    .filter(isActionableFinding)
    .sort((a, b) => a.rank - b.rank)
    .map((item) => hypothesisCard(item, catalog, selectedLotDisplay));
  const noConfident = report.no_actionable_recommendation || hypotheses.length === 0;
  const primary = report.loss_summary.primary_failure[0] ?? null;
  return {
    datasetId: payload.dataset_id,
    selectedLotId,
    selectedLotDisplay,
    findingsTitle: selectedLotDisplay ? `Investigation Findings — ${selectedLotDisplay}` : "Investigation Findings",
    opportunityTitle: selectedLotDisplay ? `Yield Opportunity — ${selectedLotDisplay}` : "Yield Opportunity",
    generatedAt: payload.generated_at,
    analysisStatus: analysisStatus(payload),
    kpis: {
      fpy: formatRate(report.fpy_summary.fpy),
      fpyLoss: formatRate(report.fpy_summary.fpy_loss),
      eligibleDies: formatCount(report.fpy_summary.eligible_die_count),
      firstPassPass: formatCount(report.fpy_summary.first_pass_pass_count),
      firstPassFail: formatCount(report.fpy_summary.first_pass_fail_count),
    },
    leadingCandidate: noConfident ? null : (hypotheses[0] ?? null),
    noConfidentHypothesis: noConfident,
    noSignalHeadline: noConfident ? NO_SIGNAL : null,
    noActionableNotice: report.no_actionable_notice
      ? replaceTestIdsInText(report.no_actionable_notice, catalog)
      : report.no_actionable_notice,
    primaryFailureLabel: primary ? formatTestLabel(primary.failure_key, catalog) : null,
    pareto: report.loss_summary.primary_failure.map((row) => paretoRow(row, catalog)),
    primaryUnavailableNote: report.loss_summary.primary_unavailable_note
      ? replaceTestIdsInText(report.loss_summary.primary_unavailable_note, catalog)
      : report.loss_summary.primary_unavailable_note,
    evidence: report.evidence_findings.map(evidenceRow),
    hypotheses,
    investigationSteps: hypotheses.map((card) => `${card.title}: ${card.nextStep}`),
    investigationItems: report.investigation_plan,
    opportunity: {
      fpy: formatRate(report.fpy_summary.fpy),
      fpyLoss: formatRate(report.fpy_summary.fpy_loss),
      rows: report.opportunities.filter((row) => row.family !== "UNION").map(opportunityRow),
      overlapNote:
        "These opportunities may overlap and must not be added together. They are investigation estimates, not guaranteed yield recovery.",
    },
    dataQuality: {
      state: dataQualityState(
        report.data_gaps.required,
        report.data_gaps.recommended,
        report.data_gaps.detector_specific,
      ),
      required: labeledStrings(report.data_gaps.required, catalog),
      recommended: labeledStrings(report.data_gaps.recommended, catalog),
      detectorSpecific: labeledStrings(report.data_gaps.detector_specific, catalog),
    },
    notices: {
      nearLimit: report.near_limit_notice
        ? replaceTestIdsInText(`${NEAR_LIMIT_HEADLINE} ${report.near_limit_notice}`, catalog)
        : null,
      sequenceCensoring: report.sequence_censoring_notice
        ? replaceTestIdsInText(report.sequence_censoring_notice, catalog)
        : report.sequence_censoring_notice,
    },
    safety: {
      productionAction: "FORBIDDEN",
      productionAuthorized: "NO",
      safetyEligible: "0",
      statement: payload.safety_statement,
    },
    testCatalog: catalog ?? [],
    recommendations: payload.recommendations ?? null,
  };
}


export const NO_SIGNAL_COPY = NO_SIGNAL;
export const NEAR_LIMIT_COPY = NEAR_LIMIT_HEADLINE;
