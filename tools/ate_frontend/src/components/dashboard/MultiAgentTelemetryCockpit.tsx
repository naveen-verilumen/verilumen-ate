"use client";

import React, { useState } from "react";
import {
  Activity,
  Zap,
  Sparkles,
  TrendingUp,
  Sliders,
  RotateCcw,
  FileCode,
  Search,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  Maximize2,
} from "lucide-react";

interface MultiAgentTelemetryCockpitProps {
  onInvestigate: (query: string) => void;
  activeWaferId?: string | null;
}

export function MultiAgentTelemetryCockpit({
  onInvestigate,
  activeWaferId = "WFR-9082",
}: MultiAgentTelemetryCockpitProps) {
  const [selectedDie, setSelectedDie] = useState<{ id: string; x: number; y: number; bin: string; code?: string } | null>({
    id: "DIE-06-08",
    x: 8,
    y: 6,
    bin: "fail",
    code: "FREQ_MARGIN",
  });

  // 48 ATE Tester Pins Matrix (Channels 00-47)
  const testerPins = Array.from({ length: 48 }, (_, i) => ({
    id: i,
    label: `CH${i.toString().padStart(2, "0")}`,
    active: i % 7 !== 0,
    speed: i < 8 ? "CLK" : i < 24 ? "SCAN" : "DATA",
  }));

  // Mini die grid for interactive circular 300mm wafer map
  const waferGridSize = 13;
  const waferRadius = 5.8;
  const waferCenter = 6;
  const waferDies = [];
  for (let r = 0; r < waferGridSize; r++) {
    for (let c = 0; c < waferGridSize; c++) {
      const dist = Math.sqrt((r - waferCenter) ** 2 + (c - waferCenter) ** 2);
      if (dist <= waferRadius) {
        let bin = "pass";
        let code = undefined;
        if (dist > 4.5 && (r + c) % 3 === 0) {
          bin = "fail";
          code = "EDGE_THERMAL";
        } else if ((r === 4 && c === 4) || (r === 6 && c === 8) || (r === 9 && c === 5)) {
          bin = "fail";
          code = "FREQ_MARGIN";
        } else if (dist > 4.0 && (r * c) % 7 === 0) {
          bin = "retest";
          code = "MARGINAL_VDD";
        }
        waferDies.push({
          id: `DIE-${r.toString().padStart(2, "0")}-${c.toString().padStart(2, "0")}`,
          r,
          c,
          bin,
          code,
        });
      }
    }
  }

  // Simulated Pass/Fail points for Shmoo with explicit typing
  const shmooPoints: { x: number; y: number; pass: boolean }[] = [
    { x: 30, y: 75, pass: true },
    { x: 45, y: 72, pass: true },
    { x: 60, y: 68, pass: true },
    { x: 75, y: 60, pass: true },
    { x: 90, y: 52, pass: true },
    { x: 105, y: 45, pass: true },
    { x: 120, y: 38, pass: true },
    { x: 135, y: 30, pass: true },
    { x: 150, y: 22, pass: true },
    { x: 165, y: 15, pass: true },
    { x: 45, y: 45, pass: false },
    { x: 60, y: 35, pass: false },
    { x: 75, y: 30, pass: false },
    { x: 90, y: 20, pass: false },
    { x: 105, y: 15, pass: false },
  ];

  return (
    <div className="flex flex-col gap-5 text-white">
      {/* ─────────────────────────────────────────────────────────────────────────────
          1. TOP OPERATIONAL STATUS BAR (Clean, Professional, No Port Numbers)
          ───────────────────────────────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-base font-bold text-white tracking-wide">
                  {activeWaferId ?? "WFR-9082"}
                </span>
                <span className="rounded bg-white/[0.05] border border-white/10 px-2.5 py-0.5 text-xs font-mono text-slate-300">
                  LOT-2024-001 · 300mm
                </span>
                <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/25 px-2.5 py-0.5 text-xs font-medium text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  ATE RUNNING
                </span>
              </div>
              <div className="flex items-center gap-6 text-xs text-slate-400 mt-1.5">
                <span>First Pass Yield: <strong className="text-white font-mono text-sm">92.4%</strong></span>
                <span>Final Yield: <strong className="text-emerald-400 font-mono text-sm">94.2%</strong></span>
                <span>Tested: <strong className="text-slate-200 font-mono text-sm">180 / 180 dies</strong></span>
              </div>
            </div>
          </div>

          <button
            onClick={() => onInvestigate("Audit current wafer across all models and summarize the findings")}
            className="flex items-center gap-2 rounded-lg border border-[var(--line-bright,#2c3a50)] bg-white/[0.05] px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-white/[0.09] hover:text-white transition-colors"
          >
            <Sparkles className="h-4 w-4 text-cyan-300" />
            <span>Full Wafer Audit</span>
          </button>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────────────────────
          2. MULTI-AGENT TELEMETRY GRID (ARRANGED IN STRICT ALPHABETICAL ORDER)
          1. Dynamic Limits (DTL)
          2. Log Analyzer
          3. M-BIST Shmoo
          4. RA Advisor
          5. Retest AI
          6. STIL Setup
          7. Vector Memory
          8. Yield Advisor
          ───────────────────────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

        {/* ── 1. DYNAMIC LIMITS (DTL) ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  Dynamic Limits (DTL)
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">Temporal GRU · 3-Month Drift Guardbands</p>
              </div>
              <button
                onClick={() => onInvestigate("Recommend dynamic test limits for the current wafer lot")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Dynamic Guardband Trend Comparison */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3.5 mb-3.5">
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="text-slate-300 font-medium">Adaptive Limit Shifts (vs Static)</span>
                <span className="text-amber-300 font-mono text-xs">TemporalHybrid</span>
              </div>
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">IDDQ_nom:</span>
                  <span className="text-emerald-400 font-medium">1.50mA → 1.42mA (+0.22 Cpk)</span>
                </div>
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">Freq_max:</span>
                  <span className="text-cyan-300 font-medium">2.25GHz → 2.18GHz (+0.45% yield)</span>
                </div>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">False Fails</span>
                <span className="font-mono text-sm font-bold text-emerald-400">-42.1%</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Drift Window</span>
                <span className="font-mono text-sm font-bold text-amber-300">90 Days</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Escape Risk</span>
                <span className="font-mono text-sm font-bold text-white">0.00% Zero</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 2. LOG ANALYZER ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  Log Analyzer
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">Adaptive Scan Pattern Prior · Likelihood Diagnostics</p>
              </div>
              <button
                onClick={() => onInvestigate("Audit scan pattern failure probabilities and adaptive log analyzer rankings")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Pattern Prior Diagnostics */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3.5 mb-3.5">
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="text-slate-300 font-medium">Top Correlated Scan Chains</span>
                <span className="text-sky-300 font-mono text-xs">P38 · P45 · P141</span>
              </div>
              <div className="space-y-1.5 text-xs font-mono">
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">Chain P38 Failure Prob:</span>
                  <span className="text-rose-400 font-medium">84.2% (Thermal Edge)</span>
                </div>
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">Chain P45 Failure Prob:</span>
                  <span className="text-amber-400 font-medium">62.8% (Perimeter Drift)</span>
                </div>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Tracked Patterns</span>
                <span className="font-mono text-sm font-bold text-white">200 / Die</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Catalog Scope</span>
                <span className="font-mono text-sm font-bold text-sky-300">9 Lots</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Policy Mode</span>
                <span className="font-mono text-sm font-bold text-emerald-400">ML Adaptive</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 3. M-BIST SHMOO ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  M-BIST Shmoo
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">Operating Margin · Statistical Process Capability</p>
              </div>
              <button
                onClick={() => onInvestigate("Explain the current Shmoo operating margin, speedpath boundary, and recommended Vdd/Freq")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Interactive Visual Shmoo Plot Canvas */}
            <div className="relative rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3 mb-3.5">
              <div className="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                <span>Frequency (GHz) vs VDD (V)</span>
                <span className="text-purple-300 font-mono text-xs">Linear Speedpath</span>
              </div>
              <svg viewBox="0 0 240 100" className="w-full h-24 overflow-visible">
                <line x1="20" y1="10" x2="230" y2="10" stroke="#1a2433" strokeDasharray="2,2" />
                <line x1="20" y1="45" x2="230" y2="45" stroke="#1a2433" strokeDasharray="2,2" />
                <line x1="20" y1="80" x2="230" y2="80" stroke="#2c3a50" />
                <line x1="20" y1="10" x2="20" y2="80" stroke="#2c3a50" />

                {shmooPoints.map((pt, idx) => (
                  <circle
                    key={idx}
                    cx={pt.x}
                    cy={pt.y}
                    r={pt.pass ? 2.5 : 2}
                    fill={pt.pass ? "#10b981" : "#ef4444"}
                    opacity={pt.pass ? 0.85 : 0.6}
                  />
                ))}

                <line
                  x1="25"
                  y1="82"
                  x2="185"
                  y2="10"
                  stroke="#a855f7"
                  strokeWidth="1.5"
                  strokeDasharray="4,2"
                />

                <circle cx="110" cy="45" r="4" fill="#a855f7" stroke="#ffffff" strokeWidth="1" />
                <text x="120" y="48" fill="#e9d5ff" fontSize="10" fontFamily="monospace">
                  Rec: 0.975V @ 1.486GHz
                </text>
              </svg>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Boundary Margin</span>
                <span className="font-mono text-sm font-bold text-purple-300">R² = 0.998</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Cycles Saved</span>
                <span className="font-mono text-sm font-bold text-emerald-400">-82.8%</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Cpk (Vmin)</span>
                <span className="font-mono text-sm font-bold text-cyan-300">1.45 Capable</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 4. RA ADVISOR (MEMORY BISR / BIRA) ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  RA Advisor
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">Memory Built-in Self-Repair · Feasibility Safety Net</p>
              </div>
              <button
                onClick={() => onInvestigate("How does RA Advisor solve memory repair using LightGBM and spare budget constraints?")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Bitmap & Repair Strategy Preview */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3.5 mb-3.5">
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="text-slate-300 font-medium">BIRA Repair Strategy: COMBO</span>
                <span className="text-emerald-400 font-mono text-xs font-semibold">100% Repaired</span>
              </div>
              <div className="space-y-1.5 text-xs font-mono">
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">Algorithm Solved:</span>
                  <span className="text-cyan-300 font-medium">ROW_COL_COMBO (2 Spare R, 1 Spare C)</span>
                </div>
                <div className="flex justify-between items-center bg-[var(--panel,#0c121b)] border border-[var(--line,#1a2433)] px-2.5 py-1.5 rounded">
                  <span className="text-slate-400">Spare Budget:</span>
                  <span className="text-emerald-400 font-medium">4R / 4C / 1BLK (Feasible)</span>
                </div>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Solve Time</span>
                <span className="font-mono text-sm font-bold text-cyan-300">1.8 ms</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Model Accuracy</span>
                <span className="font-mono text-sm font-bold text-emerald-400">96.8%</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">False Scrap</span>
                <span className="font-mono text-sm font-bold text-white">0.00% Zero</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 5. RETEST AI ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  Retest AI
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">Second-Pass Classifier · Recovery Attribution</p>
              </div>
              <button
                onClick={() => onInvestigate("Why did the retest evaluation recommend SKIP? Show decision factors for fail bin 45")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Decision Status */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3.5 mb-3.5">
              <div className="flex justify-between items-center mb-2 text-xs">
                <span className="text-slate-300 font-medium">Live Decision: DEV-014</span>
                <span className="rounded bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 text-xs font-semibold text-rose-300">
                  SKIP (P=12.8%)
                </span>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Fail_Bin = 45</span>
                  <div className="w-28 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div className="bg-rose-500 h-full w-[85%]" />
                  </div>
                  <span className="font-mono text-rose-300 text-xs">-0.42</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Test_Time = 0.25s</span>
                  <div className="w-28 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div className="bg-rose-500 h-full w-[55%]" />
                  </div>
                  <span className="font-mono text-rose-300 text-xs">-0.28</span>
                </div>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">SKIP Ratio</span>
                <span className="font-mono text-sm font-bold text-emerald-400">74.2%</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Annual Savings</span>
                <span className="font-mono text-sm font-bold text-amber-300">$45,200</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Tester Rate</span>
                <span className="font-mono text-sm font-bold text-white">$250/hr</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 6. STIL SETUP ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  STIL Setup
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">IEEE 1450 STIL · 48 I/O Channels · CUDA GBC</p>
              </div>
              <button
                onClick={() => onInvestigate("Optimize STIL timing setup and minimize clock skew with CUDA GBC")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* 48-Pin Tester Channel Heatmap */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3 mb-3.5">
              <div className="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                <span>48-Channel Tester Pin Matrix (CUDA Deskew Active)</span>
                <span className="text-indigo-300 font-mono text-xs">+14.2% Margin</span>
              </div>
              <div className="grid grid-cols-12 gap-1">
                {testerPins.map((pin) => (
                  <div
                    key={pin.id}
                    title={`${pin.label} (${pin.speed})`}
                    className={`h-3 rounded-xs text-[8px] flex items-center justify-center font-mono ${
                      pin.speed === "CLK"
                        ? "bg-indigo-600 text-white"
                        : pin.speed === "SCAN"
                        ? "bg-cyan-600 text-white font-medium"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  />
                ))}
              </div>
              <div className="flex justify-between text-xs text-slate-500 mt-2 font-mono">
                <span>Ch 00-11: Clocks</span>
                <span>Ch 12-23: Scan</span>
                <span>Ch 24-47: I/O Data</span>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Scan Chains</span>
                <span className="font-mono text-sm font-bold text-white">8 Parallel</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Clock Deskew</span>
                <span className="font-mono text-sm font-bold text-emerald-400">+14.2%</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Master Clock</span>
                <span className="font-mono text-sm font-bold text-indigo-300">100 MHz</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 7. VECTOR MEMORY ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  Vector Memory
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">LSTM STIL Compressor · Cycle Pruning</p>
              </div>
              <button
                onClick={() => onInvestigate("How much test time did STIL vector compression save?")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Vector RAM Reduction Bar */}
            <div className="rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3.5 mb-3.5">
              <div className="flex justify-between items-center text-xs mb-2">
                <span className="text-slate-300 font-medium">Tester Pin RAM Footprint</span>
                <span className="font-mono font-semibold text-emerald-400">-72.8% Savings</span>
              </div>
              <div className="h-2.5 w-full bg-slate-800 rounded-full overflow-hidden p-0.5 flex">
                <div
                  className="h-full bg-cyan-500 rounded-full"
                  style={{ width: "27.2%" }}
                  title="Retained Patterns: 4.82 MB"
                />
              </div>
              <div className="flex justify-between items-center text-xs text-slate-400 mt-2 font-mono">
                <span>Compressed: 4.82 MB</span>
                <span>Original: 18.16 MB</span>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Die Test Time</span>
                <span className="font-mono text-sm font-bold text-cyan-300">33.8 ms</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Time Saved / Die</span>
                <span className="font-mono text-sm font-bold text-emerald-400">90.7 ms</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Fault Coverage</span>
                <span className="font-mono text-sm font-bold text-white">100.0% Cov</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── 8. YIELD ADVISOR ── */}
        <div className="rounded-xl border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] p-5 shadow-sm hover:border-[var(--line-bright,#2c3a50)] transition-colors flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[var(--line,#1a2433)] pb-3 mb-3">
              <div>
                <h4 className="text-sm font-bold text-white tracking-wide">
                  Yield Advisor
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">FPY Pareto Recovery · Thermal Soak Spatial Analytics</p>
              </div>
              <button
                onClick={() => onInvestigate("Audit First Pass Yield and failure bin Pareto distribution")}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-[var(--line,#1a2433)] rounded-lg px-3 py-1.5 transition-colors"
              >
                <span>Ask AI</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Interactive Circular 300mm Wafer Map & Pareto */}
            <div className="flex items-center gap-4 rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel-2,#08101a)] p-3 mb-3.5">
              <div className="relative w-24 h-24 rounded-full border border-slate-700 bg-slate-900/90 p-1 flex items-center justify-center shrink-0">
                <div className="grid grid-cols-13 gap-[1.5px] w-full h-full p-1 items-center justify-center">
                  {waferDies.map((die) => (
                    <div
                      key={die.id}
                      onClick={() => {
                        setSelectedDie({ id: die.id, x: die.c, y: die.r, bin: die.bin, code: die.code });
                        if (die.bin === "fail") {
                          onInvestigate(`Why did die ${die.id} fail with code ${die.code || "UNKNOWN"} on wafer WFR-9082?`);
                        }
                      }}
                      className={`w-[4.5px] h-[4.5px] rounded-xs cursor-pointer transition-transform hover:scale-125 ${
                        die.bin === "pass"
                          ? "bg-emerald-500"
                          : die.bin === "retest"
                          ? "bg-amber-500"
                          : "bg-rose-500"
                      }`}
                      title={`${die.id} (${die.bin.toUpperCase()})`}
                    />
                  ))}
                </div>
              </div>

              <div className="flex-1 space-y-1.5 text-xs">
                <div className="text-slate-300 text-xs font-medium">Yield Loss Pareto Drivers</div>
                <div>
                  <div className="flex justify-between text-xs">
                    <span className="text-rose-300">Bin 4 Parametric</span>
                    <span className="font-mono text-slate-300">48%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 mt-1">
                    <div className="bg-rose-500 h-full w-[48%]" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs">
                    <span className="text-amber-300">Bin 2 Timing</span>
                    <span className="font-mono text-slate-300">26%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 mt-1">
                    <div className="bg-amber-500 h-full w-[26%]" />
                  </div>
                </div>
              </div>
            </div>

            {/* Metrics Chips */}
            <div className="grid grid-cols-3 gap-2.5 text-center">
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Thermal Soak</span>
                <span className="font-mono text-sm font-bold text-emerald-400">+1.8% Yield</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Total Recovery</span>
                <span className="font-mono text-sm font-bold text-cyan-300">+2.7% Net</span>
              </div>
              <div className="rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] p-2.5">
                <span className="text-xs text-slate-400 block mb-0.5">Selected Die</span>
                <span className="font-mono text-sm font-bold text-rose-300">{selectedDie?.id ?? "None"}</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
