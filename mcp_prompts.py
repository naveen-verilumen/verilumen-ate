"""
Verilumen ATE Intelligence — 10 Engineering Scenario MCP Prompts
===============================================================
Exposes the 10 pre-authored cross-domain and single-domain ATE engineering
scenarios as FastMCP prompts backed by live structured telemetry envelopes so
connected LLMs reason directly over measured silicon data instead of static text.

Deterministic templates remain in `mcp_router.py` exclusively as the offline
fallback for the in-dashboard copilot UI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, List
from fastmcp import FastMCP
from fastmcp.prompts import Message, PromptResult


EnvelopeFetcher = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


async def _build_scenario_prompt(
    *,
    scenario_title: str,
    objective: str,
    agents: List[str],
    params: Dict[str, Any],
    reasoning_steps: List[str],
    fetch_envelope: EnvelopeFetcher,
) -> PromptResult:
    """Fetch real telemetry envelopes for each scenario agent and compose a grounded PromptResult."""
    results = await asyncio.gather(
        *[fetch_envelope(agent, params) for agent in agents],
        return_exceptions=True,
    )
    envelopes: Dict[str, Any] = {}
    for agent, res in zip(agents, results):
        if isinstance(res, Exception):
            envelopes[agent] = {"status": "error", "error": str(res)}
        else:
            envelopes[agent] = res

    resource_refs = [f"ate://results/{agent}/latest" for agent in agents]
    checklist = "\n".join(f"{i}. {step}" for i, step in enumerate(reasoning_steps, start=1))
    prompt_text = (
        f"Engineering Scenario: {scenario_title}\n"
        f"Objective: {objective}\n\n"
        f"Parameters Under Investigation:\n{json.dumps(params, indent=2)}\n\n"
        f"Subscribed Live MCP Resources Available: {', '.join(resource_refs)}\n\n"
        f"Live Telemetry Envelopes (Reason strictly over these real values — do not invent numbers):\n"
        f"```json\n{json.dumps(envelopes, indent=2, default=str)[:12000]}\n```\n\n"
        f"Required Engineering Reasoning Steps:\n{checklist}\n\n"
        "Output concise, quantitative ATE recommendations citing exact measured values "
        "(Vdd, Fmax, Cpk, P(benefit), SHAP drivers, vector compression %, yield impact, or scan patterns). "
        "If fresh wafer/die sweeps are requested or any envelope shows source='fallback', invoke "
        "`run_analysis`, `explain_retest_decision`, or `full_wafer_analysis` to obtain live data."
    )
    return PromptResult(
        description=f"{scenario_title}: {objective}",
        messages=[Message(prompt_text, role="user")],
    )


def register_prompts(mcp: FastMCP, fetch_envelope: EnvelopeFetcher) -> None:
    """Register all 10 ATE engineering scenario prompts on the FastMCP server."""

    @mcp.prompt(tags={"shmoo", "retest", "cross-domain"})
    async def voltage_margin_vs_retest_skip(
        vdd_v: float = 1.10, wafer_id: str = "W4", fail_bin: int = 45
    ) -> PromptResult:
        """Scenario 1: Determine if increasing VDD recovers failing dies or if Retest SKIP should be enforced."""
        return await _build_scenario_prompt(
            scenario_title="Shmoo Voltage Headroom vs. Retest SKIP Enforcement",
            objective=(
                f"Evaluate whether raising VDD to {vdd_v:.2f}V on Wafer {wafer_id} recovers "
                f"Bin {fail_bin} failures or whether Retest AI confirms an unrecoverable physical defect."
            ),
            agents=["shmoo", "retest"],
            params={"vdd": vdd_v, "voltage_v": vdd_v, "wafer_id": wafer_id, "fail_bin": fail_bin},
            reasoning_steps=[
                "Compare queried VDD against Shmoo recommended_vdd, Vmin, and voltage_margin_v to verify supply headroom.",
                "Check Shmoo Cpk(Vmin) and Fmax speedpath linearity to distinguish droop starvation from hard defects.",
                "Inspect Retest AI P(benefit) probability and top TreeSHAP contributors for the given fail_bin.",
                "Conclude whether raising VDD wastes thermal budget or helps recovery, and state final SKIP/RETEST policy.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"shmoo", "yield", "cross-domain"})
    async def shmoo_operating_point_to_yield(
        wafer_id: str = "WFR-9082", lot_id: str = "LOT-2026-A1"
    ) -> PromptResult:
        """Scenario 2: Correlate Shmoo recommended setpoint with outer-ring wafer yield and FPY recovery."""
        return await _build_scenario_prompt(
            scenario_title="Shmoo Operating Setpoint Impact on First Pass Yield",
            objective=f"Quantify how applying Shmoo Vdd/Freq guardbands stabilizes outer-ring FPY on {wafer_id}.",
            agents=["shmoo", "yield_advisor"],
            params={"wafer_id": wafer_id, "lot_id": lot_id},
            reasoning_steps=[
                "Extract Shmoo optimal operating setpoint (recommended_vdd, recommended_freq) and SPC guardbands.",
                "Compare Yield Advisor overall yield, FPY, top Pareto loss bins, and spatial edge-ring concentration.",
                "Connect edge thermal/IR-drop sensitivity to recommended thermal soak and guardband actions.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"test_time", "stil", "cross-domain"})
    async def vector_compression_on_stil_chains(
        filename: str = "Production_SCAN_stuck_at_1000pat.stil",
    ) -> PromptResult:
        """Scenario 3: Evaluate scan vector compression impact on STIL scan chains, pin RAM, and timing coverage."""
        return await _build_scenario_prompt(
            scenario_title="Vector Compression Across Active STIL Scan Chains",
            objective=f"Assess pin RAM savings, execution speedup, and scan timing integrity for {filename}.",
            agents=["test_time", "stil"],
            params={"filename": filename, "filenames": [filename]},
            reasoning_steps=[
                "Review STIL scan chain count, reset pins, signal channels, and waveform period from the STIL envelope.",
                "Inspect Test Time Optimizer retained vs. discarded pattern counts, MB saved, and ms/die speedup.",
                "Verify CUDA GBC timing slack/deskew ensures zero setup/hold violations at compressed burst lengths.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"dtl", "retest", "cross-domain"})
    async def dtl_iddq_tightening_vs_retest(
        lot_id: str = "LOT-2024-001", target_cpk: float = 1.50
    ) -> PromptResult:
        """Scenario 4: Quantify how tightening DTL IDDQ guardbands eliminates redundant retest cycles."""
        return await _build_scenario_prompt(
            scenario_title="Dynamic IDDQ Guardband Tightening vs. Retest Reduction",
            objective=f"Correlate DTL parametric IDDQ tightening on {lot_id} (target Cpk {target_cpk}) with Retest suppression.",
            agents=["dtl", "retest"],
            params={"lot_id": lot_id, "target_cpk": target_cpk},
            reasoning_steps=[
                "Inspect DTL recommended IDDQ/Fmax/Vmin limits and Cpk deltas across recent drift windows.",
                "Review Retest AI historical batch metrics (unnecessary retests suppressed %, tester savings USD).",
                "Explain how tighter first-pass screening intercepts latent marginal defects before second-pass retests.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"dtl", "yield", "cross-domain"})
    async def dtl_relaxation_for_yield_recovery(
        lot_id: str = "LOT-2024-001", dataset_id: str = "yi_synthetic_v2"
    ) -> PromptResult:
        """Scenario 5: Evaluate safely relaxing over-conservative parametric limits to recover false yield fallout."""
        return await _build_scenario_prompt(
            scenario_title="Dynamic Test Limit Relaxation for False-Fail Yield Recovery",
            objective=f"Identify over-guardbanded tests on {lot_id}/{dataset_id} where Cpk allows safe relaxation.",
            agents=["dtl", "yield_advisor"],
            params={"lot_id": lot_id, "dataset_id": dataset_id},
            reasoning_steps=[
                "Examine DTL 3-month Cpk trends and candidate relaxation recommendations.",
                "Cross-reference Yield Advisor false-margin Pareto bins and recoverable yield percentages.",
                "Specify verification criteria to ensure zero customer escape / DPM regression.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"stil", "shmoo", "cross-domain"})
    async def stil_deskew_to_fmax_headroom(
        filename: str = "Production_SCAN_stuck_at_1000pat.stil",
    ) -> PromptResult:
        """Scenario 6: Quantify how CUDA GBC STIL clock deskew expands usable Shmoo Fmax headroom."""
        return await _build_scenario_prompt(
            scenario_title="STIL Clock Deskew Impact on Shmoo Fmax Headroom",
            objective="Connect tester channel skew removal in STIL timing tables to observed Fmax speedpath margin.",
            agents=["stil", "shmoo"],
            params={"filename": filename, "filenames": [filename]},
            reasoning_steps=[
                "Extract STIL setup/hold slack, clock skew, and CUDA optimization margin from the STIL envelope.",
                "Compare against Shmoo Cpk(Fmax), recommended_freq, and freq_margin_ghz.",
                "Determine safe Fmax setpoint shift and fixture jitter margin gained.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"test_time", "yield", "cross-domain"})
    async def vector_compression_vs_thermal_yield(
        compression_target_pct: float = 70.0, wafer_id: str = "WFR-9082"
    ) -> PromptResult:
        """Scenario 7: Trade off aggressive vector compression against thermal chuck soak yield stability."""
        return await _build_scenario_prompt(
            scenario_title="Vector Compression Dwell Reduction vs. Thermal Wafer Yield",
            objective=(
                f"Evaluate whether compressing test vectors by ~{compression_target_pct:.0f}% on {wafer_id} "
                "affects edge-die thermal soak stability or fault coverage."
            ),
            agents=["test_time", "yield_advisor"],
            params={"percentage": compression_target_pct, "wafer_id": wafer_id},
            reasoning_steps=[
                "Review compressed vector cycle count, ms/die savings, and self-heating dwell reduction.",
                "Inspect Yield Advisor edge-ring thermal sensitivity and chuck soak recommendations.",
                "Define prober thermal soak prerequisites required alongside compressed bursts.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"shmoo", "dtl", "retest", "3-way"})
    async def shmoo_dtl_retest_triage(
        wafer_id: str = "W4", fail_bin: int = 45
    ) -> PromptResult:
        """Scenario 8: Three-way root-cause triage across Shmoo margins, DTL drift, and Retest policy."""
        return await _build_scenario_prompt(
            scenario_title="3-Way Triage: Supply Headroom, Limit Drift & Retest Policy",
            objective=f"Triangulate Wafer {wafer_id} Bin {fail_bin} failures across Shmoo ML, DTL, and Retest AI.",
            agents=["shmoo", "dtl", "retest"],
            params={"wafer_id": wafer_id, "fail_bin": fail_bin},
            reasoning_steps=[
                "Verify voltage/frequency margin capability in Shmoo ML.",
                "Audit IDDQ/Vmin drift and recommended limit tightening in DTL.",
                "Synthesize P(benefit) + SHAP scores in Retest AI to issue unified test floor policy.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"stil", "test_time", "yield", "3-way"})
    async def stil_test_time_yield_optimization(lot_id: str = "LOT-2024-001") -> PromptResult:
        """Scenario 9: Combine STIL deskew, scan vector compression, and yield thermal calibration."""
        return await _build_scenario_prompt(
            scenario_title="3-Way Co-Optimization: STIL Timing, Vector RAM & Yield Recovery",
            objective=f"Design a unified test-time + FPY optimization plan for {lot_id}.",
            agents=["stil", "test_time", "yield_advisor"],
            params={"lot_id": lot_id},
            reasoning_steps=[
                "Quantify STIL setup pruning and CUDA GBC deskew improvements.",
                "Combine with LSTM vector RAM savings and per-die cycle time reduction.",
                "Project net UPH and First Pass Yield gain while preserving thermal equilibrium.",
            ],
            fetch_envelope=fetch_envelope,
        )

    @mcp.prompt(tags={"audit", "cross-domain", "full-suite"})
    async def full_wafer_triangulation_audit(
        wafer_id: str = "WFR-9082", lot_id: str = "LOT-2024-001", cost_per_hour: float = 250.0
    ) -> PromptResult:
        """Scenario 10: Comprehensive cross-domain correlation audit across all 7 ATE engines."""
        return await _build_scenario_prompt(
            scenario_title="Full 7-Agent Wafer Intelligence Triangulation Audit",
            objective=(
                f"Synthesize cohesive engineering findings across all 7 ATE engines for {wafer_id} / {lot_id} "
                f"(tester rate ${cost_per_hour:.0f}/hr)."
            ),
            agents=["shmoo", "test_time", "dtl", "retest", "stil", "yield_advisor", "log_analyzer"],
            params={"wafer_id": wafer_id, "lot_id": lot_id, "cost_per_hour": cost_per_hour},
            reasoning_steps=[
                "Summarize critical telemetry KPIs from each of the 7 engines with zero fabrication.",
                "Highlight cross-engine reinforcements (e.g. Shmoo+DTL guardbands, STIL+TestTime+LogAnalyzer scan efficiency, Retest+Yield ROI).",
                "Produce prioritized, concrete ATE production floor recommendations.",
            ],
            fetch_envelope=fetch_envelope,
        )
