"""Lifecycle states and allowed transitions. Activation is never implied."""

from __future__ import annotations

from typing import Literal

from yield_improvement.utils.errors import YieldImprovementError

ModelState = Literal["CANDIDATE", "VALIDATED", "APPROVED", "ACTIVE", "RETIRED", "REJECTED"]

STATES: tuple[ModelState, ...] = (
    "CANDIDATE",
    "VALIDATED",
    "APPROVED",
    "ACTIVE",
    "RETIRED",
    "REJECTED",
)

# TRAIN ≠ VALIDATE ≠ APPROVE ≠ ACTIVATE. No automatic ACTIVE transition.
ALLOWED_TRANSITIONS: frozenset[tuple[ModelState, ModelState]] = frozenset(
    {
        ("CANDIDATE", "VALIDATED"),
        ("CANDIDATE", "REJECTED"),
        ("VALIDATED", "APPROVED"),
        ("VALIDATED", "REJECTED"),
        ("APPROVED", "ACTIVE"),
        ("APPROVED", "REJECTED"),
        ("ACTIVE", "RETIRED"),
        ("RETIRED", "ACTIVE"),  # rollback only
    }
)

EVENT_TYPES = (
    "MODEL_CREATED",
    "MODEL_VALIDATED",
    "MODEL_REJECTED",
    "MODEL_APPROVED",
    "MODEL_ACTIVATED",
    "MODEL_RETIRED",
    "MODEL_ROLLED_BACK",
    "MODEL_EVALUATED",
    "MODEL_COMPARED",
)


class LifecycleError(YieldImprovementError):
    """Fail-closed lifecycle / registry error."""


def assert_transition(previous: ModelState | None, new: ModelState, *, event: str) -> None:
    if previous is None:
        if new != "CANDIDATE" and not (new == "ACTIVE" and event == "MODEL_ACTIVATED"):
            # Bootstrap of the existing champion is the only ACTIVE-from-none path.
            if not (new == "ACTIVE" and event == "MODEL_CREATED"):
                raise LifecycleError(f"invalid initial state {new} for {event}")
        return
    if (previous, new) not in ALLOWED_TRANSITIONS:
        raise LifecycleError(f"invalid transition {previous} -> {new} for {event}")
    if new == "ACTIVE" and event not in {"MODEL_ACTIVATED", "MODEL_ROLLED_BACK", "MODEL_CREATED"}:
        raise LifecycleError("ACTIVE may only be set by explicit activation, rollback, or champion bootstrap")
    if event == "MODEL_APPROVED" and new == "ACTIVE":
        raise LifecycleError("approval must not activate")
    if event == "MODEL_VALIDATED" and new == "ACTIVE":
        raise LifecycleError("validation must not activate")
    if event == "MODEL_EVALUATED" and new == "ACTIVE":
        raise LifecycleError("evaluation must not activate")
