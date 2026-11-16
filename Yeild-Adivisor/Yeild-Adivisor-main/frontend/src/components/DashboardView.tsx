import type { DashboardViewModel } from "../services/yieldImprovementViewModel";
import { HypothesisCards } from "./HypothesisCards";
import { InvestigationPlan } from "./InvestigationPlan";
import { KpiSummary } from "./KpiSummary";
import { OpportunitySection } from "./OpportunitySection";
import { ParetoChart } from "./ParetoChart";
import { RankedRecommendations } from "./RankedRecommendations";
import { TestReference } from "./TestReference";
import { WaferMap } from "./WaferMap";
import { ParametricAnalysisSection } from "./ParametricAnalysisSection";
import type { WaferMapResponse, ParametricAnalysisReport } from "../types/api";

interface Props {
  model: DashboardViewModel;
  waferMap?: WaferMapResponse | null;
  selectedLotId?: string | null;
  parametricAnalysis?: ParametricAnalysisReport | null;
  parametricLoading?: boolean;
  parametricError?: string | null;
}

export function DashboardView({
  model,
  waferMap,
  selectedLotId,
  parametricAnalysis,
  parametricLoading,
  parametricError,
}: Props) {
  const activeLotId =
    selectedLotId !== undefined
      ? selectedLotId?.trim() || null
      : model.selectedLotId?.trim() || null;

  return (
    <div className="space-y-4">
      <KpiSummary fpy={model.kpis.fpy} fpyLoss={model.kpis.fpyLoss} eligibleDies={model.kpis.eligibleDies} />
      <ParetoChart rows={model.pareto} unavailableNote={model.primaryUnavailableNote} />
      <WaferMap
        data={waferMap}
        catalog={model.testCatalog}
        selectedLotId={activeLotId}
      />
      {activeLotId ? (
        <RankedRecommendations
          bundle={model.recommendations}
          datasetId={model.datasetId}
          selectedLotId={activeLotId}
        />
      ) : null}
      <ParametricAnalysisSection
        report={parametricAnalysis}
        loading={parametricLoading}
        error={parametricError}
        selectedLotId={activeLotId}
      />
      <HypothesisCards cards={model.hypotheses} title={model.findingsTitle} />
      <InvestigationPlan steps={model.investigationSteps} noConfidentHypothesis={model.noConfidentHypothesis} />
      <OpportunitySection opportunity={model.opportunity} title={model.opportunityTitle} />
      <TestReference catalog={model.testCatalog} />
    </div>
  );
}

