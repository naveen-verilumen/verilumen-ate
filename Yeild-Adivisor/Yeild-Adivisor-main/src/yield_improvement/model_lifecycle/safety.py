"""Production invariants. Lifecycle state never authorizes production."""

from __future__ import annotations

from typing import Any

from yield_improvement.model_lifecycle.states import LifecycleError

PRODUCTION_ACTION = "FORBIDDEN"
PRODUCTION_AUTHORIZED = False
SAFETY_ELIGIBLE_PRODUCTION_COUNT = 0
SAFETY_ELIGIBLE_PRODUCTION_RATE = 0.0


def safety_payload() -> dict[str, Any]:
    return {
        "production_action": PRODUCTION_ACTION,
        "production_authorized": PRODUCTION_AUTHORIZED,
        "safety_eligible_production_count": SAFETY_ELIGIBLE_PRODUCTION_COUNT,
        "safety_eligible_production_rate": SAFETY_ELIGIBLE_PRODUCTION_RATE,
        "invoked_agents": [],
        "automatic_retraining": False,
        "automatic_activation": False,
    }


def assert_production_invariants(payload: dict[str, Any] | None = None) -> None:
    checks = payload or safety_payload()
    if checks.get("production_action") != PRODUCTION_ACTION:
        raise LifecycleError("FAIL CLOSED: production_action must be FORBIDDEN")
    if checks.get("production_authorized") is not False:
        raise LifecycleError("FAIL CLOSED: production_authorized must be false")
    if checks.get("safety_eligible_production_count", 0) != 0:
        raise LifecycleError("FAIL CLOSED: safety_eligible_production_count must be 0")
    rate = checks.get("safety_eligible_production_rate", 0.0)
    if rate not in {0, 0.0}:
        raise LifecycleError("FAIL CLOSED: safety_eligible_production_rate must be 0.0")
    if checks.get("invoked_agents"):
        raise LifecycleError("FAIL CLOSED: invoked_agents must be empty")
