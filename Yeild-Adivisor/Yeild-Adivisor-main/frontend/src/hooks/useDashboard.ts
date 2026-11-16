import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchDashboard,
  fetchDatasets,
  fetchParametricAnalysis,
  fetchWaferMap,
} from "../services/yieldImprovementApi";
import type {
  DashboardResponse,
  DatasetListItem,
  DatasetLot,
  ParametricAnalysisReport,
  WaferMapResponse,
} from "../types/api";

interface State {
  datasets: DatasetListItem[];
  selectedId: string;
  selectedLotId: string;
  lots: DatasetLot[];
  payload: DashboardResponse | null;
  waferMap: WaferMapResponse | null;
  parametricAnalysis: ParametricAnalysisReport | null;
  parametricLoading: boolean;
  parametricError: string | null;
  loading: boolean;
  error: string | null;
}

const initial: State = {
  datasets: [],
  selectedId: "",
  selectedLotId: "",
  lots: [],
  payload: null,
  waferMap: null,
  parametricAnalysis: null,
  parametricLoading: true,
  parametricError: null,
  loading: true,
  error: null,
};

export function useDashboard() {
  const [state, setState] = useState<State>(initial);
  const stateRef = useRef<State>(state);
  stateRef.current = state;

  const requestIdRef = useRef(0);

  const load = useCallback(async (datasetId?: string, lotId?: string, refresh = false) => {
    const currentRequestId = ++requestIdRef.current;

    setState((prev) => ({
      ...prev,
      loading: true,
      error: null,
      parametricLoading: true,
      parametricError: null,
    }));

    try {
      // Optimization D1: Reuse existing datasets list if valid and not refreshing
      let datasets = stateRef.current.datasets;
      const needDatasets =
        refresh ||
        datasets.length === 0 ||
        (datasetId !== undefined && !datasets.some((item) => item.dataset_id === datasetId));

      if (needDatasets) {
        const listed = await fetchDatasets();
        if (currentRequestId !== requestIdRef.current) return;
        datasets = listed.datasets;
      }

      if (datasets.length === 0) {
        if (currentRequestId !== requestIdRef.current) return;
        setState({
          datasets: [],
          selectedId: "",
          selectedLotId: "",
          lots: [],
          payload: null,
          waferMap: null,
          parametricAnalysis: null,
          parametricLoading: false,
          parametricError: null,
          loading: false,
          error: null,
        });
        return;
      }

      const preferred =
        datasetId && datasets.some((item) => item.dataset_id === datasetId)
          ? datasetId
          : datasets.some((item) => item.dataset_id === "yi_synthetic_v2")
            ? "yi_synthetic_v2"
            : datasets[0].dataset_id;
      const selected = datasets.find((item) => item.dataset_id === preferred) ?? datasets[0];
      const lots = selected.lots ?? [];
      const preferredLot = lotId && lots.some((item) => item.lot_id === lotId) ? lotId : "";

      // Optimization D2: Reuse existing waferMap if valid for current dataset and not refreshing
      const prevWaferMap = stateRef.current.waferMap;
      const prevDatasetId = stateRef.current.selectedId;
      const needWaferMap = refresh || !prevWaferMap || prevDatasetId !== preferred;

      const waferMapPromise: Promise<WaferMapResponse | null> = needWaferMap
        ? fetchWaferMap(preferred).catch(() => null)
        : Promise.resolve(prevWaferMap);

      // Optimization D3: Fetch dashboard and parametric analysis concurrently with Promise.all
      const [payload, parametricResult, waferMap] = await Promise.all([
        fetchDashboard(preferred, { refresh, lotId: preferredLot || null }),
        fetchParametricAnalysis(preferred, preferredLot || null).then(
          (data) => ({ data, error: null as string | null }),
          (err) => ({
            data: null as ParametricAnalysisReport | null,
            error: err instanceof Error ? err.message : "Parametric analysis unavailable",
          })
        ),
        waferMapPromise,
      ]);

      // Optimization D4: Stale-response protection — do not apply if a newer request was made
      if (currentRequestId !== requestIdRef.current) return;

      setState({
        datasets,
        selectedId: preferred,
        selectedLotId: preferredLot,
        lots: payload.lots?.length ? payload.lots : lots,
        payload,
        waferMap,
        parametricAnalysis: parametricResult.data,
        parametricLoading: false,
        parametricError: parametricResult.error,
        loading: false,
        error: null,
      });
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      const message = err instanceof Error ? err.message : "API unavailable";
      setState((prev) => ({
        ...prev,
        loading: false,
        error: message,
        payload: null,
        waferMap: null,
        parametricAnalysis: null,
        parametricLoading: false,
        parametricError: null,
      }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    ...state,
    selectDataset: (datasetId: string) => {
      void load(datasetId, "");
    },
    selectLot: (lotId: string) => {
      void load(stateRef.current.selectedId || undefined, lotId);
    },
    refreshAnalysis: () => {
      void load(stateRef.current.selectedId || undefined, stateRef.current.selectedLotId || undefined, true);
    },
    retry: () => {
      void load(stateRef.current.selectedId || undefined, stateRef.current.selectedLotId || undefined);
    },
  };
}
