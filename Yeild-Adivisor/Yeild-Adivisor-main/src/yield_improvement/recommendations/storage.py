"""Isolated feedback storage and state machine for engineering investigations.

Stores feedback records in artifacts/feedback/{dataset_id}_feedback.json.
Never mutates canonical datasets, analytical models, or production configurations.
Enforces valid state machine transitions and atomic writes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import threading
from typing import Any
import uuid

from yield_improvement.recommendations.contracts import (
    FeedbackCreateRequest,
    FeedbackRecord,
    FeedbackStatus,
)
from yield_improvement.utils.paths import repo_root

logger = logging.getLogger(__name__)

# Valid state machine transitions
ALLOWED_TRANSITIONS: dict[FeedbackStatus, set[FeedbackStatus]] = {
    "PROPOSED": {"ACCEPTED_FOR_INVESTIGATION", "REJECTED"},
    "ACCEPTED_FOR_INVESTIGATION": {"IN_PROGRESS", "REJECTED", "PROPOSED"},
    "IN_PROGRESS": {"CONFIRMED", "REJECTED", "INCONCLUSIVE", "VALIDATION_PENDING"},
    "VALIDATION_PENDING": {"CONFIRMED", "REJECTED", "INCONCLUSIVE", "IN_PROGRESS"},
    "CONFIRMED": {"CLOSED", "VALIDATION_PENDING"},
    "REJECTED": {"CLOSED", "IN_PROGRESS"},
    "INCONCLUSIVE": {"CLOSED", "IN_PROGRESS"},
    "CLOSED": {"IN_PROGRESS", "ACCEPTED_FOR_INVESTIGATION"},
}

DATASET_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")
RECOMMENDATION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:]+$")

_WRITE_LOCK = threading.Lock()


class FeedbackStorageError(Exception):
    """Base error for feedback storage operations."""


class InvalidStateTransitionError(FeedbackStorageError):
    """Raised when a requested status transition is not allowed by policy."""


class UnsafeIdentifierError(FeedbackStorageError):
    """Raised when an identifier contains invalid or path-traversal characters."""


class FeedbackStore:
    """Manages isolated persistence of investigation feedback records."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or (repo_root() / "artifacts" / "feedback")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _validate_id(self, identifier: str, pattern: re.Pattern, label: str) -> str:
        clean = identifier.strip()
        if not clean or not pattern.match(clean) or ".." in clean or "/" in clean or "\\" in clean:
            raise UnsafeIdentifierError(f"Invalid or unsafe {label}: '{identifier}'")
        return clean

    def _feedback_path(self, dataset_id: str) -> Path:
        clean_ds = self._validate_id(dataset_id, DATASET_ID_REGEX, "dataset_id")
        return self.root_dir / f"{clean_ds}_feedback.json"

    def _load_data(self, dataset_id: str) -> dict[str, list[dict[str, Any]]]:
        path = self._feedback_path(dataset_id)
        if not path.is_file():
            return {}
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            return {}
        except Exception as exc:
            logger.warning("Failed to parse feedback file %s: %s", path, exc)
            return {}

    def _save_data(self, dataset_id: str, data: dict[str, list[dict[str, Any]]]) -> None:
        path = self._feedback_path(dataset_id)
        tmp_path = path.with_suffix(".tmp")
        payload = json.dumps(data, indent=2, sort_keys=True)
        # Atomic write
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(path)

    def get_history(self, dataset_id: str, recommendation_id: str) -> list[FeedbackRecord]:
        clean_ds = self._validate_id(dataset_id, DATASET_ID_REGEX, "dataset_id")
        clean_rec = self._validate_id(recommendation_id, RECOMMENDATION_ID_REGEX, "recommendation_id")

        with _WRITE_LOCK:
            data = self._load_data(clean_ds)
            records_raw = data.get(clean_rec, [])
            records: list[FeedbackRecord] = []
            for item in records_raw:
                try:
                    records.append(FeedbackRecord.model_validate(item))
                except Exception as exc:
                    logger.warning("Failed to validate feedback record: %s", exc)
            return records

    def get_current_status(self, dataset_id: str, recommendation_id: str) -> FeedbackStatus:
        history = self.get_history(dataset_id, recommendation_id)
        if not history:
            return "PROPOSED"
        return history[-1].new_status

    def record_feedback(
        self,
        dataset_id: str,
        recommendation_id: str,
        request: FeedbackCreateRequest,
    ) -> FeedbackRecord:
        clean_ds = self._validate_id(dataset_id, DATASET_ID_REGEX, "dataset_id")
        clean_rec = self._validate_id(recommendation_id, RECOMMENDATION_ID_REGEX, "recommendation_id")

        with _WRITE_LOCK:
            data = self._load_data(clean_ds)
            history_raw = data.get(clean_rec, [])

            if history_raw:
                previous_status: FeedbackStatus = history_raw[-1].get("new_status", "PROPOSED")
            else:
                previous_status = "PROPOSED"

            new_status = request.new_status
            if new_status != previous_status:
                allowed = ALLOWED_TRANSITIONS.get(previous_status, set())
                if new_status not in allowed:
                    raise InvalidStateTransitionError(
                        f"Cannot transition recommendation status from {previous_status} to {new_status}. "
                        f"Allowed transitions: {sorted(list(allowed))}"
                    )

            # Special verification rule: If claiming CONFIRMED or VALIDATION_PENDING, check notes/evidence
            if new_status == "CONFIRMED" and not request.investigation_conclusion:
                raise FeedbackStorageError("investigation_conclusion is required when confirming a hypothesis.")

            ts = datetime.now(timezone.utc).isoformat()
            fb_id = f"FB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

            record = FeedbackRecord(
                feedback_id=fb_id,
                recommendation_id=clean_rec,
                dataset_id=clean_ds,
                previous_status=previous_status,
                new_status=new_status,
                engineer=request.engineer.strip(),
                investigation_notes=request.investigation_notes.strip(),
                evidence_collected=list(request.evidence_collected),
                timestamp=ts,
                investigation_conclusion=request.investigation_conclusion,
                hypothesis_confirmed=request.hypothesis_confirmed,
                independent_validation_evidence=request.independent_validation_evidence,
                validation_dataset=request.validation_dataset,
                pre_investigation_metrics=request.pre_investigation_metrics,
                post_investigation_metrics=request.post_investigation_metrics,
                adverse_effects=request.adverse_effects,
                separately_authorized_corrective_action_ref=request.separately_authorized_corrective_action_ref,
                production_action="FORBIDDEN",
                production_authorized=False,
                safety_eligible_production_rate=0.0,
            )

            history_raw.append(record.model_dump(mode="json"))
            data[clean_rec] = history_raw
            self._save_data(clean_ds, data)

            return record
