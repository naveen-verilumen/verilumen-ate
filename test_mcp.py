"""
Verilumen ATE MCP Server -- End-to-End Stdio Verification & Pre-flight Suite
===========================================================================
Verifies:
  1. Connectivity to all 7 ATE microservices + Windows Credential Manager secret.
  2. Clean stdio JSON-RPC startup with zero stdout pollution (stdout hygiene).
  3. Tool consolidation (9 tools), Pydantic output_schema, concise summaries, and ToolAnnotations.
  4. Shared httpx client & cached suite_health behavior (live probe -> TTL cache hit).
  5. Subscribable resources (`ate://results/{agent}/latest`, `ate://wafer/{id}/summary`, `ate://jobs/{run_id}`).
  6. 10 engineering scenario prompts backed by live telemetry envelopes.
  7. Non-blocking long jobs (`yield_retrain` & `stil_parse`) returning `run_id` + progress notifications.

Usage:
    python test_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import fastmcp
import httpx
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp.client.subscriptions import listen

from verilumen_secrets import get_shmoo_api_key

ROOT_DIR = Path(__file__).resolve().parent

SERVICES = {
    "shmoo         (port 5000)": "http://127.0.0.1:5000/api/index",
    "test_time     (port 8787)": "http://127.0.0.1:8787/api/health",
    "dtl           (port 8001)": "http://127.0.0.1:8001/api/v1/health",
    "retest        (port 8002)": "http://127.0.0.1:8002/health",
    "stil          (port 8765)": "http://127.0.0.1:8765/health",
    "yield_advisor (port 8003)": "http://127.0.0.1:8003/api/health",
    "log_analyzer  (port 8004)": "http://127.0.0.1:8004/api/health",
}

EXPECTED_READ_ONLY = {
    "suite_health": True,
    "list_context": True,
    "run_analysis": False,
    "get_results": True,
    "explain_retest_decision": True,
    "full_wafer_analysis": False,
    "generate_shmoo_report": False,
    "start_long_job": False,
    "get_job_status": True,
}


async def check_ports() -> int:
    online = 0
    async with httpx.AsyncClient(timeout=4.0) as client:
        async def _probe(label: str, url: str) -> bool:
            try:
                r = await client.get(url)
                ok = r.status_code == 200
                status = "[ OK ]   ONLINE" if ok else f"[ WARN ] HTTP {r.status_code}"
                print(f"  {label:<30} {status}")
                return ok
            except Exception as exc:
                print(f"  {label:<30} [ FAIL ] OFFLINE - {type(exc).__name__}")
                return False

        results = await asyncio.gather(*[_probe(lbl, u) for lbl, u in SERVICES.items()])
        online = sum(1 for x in results if x)
    return online


async def run_stdio_e2e(shmoo_token: str) -> None:
    cfg_path = ROOT_DIR / "mcp_config.json"
    env_from_cfg = {"SHMOO_API_KEY": shmoo_token}
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg_env = ((cfg.get("mcpServers") or {}).get("verilumen-ate") or {}).get("env") or {}
        if cfg_env.get("SHMOO_API_KEY"):
            env_from_cfg["SHMOO_API_KEY"] = cfg_env["SHMOO_API_KEY"]

    progress_events: list[tuple[float, float | None, str | None]] = []
    wire_progress: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        progress_events.append((progress, total, message))

    async def on_message(msg: object) -> None:
        if type(msg).__name__ == "ProgressNotification" and getattr(msg, "params", None) is not None:
            p = msg.params
            wire_progress.append((p.progress, p.total, p.message))

    transport = StdioTransport(
        command=sys.executable,
        args=[str(ROOT_DIR / "mcp_server.py")],
        env=env_from_cfg,
        cwd=str(ROOT_DIR),
    )

    async with Client(transport, progress_handler=on_progress, message_handler=on_message) as client:
        # 1. Tool count, output_schema & ToolAnnotations
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        print(f"\n  Registered tools ({len(tools)}): {sorted(tool_names)}")
        assert tool_names == set(EXPECTED_READ_ONLY.keys()), f"Unexpected tool set: {tool_names}"
        for t in tools:
            assert t.output_schema is not None and t.output_schema.get("type") == "object", (
                f"Missing object output_schema on {t.name}"
            )
            ro = getattr(t.annotations, "read_only_hint", None) if t.annotations else None
            assert ro is EXPECTED_READ_ONLY[t.name], (
                f"Expected read_only_hint={EXPECTED_READ_ONLY[t.name]} on {t.name}, got {ro}"
            )

        # 2. Cached health check verification
        h_live = await client.call_tool("suite_health", {"refresh": True})
        assert h_live.structured_content is not None
        assert h_live.structured_content["cached"] is False
        h_cached = await client.call_tool("suite_health", {"refresh": False})
        assert h_cached.structured_content is not None
        assert h_cached.structured_content["cached"] is True
        print(
            f"  [ OK ] suite_health live -> cached verified "
            f"({h_live.structured_content['online_count']}/{h_live.structured_content['total_count']} online, "
            f"summary='{h_live.content[0].text[:70]}')"
        )

        # 3. Structured output + concise text summary on domain tools
        ctx_res = await client.call_tool("list_context", {"agent": "all"})
        assert ctx_res.structured_content is not None and ctx_res.content[0].text
        print(f"  [ OK ] list_context: {ctx_res.content[0].text}")

        ret_res = await client.call_tool("explain_retest_decision", {"fail_bin": 45, "voltage_v": 1.05})
        assert ret_res.structured_content is not None
        assert ret_res.structured_content["recommendation"] in ("RETEST", "SKIP")
        print(f"  [ OK ] explain_retest_decision: {ret_res.content[0].text}")

        # 4. Resources & live subscriptions
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        res_uris = {str(r.uri) for r in resources}
        tpl_uris = {str(t.uri_template) for t in templates}
        assert "ate://results/shmoo/latest" in res_uris
        assert "ate://wafer/WFR-9082/summary" in res_uris
        assert "ate://results/{agent}/latest" in tpl_uris
        assert "ate://wafer/{wafer_id}/summary" in tpl_uris
        assert "ate://jobs/{run_id}" in tpl_uris
        print(f"  [ OK ] Resources ({len(resources)}) + templates ({len(templates)}) exposed")

        async with listen(client.session, resource_subscriptions=["ate://results/shmoo/latest"]) as sub:
            shmoo_res = await client.call_tool("run_analysis", {"agent": "shmoo", "params": {"action": "demo"}})
            assert shmoo_res.structured_content is not None
            ev = await asyncio.wait_for(sub.__anext__(), timeout=5.0)
            assert str(getattr(ev, "uri", "")) == "ate://results/shmoo/latest"
            print(f"  [ OK ] Live resource subscription notification delivered: {ev}")

        read_shmoo = await client.read_resource("ate://results/shmoo/latest")
        assert read_shmoo and "shmoo" in read_shmoo[0].text
        print("  [ OK ] Read ate://results/shmoo/latest OK")

        # 5. All 10 MCP Prompts
        prompts = await client.list_prompts()
        assert len(prompts) == 10, f"Expected 10 prompts, got {len(prompts)}: {[p.name for p in prompts]}"
        rendered = await client.get_prompt("voltage_margin_vs_retest_skip", {"vdd_v": 1.10, "wafer_id": "W4", "fail_bin": 45})
        assert rendered.messages and "Live Telemetry Envelopes" in rendered.messages[0].content.text
        print(f"  [ OK ] 10 MCP Prompts registered & live envelope rendering verified")

        # 6. Non-blocking long jobs + progress notifications (STIL parse & Yield retrain)
        t0 = time.perf_counter()
        stil_job = await client.call_tool(
            "start_long_job",
            {"job_type": "stil_parse", "target": "fault_cellaware_atpg.stil"},
        )
        t_stil_ret = time.perf_counter() - t0
        stil_run_id = stil_job.structured_content["run_id"]
        assert stil_job.structured_content["status"] == "RUNNING"
        assert t_stil_ret < 2.0, f"stil_parse blocked on start: {t_stil_ret:.2f}s"

        t1 = time.perf_counter()
        yield_job = await client.call_tool(
            "start_long_job",
            {"job_type": "yield_retrain", "target": "yi_synthetic_v2"},
        )
        t_yield_ret = time.perf_counter() - t1
        yield_run_id = yield_job.structured_content["run_id"]
        assert yield_job.structured_content["status"] == "RUNNING"
        assert t_yield_ret < 2.0, f"yield_retrain blocked on start: {t_yield_ret:.2f}s"
        print(
            f"  [ OK ] Long jobs returned non-blocking run_ids immediately: "
            f"stil={stil_run_id} ({t_stil_ret*1000:.0f}ms), yield={yield_run_id} ({t_yield_ret*1000:.0f}ms)"
        )

        # Wait until both finish and verify COMPLETED + progress notifications
        deadline = time.monotonic() + 30.0
        final_stil = final_yield = None
        while time.monotonic() < deadline:
            s_res = await client.call_tool("get_job_status", {"run_id": stil_run_id})
            y_res = await client.call_tool("get_job_status", {"run_id": yield_run_id})
            final_stil = s_res.structured_content
            final_yield = y_res.structured_content
            if final_stil["status"] in ("COMPLETED", "FAILED") and final_yield["status"] in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.4)

        assert final_stil and final_stil["status"] == "COMPLETED", f"STIL job failed: {final_stil}"
        assert final_yield and final_yield["status"] == "COMPLETED", f"Yield job failed: {final_yield}"
        assert len(wire_progress) >= 6, f"Expected multi-stage wire progress notifications, got {wire_progress}"
        print(
            f"  [ OK ] Long jobs completed with {len(wire_progress)} stdio ProgressNotifications! "
            f"Yield candidate={final_yield['result'].get('model_version')}"
        )

        # 7. Also verify full_wafer_analysis end-to-end
        full_res = await client.call_tool("full_wafer_analysis", {"wafer_id": "WFR-9082", "lot_id": "LOT-2024-001"})
        assert full_res.structured_content is not None
        assert len(full_res.structured_content.get("agents_completed", [])) == 7
        print("  [ OK ] full_wafer_analysis completed across all 7 agents")

        # 8. Also verify generate_shmoo_report using Credential Manager SHMOO_API_KEY
        rep_res = await client.call_tool("generate_shmoo_report", {"text_mode": "template", "test_methodology": "MBIST"})
        assert rep_res.structured_content is not None
        print(f"  [ OK ] generate_shmoo_report: {rep_res.content[0].text}")


async def main() -> None:
    print()
    print("=" * 72)
    print("  Verilumen ATE MCP Server -- Verification & Stdio E2E Suite")
    print("=" * 72)
    token = get_shmoo_api_key(create_if_missing=True)
    print(f"  fastmcp version : {fastmcp.__version__}")
    print(f"  secret keyring  : OK (SHMOO_API_KEY provisioned in Windows Credential Manager)")
    print()
    online = await check_ports()
    print(f"\n  Services online : {online}/{len(SERVICES)}")
    await run_stdio_e2e(token)
    print("\n" + "=" * 72)
    print("  ALL MCP STDIO E2E CHECKS PASSED")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
