"use client";

import React, { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { MCPToolExplorerModal, MCPTool } from "./MCPToolExplorerModal";

const DEFAULT_TOOLS: MCPTool[] = [
  // Shmoo ML (3 tools)
  { name: "shmoo_health", agent: "Shmoo ML", description: "Check if Shmoo ML service is running and healthy", args: [] },
  { name: "shmoo_load_demo", agent: "Shmoo ML", description: "Load demo Shmoo dataset & run ML boundary extraction (RANSAC, SPC, ROI)", args: [] },
  { name: "shmoo_generate_report", agent: "Shmoo ML", description: "Generate comprehensive PDF report for Shmoo analysis", args: ["session_id", "text_mode", "test_methodology"] },
  // Vector Memory (3 tools)
  { name: "test_time_health", agent: "Vector Memory", description: "Check if Test Time Optimizer is online", args: [] },
  { name: "test_time_run_demo", agent: "Vector Memory", description: "Run LSTM compression on STIL vectors and calculate time savings", args: [] },
  { name: "test_time_analyze_fail_logs", agent: "Vector Memory", description: "Analyze ATE log files to detect fail patterns across cycles", args: ["log_summary"] },
  // Dynamic Limits (5 tools)
  { name: "dtl_health", agent: "Dynamic Limits", description: "Check readiness of the DTL recommendation engine", args: [] },
  { name: "dtl_get_selectors", agent: "Dynamic Limits", description: "Retrieve available lots, wafers, and die selections", args: [] },
  { name: "dtl_get_measurements", agent: "Dynamic Limits", description: "Fetch measurement distributions and Cpk stats for parameters", args: ["lot_id", "die_id", "test_parameter"] },
  { name: "dtl_get_recommendations", agent: "Dynamic Limits", description: "AI-recommended tight/relax limit guardbands for Cpk optimization", args: ["lot_id", "die_id"] },
  { name: "dtl_run_three_month_analysis", agent: "Dynamic Limits", description: "Run temporal 3-month model analysis on historical lots", args: [] },
  // Retest AI (7 tools)
  { name: "retest_health", agent: "Retest AI", description: "Check if Retest-Benefit Prediction service is online", args: [] },
  { name: "retest_model_info", agent: "Retest AI", description: "Inspect XGBoost model version, feature whitelist, and AUC", args: [] },
  { name: "retest_predict_single", agent: "Retest AI", description: "Predict P(RETEST_BENEFICIAL) -> RETEST or SKIP recommendation", args: ["failure_event", "device_id", "fail_test", "voltage_v", "temperature_c"] },
  { name: "retest_predict_with_explanation", agent: "Retest AI", description: "Predict retest decision with SHAP explainability values", args: ["failure_event", "device_id", "fail_test", "voltage_v", "temperature_c"] },
  { name: "retest_get_historical_analysis", agent: "Retest AI", description: "Batch analysis for Month-12 dataset with financial cost savings", args: ["cost_per_hour"] },
  { name: "retest_get_available_devices", agent: "Retest AI", description: "List devices and events in the Retest AI dataset", args: [] },
  { name: "retest_get_online_learning_status", agent: "Retest AI", description: "Check continuous online learning model status", args: [] },
  // STIL Setup & Optimization (5 tools)
  { name: "stil_health", agent: "STIL Setup", description: "Check if STIL Test Setup & Optimization engine is online", args: [] },
  { name: "stil_list_files", agent: "STIL Setup", description: "List available STIL test vector and setup files", args: [] },
  { name: "stil_analyze", agent: "STIL Setup", description: "Parse STIL test setup, signals, clocks, and timing tables", args: ["filename"] },
  { name: "stil_optimize", agent: "STIL Setup", description: "Run CUDA GBC optimization on test setups", args: ["filenames"] },
  { name: "stil_explain_setup", agent: "STIL Setup", description: "AI explanation of test setup anomalies and clock skew", args: ["filenames"] },
  // Yield Advisor (6 tools)
  { name: "yield_advisor_health", agent: "Yield Advisor", description: "Check if Yield Improvement Advisor service is online", args: [] },
  { name: "yield_advisor_list_datasets", agent: "Yield Advisor", description: "List available wafer datasets for yield analysis", args: [] },
  { name: "yield_advisor_get_dashboard", agent: "Yield Advisor", description: "Get FPY, yield KPIs, and failure Pareto distribution", args: ["dataset_id"] },
  { name: "yield_advisor_get_recommendations", agent: "Yield Advisor", description: "AI recommendations to recover wafer yield", args: ["dataset_id"] },
  { name: "yield_advisor_get_failing_dies", agent: "Yield Advisor", description: "Extract wafer coordinates and signatures for failing dies", args: ["dataset_id", "recommendation_id"] },
  { name: "yield_advisor_wafer_map", agent: "Yield Advisor", description: "Spatial wafer map with bin breakdown", args: ["dataset_id"] },
  // Orchestrator (2 tools)
  { name: "suite_health_check", agent: "Orchestrator", description: "Check health of all 6 microservices simultaneously", args: [] },
  { name: "suite_full_wafer_analysis", agent: "Orchestrator", description: "Parallel multi-agent execution across all tools with merged summary", args: ["cost_per_hour"] },
];

interface MCPStatusBadgeProps {
  onOpenChatWithQuery?: (query: string) => void;
}

export function MCPStatusBadge({ onOpenChatWithQuery }: MCPStatusBadgeProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [tools, setTools] = useState<MCPTool[]>(DEFAULT_TOOLS);
  const [isOnline, setIsOnline] = useState(true);
  const [activeCount, setActiveCount] = useState(31);
  const [activeAgents, setActiveAgents] = useState(6);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/mcp/status");
        if (!res.ok) throw new Error("status error");
        const data = await res.json();
        if (mounted) {
          // Show green if backend is reachable (even if some services are offline)
          // "offline" status means services are down but backend is reachable
          setIsOnline(true);
          // Always show the registered tool count (31), not online service count
          setActiveCount(data.tools_count ?? 31);
          // Count total configured agents from services object
          const agentCount = data.total_services_count ?? Object.keys(data.services ?? {}).length ?? 6;
          setActiveAgents(agentCount);
          if (data.tools && data.tools.length > 0) {
            setTools(data.tools);
          }
        }
      } catch {
        // Backend itself is unreachable — show amber
        if (mounted) {
          setIsOnline(false);
          setActiveCount(31);
          setActiveAgents(6);
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className="group flex items-center gap-2 rounded-lg border border-[var(--line,#1e293b)] bg-[rgba(10,18,30,0.85)] px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 transition-all hover:border-cyan-500/40 hover:bg-[rgba(15,26,44,0.95)] hover:shadow-[0_0_12px_rgba(6,182,212,0.15)]"
        title={`Click to view all ${activeCount} registered MCP tools across ${activeAgents} AI agents`}
      >
        <span className="relative flex h-2 w-2">
          {isOnline && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              isOnline ? "bg-emerald-500 shadow-[0_0_6px_#10b981]" : "bg-amber-500"
            }`}
          />
        </span>
        <span className="font-mono text-cyan-300">MCP</span>
        <span className="hidden sm:inline text-slate-300">
          {isOnline
            ? `${activeAgents} Agents · ${activeCount} Tools`
            : "Connecting..."}
        </span>
        <ChevronRight className="h-3 w-3 text-slate-500 group-hover:text-cyan-300 transition-colors" />
      </button>

      <MCPToolExplorerModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        tools={tools}
        onSelectToolForChat={(toolName) => {
          if (onOpenChatWithQuery) {
            onOpenChatWithQuery(`Run tool ${toolName}() and summarize its findings`);
          }
        }}
      />
    </>
  );
}
