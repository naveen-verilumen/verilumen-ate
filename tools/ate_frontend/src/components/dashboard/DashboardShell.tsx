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
import { AICopilotDrawer } from "@/components/mcp/AICopilotDrawer";
import { MultiAgentTelemetryCockpit } from "@/components/dashboard/MultiAgentTelemetryCockpit";
import {
  Sparkles,
  Activity,
  Zap,
  Menu,
  X,
  LayoutDashboard,
  Clock,
  Sliders,
  RotateCcw,
  FileCode,
  TrendingUp,
  Search,
  Cpu,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useWaferRealtime } from "@/hooks/useWaferRealtime";
import { fetchWafer } from "@/services/api";
import { useOpsStore } from "@/stores/opsStore";

type TabType =
  | "overview"
  | "dtl"
  | "log_analyzer"
  | "shmoo"
  | "ra_advisor"
  | "retest"
  | "stil"
  | "test_time"
  | "yield";

// Strictly Alphabetical Order: DTL -> Log Analyzer -> M-BIST Shmoo -> RA Advisor -> Retest AI -> STIL Setup -> Vector Memory -> Yield Advisor
const AGENTS = [
  {
    id: "dtl" as const,
    name: "Dynamic Limits (DTL)",
    icon: Sliders,
  },
  {
    id: "log_analyzer" as const,
    name: "Log Analyzer",
    icon: Search,
  },
  {
    id: "shmoo" as const,
    name: "M-BIST Shmoo",
    icon: Activity,
  },
  {
    id: "ra_advisor" as const,
    name: "RA Advisor",
    icon: Cpu,
  },
  {
    id: "retest" as const,
    name: "Retest AI",
    icon: RotateCcw,
  },
  {
    id: "stil" as const,
    name: "STIL Setup",
    icon: FileCode,
  },
  {
    id: "test_time" as const,
    name: "Vector Memory",
    icon: Clock,
  },
  {
    id: "yield" as const,
    name: "Yield Advisor",
    icon: TrendingUp,
  },
];

export function DashboardShell() {
  const { summary, isLoading, isError, refetch } = useDashboardData();
  const selectedWaferId = useOpsStore((s) => s.waferId);
  const hydrateFromSummary = useOpsStore((s) => s.hydrateFromSummary);
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCockpitOpen, setIsCockpitOpen] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<{ tab: TabType | "cockpit" }>;
      if (custom.detail?.tab) {
        if (custom.detail.tab === "cockpit") {
          setIsCockpitOpen(true);
        } else {
          setActiveTab(custom.detail.tab);
        }
      }
    };
    window.addEventListener("switchSuiteTab", handler);
    return () => window.removeEventListener("switchSuiteTab", handler);
  }, []);

  useEffect(() => {
    const handleOpenCopilot = () => {
      setIsCockpitOpen(true);
    };
    window.addEventListener("openCopilot", handleOpenCopilot);
    return () => window.removeEventListener("openCopilot", handleOpenCopilot);
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
    setIsCockpitOpen(true);
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent("openCopilot", { detail: { query } }));
    }, 100);
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

      {/* ─────────────────────────────────────────────────────────────────────────────
          LEFT NAVIGATION SIDEBAR DRAWER (Click to open, choose agent)
          ───────────────────────────────────────────────────────────────────────────── */}
      {isSidebarOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setIsSidebarOpen(false)}
          />

          {/* Drawer Panel: Increased width & larger bar size, no port numbers, no subheadings */}
          <div className="relative flex flex-col w-84 sm:w-96 lg:w-[400px] h-full border-r border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] px-6 py-4 bg-[var(--panel-2,#08101a)]">
              <VerilumenBrand size="header" />
              <button
                onClick={() => setIsSidebarOpen(false)}
                className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                title="Close Navigation"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Navigation List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-5 custom-scrollbar">
              {/* SYSTEM OVERVIEW */}
              <div>
                <button
                  onClick={() => {
                    setActiveTab("overview");
                    setIsSidebarOpen(false);
                  }}
                  className={`flex items-center justify-between w-full rounded-xl px-4 py-3.5 text-left transition-all ${
                    activeTab === "overview"
                      ? "bg-[rgba(107,193,242,0.12)] border border-[rgba(107,193,242,0.3)] text-white shadow-sm"
                      : "text-slate-200 hover:bg-white/[0.04] hover:text-white border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <LayoutDashboard className="h-4 w-4 text-[var(--cyan,#6bc1f2)]" />
                    <span className="text-sm font-semibold">Overview</span>
                  </div>
                  {activeTab === "overview" && (
                    <span className="h-2 w-2 rounded-full bg-[var(--cyan,#6bc1f2)]" />
                  )}
                </button>
              </div>

              {/* AUTONOMOUS ATE AGENTS (Strictly Alphabetical, No Port Numbers, No Subheadings) */}
              <div>
                <div className="text-xs font-mono uppercase tracking-wider text-[var(--muted-2,#5a6a82)] mb-2.5 px-3">
                  Autonomous ATE Agents
                </div>
                <div className="space-y-1.5">
                  {AGENTS.map((item) => {
                    const isActive = activeTab === item.id;
                    const IconComponent = item.icon;
                    return (
                      <button
                        key={item.id}
                        onClick={() => {
                          setActiveTab(item.id);
                          setIsSidebarOpen(false);
                        }}
                        className={`flex items-center justify-between w-full rounded-xl px-4 py-3.5 text-left transition-all ${
                          isActive
                            ? "bg-[rgba(107,193,242,0.12)] border border-[rgba(107,193,242,0.3)] text-white shadow-sm"
                            : "text-slate-200 hover:bg-white/[0.04] hover:text-white border border-transparent"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <IconComponent className="h-4 w-4 text-slate-400" />
                          <span className="text-sm font-semibold">{item.name}</span>
                        </div>
                        {isActive && (
                          <span className="h-2 w-2 rounded-full bg-[var(--cyan,#6bc1f2)]" />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="border-t border-[var(--line,#1a2433)] p-4 bg-[var(--panel-2,#08101a)]">
              <button
                onClick={() => {
                  setIsSidebarOpen(false);
                  setIsCockpitOpen(true);
                }}
                className="flex items-center justify-center gap-2 w-full rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] py-2.5 text-sm font-semibold text-white hover:bg-white/[0.09] transition-colors"
              >
                <Sparkles className="h-4 w-4 text-cyan-300" />
                <span>Launch AI Copilot</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          MAIN HEADER
          ───────────────────────────────────────────────────────────────────────────── */}
      <header className="vl-header vl-section-enter relative z-30 mb-[20px] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5 flex-wrap">
          {/* Menu button to open the left agent navigation drawer - "Overview" word removed */}
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="flex items-center gap-2 rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] px-3.5 py-2 text-sm font-semibold text-slate-200 hover:text-white hover:border-[var(--line-bright,#2c3a50)] hover:bg-white/[0.04] transition-all"
            title="Open Agent Navigation"
          >
            <Menu className="h-4 w-4 text-[var(--cyan,#6bc1f2)]" />
            <span>Agents</span>
          </button>

          <VerilumenBrand size="header" />
          <span className="rounded bg-sky-950/70 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-400 border border-sky-800/40">
            v1.1.1
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-4">
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

      {/* ─────────────────────────────────────────────────────────────────────────────
          ACTIVE CONTENT AREA: OVERVIEW OR EMBEDDED AGENT
          ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "overview" ? (
        <>
          <div className="vl-section-enter vl-section-enter-delay-1 mb-3">
            <EnterpriseControls />
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
        <div className="vl-surface-deep relative flex flex-col overflow-hidden rounded-xl border border-[var(--line)] p-5 shadow-2xl">
          {/* Top Bar with Microservice Title & One-Click AI Action Buttons */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-3.5">
            <div className="flex items-center gap-3">
              <span className="text-base font-bold tracking-wide text-white">
                {activeTab === "dtl" && "Dynamic Test Limits (DTL) Recommendation Engine"}
                {activeTab === "log_analyzer" && "Log Analyzer (Adaptive Scan Pattern Recommendation Agent)"}
                {activeTab === "shmoo" && "M-BIST Shmoo Margin Optimization Engine"}
                {activeTab === "ra_advisor" && "RA Advisor — Memory Built-in Self-Repair (BISR / BIRA)"}
                {activeTab === "retest" && "AI Retest-Benefit Prediction Intelligence"}
                {activeTab === "stil" && "STIL Test Setup & CUDA GBC Optimization Dashboard"}
                {activeTab === "test_time" && "Vector Memory & Test Time Optimization (LSTM Compressor)"}
                {activeTab === "yield" && "Yield Improvement Advisor (FPY & Pareto Recovery Engine)"}
              </span>
              <span className="rounded bg-[var(--green-dim)] px-2.5 py-0.5 text-xs font-bold text-[var(--green)]">
                ONLINE INSTANCE
              </span>
            </div>

            {/* ONE-CLICK AI ACTIONS */}
            <div className="flex items-center gap-2 flex-wrap">
              {activeTab === "dtl" && (
                <button
                  onClick={() => triggerCopilot("Explain recommended tight/relax test limits and Cpk capability")}
                  className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                >
                  <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                  Explain DTL Guardbands
                </button>
              )}

              {activeTab === "log_analyzer" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Audit scan pattern failure probabilities and adaptive log analyzer rankings")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-sky-300" />
                    Audit Pattern Priorities
                  </button>
                  <button
                    onClick={() => triggerCopilot("Summarize top failing scan patterns across wafer lots in Log Analyzer")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Activity className="h-3.5 w-3.5 text-sky-400" />
                    Lot Pattern Breakdown
                  </button>
                </>
              )}

              {activeTab === "shmoo" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Explain the current Shmoo failure pattern, voltage boundary, and recommended Vdd/Freq")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-purple-300" />
                    Ask Copilot to Explain Pattern
                  </button>
                  <button
                    onClick={() => triggerCopilot("Show SPC Cpk statistical guardbands and process capability for this Shmoo run")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Activity className="h-3.5 w-3.5 text-cyan-400" />
                    Cpk Guardbands
                  </button>
                </>
              )}

              {activeTab === "ra_advisor" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Explain RA Advisor repair strategy for the current fail bitmap")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
                    Explain Repair Strategy
                  </button>
                  <button
                    onClick={() => triggerCopilot("Check spare budget feasibility and row/column allocation")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Zap className="h-3.5 w-3.5 text-emerald-400" />
                    Spare Feasibility
                  </button>
                </>
              )}

              {activeTab === "retest" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Why did Retest recommend SKIP? Show feature attribution for failure event")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-emerald-300" />
                    Generate Root-Cause Summary
                  </button>
                  <button
                    onClick={() => triggerCopilot("Calculate annualized tester cost savings from SKIP recommendations")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Zap className="h-3.5 w-3.5 text-amber-400" />
                    Batch Cost Impact
                  </button>
                </>
              )}

              {activeTab === "stil" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Optimize STIL timing setup and minimize clock skew with CUDA GBC")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-indigo-300" />
                    Optimize STIL Timing
                  </button>
                  <button
                    onClick={() => triggerCopilot("Analyze STIL test setup signals, clocks, and waveform tables")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Activity className="h-3.5 w-3.5 text-indigo-400" />
                    Clocks & Signals
                  </button>
                </>
              )}

              {activeTab === "test_time" && (
                <button
                  onClick={() => triggerCopilot("Summarize STIL scan vector compression ratio and time savings")}
                  className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                >
                  <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
                  Summarize Vector Compression
                </button>
              )}

              {activeTab === "yield" && (
                <>
                  <button
                    onClick={() => triggerCopilot("Audit First Pass Yield and failure bin Pareto distribution")}
                    className="flex items-center gap-1.5 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] transition-colors"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-rose-300" />
                    Audit FPY & Pareto
                  </button>
                  <button
                    onClick={() => triggerCopilot("Show Yield Advisor recommendations and failing dies")}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700/80 transition-all"
                  >
                    <Zap className="h-3.5 w-3.5 text-rose-400" />
                    Yield Actions
                  </button>
                </>
              )}

              <button
                onClick={() => setActiveTab("overview")}
                className="rounded-lg border border-[var(--line)] bg-[rgba(255,255,255,0.06)] px-3.5 py-1.5 text-xs font-semibold text-[var(--cyan)] transition-colors hover:bg-[rgba(107,193,242,0.15)] ml-2"
              >
                ← Overview
              </button>
            </div>
          </div>

          <iframe
            src={
              activeTab === "dtl"
                ? "http://127.0.0.1:5174/three-month"
                : activeTab === "log_analyzer"
                ? "http://127.0.0.1:5177"
                : activeTab === "shmoo"
                ? "http://127.0.0.1:5000"
                : activeTab === "ra_advisor"
                ? "http://127.0.0.1:8005"
                : activeTab === "retest"
                ? "http://127.0.0.1:5175"
                : activeTab === "stil"
                ? "http://127.0.0.1:8765"
                : activeTab === "test_time"
                ? "http://127.0.0.1:8787"
                : activeTab === "yield"
                ? "http://127.0.0.1:5176"
                : "http://127.0.0.1:5000"
            }
            className="h-[calc(100vh-220px)] min-h-[640px] w-full rounded-lg border-0 bg-transparent"
            title="Embedded Suite Microservice"
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          AI COPILOT POPUP MODAL (Popped up when clicking AI Copilot button at bottom)
          ───────────────────────────────────────────────────────────────────────────── */}
      {isCockpitOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-xs transition-opacity"
            onClick={() => setIsCockpitOpen(false)}
          />

          {/* Modal Container */}
          <div className="relative flex flex-col w-full max-w-[1520px] h-[92vh] rounded-2xl border border-[var(--line,#1a2433)] bg-[var(--bg,#05080e)] shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] px-6 py-4 bg-[var(--panel,#0c121b)] shrink-0">
              <div>
                <h3 className="text-base font-bold text-white tracking-wide">
                  Verilumen ATE Multi-Agent Telemetry & AI Copilot
                </h3>
              </div>

              <button
                onClick={() => setIsCockpitOpen(false)}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] px-3.5 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:border-slate-600 transition-colors"
              >
                <X className="h-4 w-4" />
                <span>Close AI Copilot</span>
              </button>
            </div>

            {/* Modal Content: 60/40 Split */}
            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar">
              <div className="flex flex-col lg:flex-row gap-5 items-stretch min-h-full">
                {/* Left Pane (60%): Interactive Multi-Agent Telemetry */}
                <div className="w-full lg:w-[60%] flex flex-col space-y-4">
                  <MultiAgentTelemetryCockpit
                    activeWaferId={wafer?.wafer_id ?? "WFR-9082"}
                    onInvestigate={triggerCopilot}
                  />
                </div>

                {/* Right Pane (40%): Docked Verilumen ATE Copilot */}
                <div className="w-full lg:w-[40%] flex flex-col min-h-[600px] lg:sticky lg:top-0">
                  <AICopilotDrawer mode="docked" onClose={() => setIsCockpitOpen(false)} />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          FLOATING AI COPILOT BUTTON AT THE BOTTOM (Clean, Professional)
          ───────────────────────────────────────────────────────────────────────────── */}
      {!isCockpitOpen && (
        <button
          onClick={() => setIsCockpitOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full border border-[var(--line-bright,#2c3a50)] bg-[var(--panel,#0c121b)] px-4 py-2.5 text-sm font-semibold text-white shadow-xl backdrop-blur-md transition-all hover:bg-[var(--panel-2,#08101a)] hover:border-slate-500 group"
          title="Open Verilumen AI Copilot"
        >
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/25">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <span className="tracking-wide">AI Copilot</span>
        </button>
      )}

      <footer className="mt-8 flex flex-wrap justify-between gap-2 border-t border-[rgba(107,193,242,0.18)] pt-4 text-xs text-[#7f96b0] vl-section-enter vl-section-enter-delay-5">
        <span>
          Verilumen - ATE v1.1.1 · Connected via FastMCP
        </span>
        <span className="font-mono text-xs tracking-wide text-[#9ec9ef]">
          {summary?.connection_hint ?? "Live telemetry synchronized across autonomous agents"}
        </span>
      </footer>
    </div>
  );
}
