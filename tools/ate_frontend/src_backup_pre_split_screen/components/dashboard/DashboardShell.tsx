"use client";

import { useEffect, useState } from "react";
import { DisconnectedBanner } from "@/components/common/DisconnectedBanner";
import { ErrorState } from "@/components/common/ErrorState";
import { LiveStatusIndicator } from "@/components/common/LiveStatusIndicator";
import { LoadingState } from "@/components/common/LoadingState";
import { VerilumenBrand } from "@/components/branding/VerilumenBrand";
import { SessionControl } from "@/components/auth/SessionControl";
import { EnterpriseControls } from "@/components/dashboard/EnterpriseControls";
import { TestFloorEventLog } from "@/components/events/TestFloorEventLog";
import { HeaderStats } from "@/components/kpi/HeaderStats";
import { OptimizationKpiGrid } from "@/components/kpi/OptimizationKpiGrid";
import { DynamicTestLimits } from "@/components/limits/DynamicTestLimits";
import { PredictiveMaintenanceCard } from "@/components/maintenance/PredictiveMaintenanceCard";
import { UploadControl } from "@/components/uploads/UploadControl";
import { WaferMap } from "@/components/wafer/WaferMap";
import { YieldSummary } from "@/components/wafer/YieldSummary";
import { MCPStatusBadge } from "@/components/mcp/MCPStatusBadge";
import { AICopilotDrawer } from "@/components/mcp/AICopilotDrawer";
import { Sparkles, Activity, Zap } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useWaferRealtime } from "@/hooks/useWaferRealtime";
import { fetchWafer } from "@/services/api";
import { useOpsStore } from "@/stores/opsStore";

export function DashboardShell() {
  const { summary, isLoading, isError, refetch } = useDashboardData();
  const selectedWaferId = useOpsStore((s) => s.waferId);
  const hydrateFromSummary = useOpsStore((s) => s.hydrateFromSummary);
  const [activeTab, setActiveTab] = useState<"overview" | "shmoo" | "test_time" | "dtl" | "retest" | "stil" | "yield">("overview");

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<{ tab: "overview" | "shmoo" | "test_time" | "dtl" | "retest" | "stil" | "yield" }>;
      if (custom.detail?.tab) setActiveTab(custom.detail.tab);
    };
    window.addEventListener("switchSuiteTab", handler);
    return () => window.removeEventListener("switchSuiteTab", handler);
  }, []);

  useEffect(() => {
    if (!summary?.active_wafer) return;
    hydrateFromSummary({
      lotId: summary.active_wafer.lot_id,
      waferId: summary.active_wafer.wafer_id,
      testerId: null,
      siteId: null,
    });
  }, [summary, hydrateFromSummary]);

  const waferId = selectedWaferId || summary?.active_wafer?.wafer_id || null;
  useWaferRealtime(waferId, true);

  const waferQuery = useQuery({
    queryKey: ["wafer", waferId, "detail"],
    queryFn: () => fetchWafer(waferId!),
    enabled: Boolean(waferId),
    staleTime: 8_000,
  });

  const triggerCopilot = (query: string) => {
    window.dispatchEvent(new CustomEvent("openCopilot", { detail: { query } }));
  };

  if (isLoading && !summary) {
    return (
      <div className="mx-auto max-w-[1400px] px-7 pb-[90px] pt-[30px]">
        <LoadingState />
      </div>
    );
  }

  if (isError && !summary) {
    return (
      <div className="mx-auto max-w-[1400px] px-7 pb-[90px] pt-[30px]">
        <ErrorState
          message="Unable to load dashboard summary from the API."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  const wafer = waferQuery.data ?? summary?.active_wafer ?? null;

  return (
    <div className="mx-auto max-w-[1440px] px-7 pb-[90px] pt-[24px]">
      <DisconnectedBanner />

      <header className="vl-header vl-section-enter relative z-50 mb-[20px] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-wrap">
          <VerilumenBrand size="header" />
          <nav className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[rgba(10,18,30,0.85)] p-1 shadow-inner backdrop-blur-md">
            <button
              onClick={() => setActiveTab("overview")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "overview"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              🌐 Overview
            </button>
            <button
              onClick={() => setActiveTab("shmoo")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "shmoo"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              ⚡ M-BIST Shmoo
            </button>
            <button
              onClick={() => setActiveTab("test_time")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "test_time"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              ⏱️ Vector Memory
            </button>
            <button
              onClick={() => setActiveTab("dtl")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "dtl"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              📊 Dynamic Limits (DTL)
            </button>
            <button
              onClick={() => setActiveTab("retest")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "retest"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              🎯 Retest AI
            </button>
            <button
              onClick={() => setActiveTab("stil")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "stil"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              📑 STIL Setup
            </button>
            <button
              onClick={() => setActiveTab("yield")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-semibold transition-all ${
                activeTab === "yield"
                  ? "bg-[rgba(107,193,242,0.18)] text-[var(--cyan)] shadow-[0_0_12px_rgba(107,193,242,0.25)] border border-[rgba(107,193,242,0.35)]"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              📈 Yield Advisor
            </button>
          </nav>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Live MCP Status Badge */}
          <MCPStatusBadge onOpenChatWithQuery={triggerCopilot} />

          <HeaderStats data={summary?.header ?? null} />
          <div className="flex items-center gap-3 border-l border-[var(--line)] pl-3">
            <UploadControl />
            <div className="text-right">
              <div className="vl-label mb-0.5">Live Connection</div>
              <LiveStatusIndicator />
            </div>
            <SessionControl />
          </div>
        </div>
      </header>

      {activeTab === "overview" ? (
        <>
          <div className="vl-section-enter vl-section-enter-delay-1 flex items-center justify-between gap-4 mb-3">
            <div className="flex-1">
              <EnterpriseControls />
            </div>
            <button
              onClick={() => triggerCopilot("Audit current wafer across all models and summarize the findings")}
              className="hidden lg:flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-[rgba(6,182,212,0.1)] px-4 py-2.5 text-xs font-bold text-cyan-300 shadow-[0_0_20px_rgba(6,182,212,0.15)] hover:bg-[rgba(6,182,212,0.2)] hover:border-cyan-500/50 transition-all shrink-0"
            >
              <Sparkles className="h-4 w-4 text-cyan-300" />
              <span>Audit Wafer with AI Copilot</span>
            </button>
          </div>

          <section
            id="live-wafer-map"
            className="vl-surface-deep vl-section-enter vl-section-enter-delay-2 mb-[30px] grid grid-cols-1 gap-[26px] p-6 md:grid-cols-[340px_1fr]"
          >
            <WaferMap waferId={wafer?.wafer_id ?? null} />
            <YieldSummary wafer={wafer} />
          </section>

          <div id="optimization-parameters" className="vl-section-title mb-3 scroll-mt-6 vl-section-enter vl-section-enter-delay-3">
            Optimization Parameters
          </div>
          <div className="vl-section-enter vl-section-enter-delay-3">
            <OptimizationKpiGrid>
              <PredictiveMaintenanceCard />
              <DynamicTestLimits data={summary?.test_limits ?? null} />
            </OptimizationKpiGrid>
          </div>

          <div className="mt-1 vl-section-enter vl-section-enter-delay-4">
            <TestFloorEventLog />
          </div>
        </>
      ) : (
        <div className="vl-surface-deep relative flex flex-col overflow-hidden rounded-xl border border-[var(--line)] p-4 shadow-2xl">
          {/* Top Bar with Microservice Title & One-Click AI Action Buttons */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-3">
            <div className="flex items-center gap-2.5">
              <span className="text-[14px] font-bold tracking-wide text-white">
                {activeTab === "shmoo" && "⚡ M-BIST Shmoo ML Optimization Engine (RANSAC, SPC & Active Learning)"}
                {activeTab === "test_time" && "⏱️ ATE Vector Memory & Test Time Optimization (LSTM Compressor)"}
                {activeTab === "dtl" && "📊 Dynamic Test Limits (DTL) Recommendation Engine"}
                {activeTab === "retest" && "🎯 AI Retest-Benefit Prediction Intelligence (XGBoost & SHAP)"}
                {activeTab === "stil" && "📑 STIL Test Setup & CUDA GBC Optimization Dashboard"}
                {activeTab === "yield" && "📈 Yield Improvement Advisor (FPY & Pareto Recovery Engine)"}
              </span>
              <span className="rounded bg-[var(--green-dim)] px-2 py-0.5 text-[10px] font-bold text-[var(--green)]">
                ONLINE INSTANCE
              </span>
            </div>

            {/* ONE-CLICK AI ACTIONS */}
            <div className="flex items-center gap-2 flex-wrap">
              {activeTab === "shmoo" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Explain the current Shmoo failure pattern, RANSAC boundary, and recommended Vdd/Freq")}
                    className="flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-950/40 px-3 py-1.5 text-xs font-semibold text-purple-200 hover:bg-purple-900/60 transition-all shadow-[0_0_10px_rgba(168,85,247,0.2)]"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-purple-300" />
                    Ask Copilot to Explain Pattern
                  </button>
                  <button
                    onClick={() => triggerCopilot("Show SPC Cpk statistical guardbands and process capability for this Shmoo run")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Activity className="h-3.5 w-3.5 text-cyan-400" />
                    Cpk Guardbands
                  </button>
                </>
              )}

              {activeTab === "retest" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Why did Retest recommend SKIP? Show SHAP attribution values for failure event")}
                    className="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-900/60 transition-all shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-emerald-300" />
                    Generate SHAP Root-Cause Summary
                  </button>
                  <button
                    onClick={() => triggerCopilot("Calculate annualized tester cost savings from SKIP recommendations")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Zap className="h-3.5 w-3.5 text-amber-400" />
                    Batch Cost Impact
                  </button>
                </>
              )}

              {activeTab === "test_time" && (
                <button
                  onClick={() => triggerCopilot("Summarize STIL scan vector compression ratio and time savings")}
                  className="flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/40 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-900/60 transition-all shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                >
                  <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
                  Summarize Vector Compression
                </button>
              )}

              {activeTab === "dtl" && (
                <button
                  onClick={() => triggerCopilot("Explain recommended tight/relax test limits and Cpk capability")}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-950/40 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-900/60 transition-all shadow-[0_0_10px_rgba(245,158,11,0.2)]"
                >
                  <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                  Explain DTL Guardbands
                </button>
              )}

              {activeTab === "stil" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Optimize STIL timing setup and minimize clock skew with CUDA GBC")}
                    className="flex items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-950/40 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/60 transition-all shadow-[0_0_10px_rgba(99,102,241,0.2)]"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
                    Optimize STIL Timing
                  </button>
                  <button
                    onClick={() => triggerCopilot("Analyze STIL test setup signals, clocks, and waveform tables")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Activity className="h-3.5 w-3.5 text-indigo-400" />
                    Clocks & Signals
                  </button>
                </>
              )}

              {activeTab === "yield" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Audit First Pass Yield and failure bin Pareto distribution")}
                    className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-950/40 px-3 py-1.5 text-xs font-semibold text-rose-200 hover:bg-rose-900/60 transition-all shadow-[0_0_10px_rgba(244,63,94,0.2)]"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-rose-300" />
                    Audit FPY & Pareto
                  </button>
                  <button
                    onClick={() => triggerCopilot("Show Yield Advisor recommendations and failing dies")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Zap className="h-3.5 w-3.5 text-rose-400" />
                    Yield Actions
                  </button>
                </>
              )}

              <button
                onClick={() => setActiveTab("overview")}
                className="rounded-md border border-[var(--line)] bg-[rgba(255,255,255,0.06)] px-3 py-1.5 text-[11.5px] font-semibold text-[var(--cyan)] transition-colors hover:bg-[rgba(107,193,242,0.15)] ml-2"
              >
                ← Overview
              </button>
            </div>
          </div>

          <iframe
            src={
              activeTab === "shmoo"
                ? "http://127.0.0.1:5000"
                : activeTab === "test_time"
                ? "http://127.0.0.1:8787"
                : activeTab === "dtl"
                ? "http://127.0.0.1:5174/three-month"
                : activeTab === "retest"
                ? "http://127.0.0.1:5175"
                : activeTab === "stil"
                ? "http://127.0.0.1:8765"
                : activeTab === "yield"
                ? "http://127.0.0.1:5176"
                : "http://127.0.0.1:5000"
            }
            className="h-[calc(100vh-220px)] min-h-[640px] w-full rounded-lg border-0 bg-transparent"
            title="Embedded Suite Microservice"
          />
        </div>
      )}

      {/* Floating AI Copilot Drawer */}
      <AICopilotDrawer />

      <footer className="mt-8 flex flex-wrap justify-between gap-2 border-t border-[rgba(107,193,242,0.18)] pt-4 text-[11px] text-[#7f96b0] vl-section-enter vl-section-enter-delay-5">
        <span>
          Verilumen Multi-Agent ATE Intelligence Suite · Connected via MCP
        </span>
        <span className="font-mono text-[10px] tracking-wide text-[#9ec9ef]">
          {summary?.connection_hint ?? "Live telemetry · 6 Autonomous AI Agents · FastMCP Stdio & HTTP Bridge"}
        </span>
      </footer>
    </div>
  );
}
