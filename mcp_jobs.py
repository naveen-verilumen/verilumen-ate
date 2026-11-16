"""
Verilumen ATE Intelligence — Asynchronous Long-Job Runner
=========================================================
Executes heavy Yield ML retraining and IEEE 1450 STIL parsing in non-blocking
background tasks, returning a `run_id` immediately and streaming MCP progress
notifications + resource update notifications upon stage transitions.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import gc
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

from mcp_schemas import JobStatusEnvelope

logger = logging.getLogger("verilumen.mcp.jobs")

MAX_TRACKED_JOBS = 64
ROOT_DIR = Path(__file__).resolve().parent
YIELD_ROOT = ROOT_DIR / "Yeild-Adivisor" / "Yeild-Adivisor-main"
YIELD_SRC = YIELD_ROOT / "src"
STIL_DIR = ROOT_DIR / "still" / "still"
STIL_DASHBOARD_DIR = STIL_DIR / "dashboard"
DEMO_STIL_DIR = ROOT_DIR / "demo_datasets" / "test_time" / "pre test"


def _utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _safe_child_name(target: str) -> str:
    cleaned = target.strip()
    if not cleaned:
        return ""
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned or ":" in cleaned:
        raise ValueError(f"Unsafe target identifier rejected: {target!r}")
    return cleaned


def _resolve_yield_dataset(target: str) -> Path:
    name = _safe_child_name(target) or "yi_synthetic_v2"
    candidates = [
        YIELD_ROOT / "data" / "synthetic" / "agent_visible" / name,
        YIELD_ROOT / "tests" / "fixtures" / "synthetic_v1" / "agent_visible" / name,
        YIELD_ROOT / "tests" / "fixtures" / "synthetic_v1" / "monitoring" / "agent_visible" / name,
        YIELD_ROOT / "tests" / "fixtures" / "fpy" / name,
    ]
    for cand in candidates:
        if (cand / "die_attempts.csv").is_file():
            return cand
    raise FileNotFoundError(f"Yield dataset {name!r} not found or missing die_attempts.csv.")


def _resolve_stil_file(target: str) -> Path:
    name = _safe_child_name(target) or "Production_SCAN_stuck_at_1000pat.stil"
    for base in (STIL_DIR, DEMO_STIL_DIR):
        cand = (base / name).resolve()
        if str(cand).startswith(str(base.resolve())) and cand.is_file():
            return cand
    raise FileNotFoundError(f"STIL file {name!r} not found in configured STIL directories.")


class JobManager:
    """Manages non-blocking background ATE compute jobs with MCP progress notifications."""

    def __init__(
        self,
        on_resource_updated: Callable[[str], Awaitable[None]],
        on_agent_result_ready: Callable[[str, Dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._jobs: "OrderedDict[str, JobStatusEnvelope]" = OrderedDict()
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._heavy_sem = asyncio.Semaphore(1)
        self._on_resource_updated = on_resource_updated
        self._on_agent_result_ready = on_agent_result_ready

    def get(self, run_id: str) -> Optional[JobStatusEnvelope]:
        return self._jobs.get(run_id)

    def _store(self, env: JobStatusEnvelope) -> None:
        self._jobs[env.run_id] = env
        self._jobs.move_to_end(env.run_id)
        while len(self._jobs) > MAX_TRACKED_JOBS:
            old_id, _ = self._jobs.popitem(last=False)
            self._tasks.pop(old_id, None)

    async def cancel_all(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def start_job(
        self,
        job_type: Literal["yield_retrain", "stil_parse"],
        target: str = "",
        *,
        ctx: Any = None,
        stil_url: str = "http://127.0.0.1:8765",
        http_client: Any = None,
    ) -> JobStatusEnvelope:
        # Validate target eagerly before queuing
        if job_type == "yield_retrain":
            resolved_path = _resolve_yield_dataset(target)
        else:
            resolved_path = _resolve_stil_file(target)

        run_id = f"{job_type}-{uuid.uuid4().hex[:8]}"
        now = _utc_iso()
        resource_uri = f"ate://jobs/{run_id}"
        env = JobStatusEnvelope(
            run_id=run_id,
            job_type=job_type,
            target=resolved_path.name,
            status="RUNNING",
            progress=5.0,
            total=100.0,
            phase="queued",
            started_at=now,
            updated_at=now,
            resource_uri=resource_uri,
            logs=[f"[{now}] Queued {job_type} for {resolved_path.name}"],
            summary=(
                f"Started non-blocking {job_type} job (run_id={run_id}) for '{resolved_path.name}'. "
                f"Track live progress via notifications or call get_job_status(run_id='{run_id}')."
            ),
        )
        self._store(env)

        session = None
        progress_token: str | int | None = None
        if ctx is not None:
            try:
                session = ctx.session
                rc = ctx.request_context
                meta = rc._srctx.meta if rc is not None and rc._srctx is not None else None
                if meta:
                    progress_token = meta.get("progress_token")
                await ctx.report_progress(5.0, 100.0, f"Queued {job_type}: {resolved_path.name}")
            except Exception as exc:
                logger.debug("Initial progress notification skipped: %s", exc)

        async def _notify(progress: float, phase: str, message: str) -> None:
            job = self._jobs.get(run_id)
            if job:
                logs = list(job.logs)
                logs.append(f"[{_utc_iso()}] ({progress:.0f}%) {phase}: {message}")
                self._jobs[run_id] = job.model_copy(
                    update={
                        "progress": progress,
                        "phase": phase,
                        "updated_at": _utc_iso(),
                        "logs": logs[-20:],
                    }
                )
            if session is not None and progress_token is not None:
                try:
                    await session.send_progress_notification(
                        progress_token=progress_token,
                        progress=progress,
                        total=100.0,
                        message=f"{phase}: {message}",
                    )
                except Exception as exc:
                    logger.debug("Progress notification error for %s: %s", run_id, exc)
            try:
                await self._on_resource_updated(resource_uri)
            except Exception:
                pass

        task = asyncio.create_task(
            self._run_job(
                run_id=run_id,
                job_type=job_type,
                target_path=resolved_path,
                notify=_notify,
                stil_url=stil_url,
                http_client=http_client,
            )
        )
        self._tasks[run_id] = task
        return env

    async def _run_job(
        self,
        *,
        run_id: str,
        job_type: Literal["yield_retrain", "stil_parse"],
        target_path: Path,
        notify: Callable[[float, str, str], Awaitable[None]],
        stil_url: str,
        http_client: Any,
    ) -> None:
        try:
            async with self._heavy_sem:
                if job_type == "yield_retrain":
                    result_payload, summary = await self._exec_yield_retrain(target_path, notify)
                    target_agent = "yield_advisor"
                else:
                    result_payload, summary = await self._exec_stil_parse(target_path, notify, stil_url, http_client)
                    target_agent = "stil"

            done_at = _utc_iso()
            job = self._jobs[run_id]
            logs = list(job.logs) + [f"[{done_at}] COMPLETED: {summary}"]
            self._jobs[run_id] = job.model_copy(
                update={
                    "status": "COMPLETED",
                    "progress": 100.0,
                    "phase": "completed",
                    "updated_at": done_at,
                    "completed_at": done_at,
                    "result": result_payload,
                    "logs": logs[-20:],
                    "summary": summary,
                }
            )
            await self._on_agent_result_ready(target_agent, result_payload)
            await self._on_resource_updated(job.resource_uri)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Background job %s failed", run_id)
            err_at = _utc_iso()
            job = self._jobs.get(run_id)
            if job:
                self._jobs[run_id] = job.model_copy(
                    update={
                        "status": "FAILED",
                        "phase": "failed",
                        "updated_at": err_at,
                        "completed_at": err_at,
                        "error": str(exc),
                        "summary": f"Job {run_id} failed: {exc}",
                    }
                )
                await self._on_resource_updated(job.resource_uri)

    async def _exec_yield_retrain(
        self,
        dataset_dir: Path,
        notify: Callable[[float, str, str], Awaitable[None]],
    ) -> tuple[Dict[str, Any], str]:
        if str(YIELD_SRC) not in sys.path:
            sys.path.insert(0, str(YIELD_SRC))

        await notify(15.0, "prepare", f"Validating schema & preparing candidate for {dataset_dir.name}")

        def _prepare(lp_root: Path):
            gc.collect()
            from yield_improvement.model_lifecycle.registry import LifecyclePaths
            from yield_improvement.model_lifecycle.training import prepare_candidate

            lp = LifecyclePaths(root=lp_root)
            champion_src = YIELD_ROOT / "artifacts" / "ml" / "yi_ml_v1"
            shutil.copytree(champion_src, lp.root / "yi_ml_v1", dirs_exist_ok=True)
            with contextlib.redirect_stdout(sys.stderr):
                return prepare_candidate(dataset_dir, paths=lp)

        with tempfile.TemporaryDirectory(prefix="vl_yield_retrain_") as tmp_dir:
            lp_root = Path(tmp_dir) / "ml"
            prep = await asyncio.to_thread(_prepare, lp_root)
            cand_version = prep["model_version"]

            await notify(45.0, "train", f"Training logistic candidate {cand_version} with nested LOLO CV")

            def _train():
                from yield_improvement.model_lifecycle.registry import LifecyclePaths
                from yield_improvement.model_lifecycle.training import train_candidate

                with contextlib.redirect_stdout(sys.stderr):
                    return train_candidate(cand_version, paths=LifecyclePaths(root=lp_root))

            trained = await asyncio.to_thread(_train)
            await notify(80.0, "evaluate", f"Evaluating LOLO generalization & calibration for {cand_version}")

            def _evaluate():
                from yield_improvement.model_lifecycle.registry import LifecyclePaths
                from yield_improvement.model_lifecycle.evaluate import evaluate_version

                with contextlib.redirect_stdout(sys.stderr):
                    return evaluate_version(cand_version, dataset_dir=dataset_dir, paths=LifecyclePaths(root=lp_root))

            ev = await asyncio.to_thread(_evaluate)

        cal = ev.get("calibrated_metrics") or {}
        raw = ev.get("raw_metrics") or {}
        roc_auc = cal.get("roc_auc") or raw.get("roc_auc")
        brier = cal.get("brier") or raw.get("brier")
        summary = (
            f"Yield ML candidate '{cand_version}' retrained on '{dataset_dir.name}' "
            f"({trained.get('n_samples', 0)} samples across {trained.get('n_lots', 0)} lots). "
            f"ROC-AUC={roc_auc:.4f}, Brier={brier:.4f}. Champion yi_ml_v1 untouched (production_authorized=False)."
            if isinstance(roc_auc, (int, float)) and isinstance(brier, (int, float))
            else f"Yield ML candidate '{cand_version}' retrained on '{dataset_dir.name}' (champion untouched)."
        )
        payload = {
            "dataset_id": dataset_dir.name,
            "model_version": cand_version,
            "architecture": trained.get("architecture", "logistic"),
            "n_samples": trained.get("n_samples"),
            "n_lots": trained.get("n_lots"),
            "calibrated_metrics": cal,
            "raw_metrics": raw,
            "operational": ev.get("operational", {}),
            "activated": False,
            "production_authorized": False,
            "summary": summary,
        }
        await notify(100.0, "completed", summary)
        return payload, summary

    async def _exec_stil_parse(
        self,
        stil_path: Path,
        notify: Callable[[float, str, str], Awaitable[None]],
        stil_url: str,
        http_client: Any,
    ) -> tuple[Dict[str, Any], str]:
        if str(STIL_DASHBOARD_DIR) not in sys.path:
            sys.path.insert(0, str(STIL_DASHBOARD_DIR))

        size_mb = stil_path.stat().st_size / (1024 * 1024)
        await notify(20.0, "scan_headers", f"Streaming IEEE 1450 header & SignalGroups ({size_mb:.2f} MB)")

        def _stream_scan_counts() -> dict[str, Any]:
            # Stream chunks incrementally without reading entire multi-MB file into regex copies twice
            pat_re = re.compile(rb"^Pattern\s+\w+", re.M)
            vec_re = re.compile(rb"\bV\s*\{")
            sig_count_bytes = 0
            pat_count = 0
            vec_count = 0
            chunk_size = 1024 * 1024
            with stil_path.open("rb") as fh:
                while chunk := fh.read(chunk_size):
                    sig_count_bytes += len(chunk)
                    pat_count += len(pat_re.findall(chunk))
                    vec_count += len(vec_re.findall(chunk))
            return {
                "bytes_scanned": sig_count_bytes,
                "pattern_blocks": pat_count,
                "vector_statements": vec_count,
            }

        scan_stats = await asyncio.to_thread(_stream_scan_counts)
        await notify(55.0, "extract_setup", f"Extracting setup cycles & waveforms ({scan_stats['vector_statements']} vectors)")

        parsed_payload: Dict[str, Any] = {}
        # Try live STIL microservice first if healthy, else invoke local parser in worker thread
        used_live = False
        if http_client is not None and stil_path.parent == STIL_DIR:
            try:
                r = await http_client.get(f"{stil_url}/api/analyze", params={"name": stil_path.name}, timeout=12.0)
                if r.status_code == 200:
                    parsed_payload = r.json()
                    used_live = True
            except Exception:
                used_live = False

        if not used_live:
            def _local_analyze() -> dict[str, Any]:
                from stil_setup import analyze_stil

                with contextlib.redirect_stdout(sys.stderr):
                    return analyze_stil(stil_path)

            parsed_payload = await asyncio.to_thread(_local_analyze)

        await notify(85.0, "summarize", f"Finalizing setup cycle table for {stil_path.name}")

        setup_cycles = parsed_payload.get("setup_cycles") or parsed_payload.get("setup_expanded") or 0
        summary = (
            f"Parsed STIL file '{stil_path.name}' ({size_mb:.2f} MB): "
            f"{scan_stats['vector_statements']} vector blocks, "
            f"{len(parsed_payload.get('blocks', []))} top STIL blocks, "
            f"setup_cycles={setup_cycles}, reset_pins={parsed_payload.get('reset_pins', [])}."
        )
        parsed_payload["scan_stats"] = scan_stats
        parsed_payload["summary"] = summary
        await notify(100.0, "completed", summary)
        return parsed_payload, summary
