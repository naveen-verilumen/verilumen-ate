"""FastAPI read-only adapter for the Node.js dashboard. GET only."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from yield_improvement.api.service import assemble_dashboard, list_datasets, load_health_snapshot, load_ml_snapshot
from yield_improvement.api.wafer_map import build_wafer_map
from yield_improvement.config.test_catalog import public_test_catalog


def create_app() -> FastAPI:
    app = FastAPI(
        title="Yield Improvement Agent API",
        description="Read-only presentation of existing analysis. Production action is FORBIDDEN.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
            "http://localhost:5176",
            "http://127.0.0.1:5176",
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def allow_dashboard_iframe(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000"
        )
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        return response
    app.state.dashboard_cache = {}
    app.state.wafer_map_cache = {}
    app.state.parametric_cache = {}
    app.state.failing_dies_cache = {}

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "production_action": "FORBIDDEN",
            "production_authorized": False,
            "invoked_agents": [],
        }

    @app.get("/api/datasets")
    def api_datasets() -> dict[str, Any]:
        return {"datasets": list_datasets()}

    @app.get("/api/ml/active")
    def api_ml_active() -> dict[str, Any]:
        return load_ml_snapshot()

    @app.get("/api/test-catalog")
    def api_test_catalog() -> dict[str, Any]:
        return public_test_catalog()

    @app.get("/api/datasets/{dataset_id}/health")
    def api_dataset_health(dataset_id: str) -> dict[str, Any]:
        return load_health_snapshot(dataset_id)

    @app.get("/api/datasets/{dataset_id}/wafer-map")
    def api_wafer_map(dataset_id: str) -> dict[str, Any]:
        cache: dict[str, Any] = app.state.wafer_map_cache
        if dataset_id in cache:
            return cache[dataset_id]
        try:
            payload = build_wafer_map(dataset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        cache[dataset_id] = payload
        return payload

    @app.get("/api/datasets/{dataset_id}/dashboard")
    def api_dashboard(dataset_id: str, refresh: bool = False, lot_id: str | None = None) -> dict[str, Any]:
        cache: dict[str, Any] = app.state.dashboard_cache
        cache_key = f"{dataset_id}::{lot_id or '*'}"
        if not refresh and cache_key in cache:
            payload = cache[cache_key]
            payload["test_catalog"] = public_test_catalog()
            return payload
        try:
            payload = assemble_dashboard(dataset_id, lot_id=lot_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Analysis results are not available yet. {exc}") from exc
        cache[cache_key] = payload
        return payload

    @app.get("/api/datasets/{dataset_id}/recommendations")
    def api_recommendations(dataset_id: str, lot_id: str | None = None) -> dict[str, Any]:
        from yield_improvement.api.service import get_recommendations_bundle

        try:
            return get_recommendations_bundle(dataset_id, lot_id=lot_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {exc}") from exc

    @app.get("/api/datasets/{dataset_id}/parametric-analysis")
    def api_parametric_analysis(dataset_id: str, refresh: bool = False, lot_id: str | None = None) -> dict[str, Any]:
        from yield_improvement.api.service import get_parametric_analysis

        cache: dict[str, Any] = app.state.parametric_cache
        cache_key = f"{dataset_id}::{lot_id or '*'}"
        if not refresh and cache_key in cache:
            return cache[cache_key]

        try:
            payload = get_parametric_analysis(dataset_id, lot_id=lot_id)
            cache[cache_key] = payload
            return payload
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to generate parametric analysis: {exc}") from exc

    @app.get("/api/datasets/{dataset_id}/recommendations/{recommendation_id}")
    def api_recommendation_detail(dataset_id: str, recommendation_id: str) -> dict[str, Any]:
        from yield_improvement.api.service import get_recommendations_bundle

        try:
            bundle = get_recommendations_bundle(dataset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        for rec in bundle.get("recommendations", []):
            if rec.get("recommendation_id") == recommendation_id:
                return rec
        raise HTTPException(status_code=404, detail=f"Recommendation '{recommendation_id}' not found in dataset '{dataset_id}'")

    @app.get("/api/datasets/{dataset_id}/recommendations/{recommendation_id}/failing-dies")
    def api_recommendation_failing_dies(
        dataset_id: str,
        recommendation_id: str,
        lot_id: str | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        from yield_improvement.recommendations.failing_dies import extract_recommendation_failing_dies

        cache: dict[str, Any] = app.state.failing_dies_cache
        cache_key = f"{dataset_id}::{recommendation_id}::{lot_id or '*'}"
        if not refresh and cache_key in cache:
            return cache[cache_key]

        try:
            payload = extract_recommendation_failing_dies(
                dataset_id,
                recommendation_id,
                lot_id=lot_id,
            )
            cache[cache_key] = payload
            return payload
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to extract failing dies: {exc}") from exc

    @app.post("/api/datasets/{dataset_id}/recommendations/{recommendation_id}/feedback")
    def api_post_feedback(dataset_id: str, recommendation_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        from yield_improvement.recommendations.contracts import FeedbackCreateRequest
        from yield_improvement.recommendations.storage import (
            FeedbackStorageError,
            FeedbackStore,
            InvalidStateTransitionError,
            UnsafeIdentifierError,
        )

        try:
            req = FeedbackCreateRequest.model_validate(request_body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid feedback payload: {exc}") from exc

        store = FeedbackStore()
        try:
            record = store.record_feedback(dataset_id, recommendation_id, req)
            # Evict dashboard cache so updated status is reflected immediately
            app.state.dashboard_cache.clear()
            return record.model_dump(mode="json")
        except (InvalidStateTransitionError, UnsafeIdentifierError, FeedbackStorageError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc

    @app.get("/api/datasets/{dataset_id}/recommendations/{recommendation_id}/feedback")
    def api_get_feedback_history(dataset_id: str, recommendation_id: str) -> dict[str, Any]:
        from yield_improvement.recommendations.storage import FeedbackStore, UnsafeIdentifierError

        store = FeedbackStore()
        try:
            history = store.get_history(dataset_id, recommendation_id)
            status = store.get_current_status(dataset_id, recommendation_id)
            return {
                "recommendation_id": recommendation_id,
                "dataset_id": dataset_id,
                "current_status": status,
                "history": [r.model_dump(mode="json") for r in history],
            }
        except UnsafeIdentifierError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()

