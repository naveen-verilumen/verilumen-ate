import type {
  DashboardResponse,
  DatasetListResponse,
  EngineeringRecommendation,
  FeedbackCreateRequest,
  FeedbackHistoryResponse,
  FeedbackRecord,
  HealthSnapshot,
  MlSnapshot,
  RecommendationBundle,
  WaferMapResponse,
  ParametricAnalysisReport,
  RecommendationFailingDiesResponse,
} from "../types/api";


async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // keep status text
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function fetchDatasets(): Promise<DatasetListResponse> {
  const response = await fetch("/api/datasets");
  return parseJson<DatasetListResponse>(response);
}

export async function fetchDashboard(
  datasetId: string,
  options: { refresh?: boolean; lotId?: string | null } = {},
): Promise<DashboardResponse> {
  const params = new URLSearchParams();
  if (options.refresh) {
    params.set("refresh", "true");
  }
  if (options.lotId) {
    params.set("lot_id", options.lotId);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/dashboard${query}`);
  return parseJson<DashboardResponse>(response);
}

export async function fetchWaferMap(datasetId: string): Promise<WaferMapResponse> {
  const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/wafer-map`);
  return parseJson<WaferMapResponse>(response);
}

export async function fetchActiveMl(): Promise<MlSnapshot> {
  const response = await fetch("/api/ml/active");
  return parseJson<MlSnapshot>(response);
}

export async function fetchHealth(datasetId: string): Promise<HealthSnapshot> {
  const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/health`);
  return parseJson<HealthSnapshot>(response);
}

export async function fetchRecommendations(
  datasetId: string,
  lotId?: string | null,
): Promise<RecommendationBundle> {
  const query = lotId ? `?lot_id=${encodeURIComponent(lotId)}` : "";
  const response = await fetch(`/api/datasets/${encodeURIComponent(datasetId)}/recommendations${query}`);
  return parseJson<RecommendationBundle>(response);
}

export async function fetchRecommendationDetail(
  datasetId: string,
  recommendationId: string,
): Promise<EngineeringRecommendation> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/recommendations/${encodeURIComponent(recommendationId)}`,
  );
  return parseJson<EngineeringRecommendation>(response);
}

export async function submitRecommendationFeedback(
  datasetId: string,
  recommendationId: string,
  payload: FeedbackCreateRequest,
): Promise<FeedbackRecord> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/recommendations/${encodeURIComponent(recommendationId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseJson<FeedbackRecord>(response);
}

export async function fetchFeedbackHistory(
  datasetId: string,
  recommendationId: string,
): Promise<FeedbackHistoryResponse> {
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/recommendations/${encodeURIComponent(recommendationId)}/feedback`,
  );
  return parseJson<FeedbackHistoryResponse>(response);
}

export async function fetchParametricAnalysis(
  datasetId: string,
  lotId?: string | null,
): Promise<ParametricAnalysisReport> {
  const query = lotId ? `?lot_id=${encodeURIComponent(lotId)}` : "";
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/parametric-analysis${query}`,
  );
  return parseJson<ParametricAnalysisReport>(response);
}

export async function fetchRecommendationFailingDies(
  datasetId: string,
  recommendationId: string,
  lotId?: string | null,
): Promise<RecommendationFailingDiesResponse> {
  const query = lotId ? `?lot_id=${encodeURIComponent(lotId)}` : "";
  const response = await fetch(
    `/api/datasets/${encodeURIComponent(datasetId)}/recommendations/${encodeURIComponent(recommendationId)}/failing-dies${query}`,
  );
  return parseJson<RecommendationFailingDiesResponse>(response);
}


