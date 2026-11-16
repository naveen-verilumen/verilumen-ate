"""Controlled model lifecycle. Manual only. Never auto-trains or auto-activates."""

from yield_improvement.model_lifecycle.commands import (
    activate_candidate,
    approve_candidate,
    compare_candidate,
    evaluate_version,
    inspect_model,
    list_models,
    prepare_candidate,
    reject_candidate,
    rollback_to,
    train_candidate,
    validate_candidate,
    verify_registry,
)
from yield_improvement.model_lifecycle.states import LifecycleError

__all__ = [
    "LifecycleError",
    "prepare_candidate",
    "train_candidate",
    "evaluate_version",
    "compare_candidate",
    "validate_candidate",
    "approve_candidate",
    "activate_candidate",
    "reject_candidate",
    "rollback_to",
    "list_models",
    "inspect_model",
    "verify_registry",
]
