"use client";

import React, { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { MCPToolExplorerModal, MCPTool } from "./MCPToolExplorerModal";

const DEFAULT_TOOLS: MCPTool[] = [
  { name: "suite_health", agent: "Orchestrator", description: "Cached health probe across all 7 ATE microservices (supports refresh=true bypass)", args: ["refresh"], readOnlyHint: true },
  { name: "list_context", agent: "Orchestrator", description: "Discover available lots, wafers, dies, STIL files, Yield datasets, and scan catalogs", args: ["agent", "lot_id"], readOnlyHint: true },
  { name: "run_analysis", agent: "Multi-Agent", description: "Run bounded analysis on any ATE agent (shmoo, test_time, dtl, retest, stil, yield_advisor, log_analyzer)", args: ["agent", "params"], readOnlyHint: false },
  { name: "get_results", agent: "Multi-Agent", description: "Read latest structured telemetry, wafer map, failing dies, DTL measurements, or job results", args: ["agent", "view", "lot_id", "die_id", "wafer_id", "dataset_id", "run_id"], readOnlyHint: true },
  { name: "full_wafer_analysis", agent: "Orchestrator", description: "Parallel multi-agent wafer triangulation across all 7 engines updating wafer resources", args: ["wafer_id", "lot_id", "cost_per_hour"], readOnlyHint: false },
  { name: "explain_retest_decision", agent: "Retest AI", description: "Predict RETEST vs SKIP with feature attribution for a failed ATE die", args: ["fail_test", "voltage_v", "temperature_c", "fail_bin", "device_id"], readOnlyHint: true },
  { name: "generate_shmoo_report", agent: "Shmoo ML", description: "Generate PDF analysis report for a Shmoo characterization session", args: ["session_id", "text_mode", "test_methodology"], readOnlyHint: false },
  { name: "start_long_job", agent: "Long Jobs", description: "Launch non-blocking Yield ML retraining or STIL large-file parse returning run_id + progress notifications", args: ["job_type", "target"], readOnlyHint: false },
  { name: "get_job_status", agent: "Long Jobs", description: "Read progress percentage, phase logs, and structured result envelope for a run_id", args: ["run_id"], readOnlyHint: true },
];

interface MCPStatusBadgeProps {
  onOpenChatWithQuery?: (query: string) => void;
}

export function MCPStatusBadge({ onOpenChatWithQuery }: MCPStatusBadgeProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [tools, setTools] = useState<MCPTool[]>(DEFAULT_TOOLS);
  const [isOnline, setIsOnline] = useState(true);
  const [activeCount, setActiveCount] = useState(9);
  const [activeAgents, setActiveAgents] = useState(7);

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
          setActiveCount(data.tools_count ?? 9);
          // Count total configured agents from services object
          const agentCount = data.total_services_count ?? Object.keys(data.services ?? {}).length ?? 7;
          setActiveAgents(agentCount);
          if (data.tools && data.tools.length > 0) {
            setTools(data.tools);
          }
        }
      } catch {
        // Backend itself is unreachable — show amber
        if (mounted) {
          setIsOnline(false);
          setActiveCount(9);
          setActiveAgents(7);
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
