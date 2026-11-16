"use client";

import React, { useState } from "react";
import { X, Sparkles, Terminal, ArrowRight } from "lucide-react";

export interface MCPTool {
  name: string;
  agent: string;
  description: string;
  args: string[];
}

interface MCPToolExplorerModalProps {
  isOpen: boolean;
  onClose: () => void;
  tools: MCPTool[];
  onSelectToolForChat?: (toolName: string) => void;
}

export function MCPToolExplorerModal({
  isOpen,
  onClose,
  tools,
  onSelectToolForChat,
}: MCPToolExplorerModalProps) {
  const [selectedAgent, setSelectedAgent] = useState<string>("All");

  if (!isOpen) return null;

  const agents = ["All", ...Array.from(new Set(tools.map((t) => t.agent)))];

  const filteredTools =
    selectedAgent === "All"
      ? tools
      : tools.filter((t) => t.agent === selectedAgent);

  const getAgentColor = (agent: string) => {
    switch (agent) {
      case "Shmoo ML":
        return "bg-purple-950/40 text-purple-300 border-purple-800/40";
      case "Vector Memory":
        return "bg-cyan-950/40 text-cyan-300 border-cyan-800/40";
      case "Dynamic Limits":
        return "bg-amber-950/40 text-amber-300 border-amber-800/40";
      case "Retest AI":
        return "bg-emerald-950/40 text-emerald-300 border-emerald-800/40";
      case "STIL Setup":
        return "bg-indigo-950/40 text-indigo-300 border-indigo-800/40";
      case "Yield Advisor":
        return "bg-rose-950/40 text-rose-300 border-rose-800/40";
      case "Orchestrator":
        return "bg-blue-950/40 text-blue-300 border-blue-800/40";
      default:
        return "bg-slate-900 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl max-h-[85vh] flex flex-col rounded-2xl border border-[var(--line,#1e293b)] bg-[rgba(13,20,33,0.98)] shadow-[0_20px_60px_rgba(0,0,0,0.8)] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--line,#1e293b)] px-6 py-4 bg-[rgba(18,28,46,0.6)]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Terminal className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white tracking-wide">
                  Model Context Protocol (MCP) Registry
                </h3>
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-400 border border-emerald-500/20">
                  {tools.length} Tools Loaded
                </span>
              </div>
              <p className="text-xs text-[var(--muted,#94a3b8)]">
                AI agents can invoke these tools autonomously to execute tests & synthesize results.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line,#1e293b)] px-6 py-3 bg-[rgba(15,23,38,0.4)]">
          {agents.map((agent) => (
            <button
              key={agent}
              onClick={() => setSelectedAgent(agent)}
              className={`rounded-lg px-3 py-1 text-xs font-medium transition-all ${
                selectedAgent === agent
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                  : "bg-slate-900/40 text-slate-400 border border-slate-800 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              {agent === "All" ? `All (${tools.length})` : agent}
            </button>
          ))}
        </div>

        {/* Tools Grid */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3 custom-scrollbar">
          {filteredTools.map((tool) => (
            <div
              key={tool.name}
              className="group relative flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-[var(--line,#1e293b)] bg-[rgba(18,27,44,0.4)] p-4 transition-all hover:border-cyan-500/30 hover:bg-[rgba(22,34,55,0.6)]"
            >
              <div className="space-y-1.5 flex-1 pr-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-sm font-semibold text-white group-hover:text-cyan-300 transition-colors">
                    {tool.name}()
                  </span>
                  <span
                    className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${getAgentColor(
                      tool.agent
                    )}`}
                  >
                    {tool.agent}
                  </span>
                </div>
                <p className="text-xs text-[var(--muted,#94a3b8)] leading-relaxed">
                  {tool.description}
                </p>
                {tool.args && tool.args.length > 0 && (
                  <div className="flex items-center gap-1.5 pt-1">
                    <span className="text-[10.5px] text-slate-500">Parameters:</span>
                    {tool.args.map((arg) => (
                      <span
                        key={arg}
                        className="rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-700/60"
                      >
                        {arg}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {onSelectToolForChat && (
                <button
                  onClick={() => {
                    onSelectToolForChat(tool.name);
                    onClose();
                  }}
                  className="flex items-center gap-1.5 self-start sm:self-center shrink-0 rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-500/40 transition-all"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Ask Copilot
                  <ArrowRight className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-[var(--line,#1e293b)] px-6 py-3 bg-[rgba(15,23,38,0.7)] flex items-center justify-between text-xs text-[var(--muted,#94a3b8)]">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>FastMCP Server running on localhost (stdio transport active)</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1 text-slate-300 hover:text-white hover:bg-white/5 transition-colors font-medium"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}
