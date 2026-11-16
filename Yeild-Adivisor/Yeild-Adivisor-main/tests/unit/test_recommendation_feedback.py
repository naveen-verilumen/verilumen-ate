from __future__ import annotations

import pytest

from yield_improvement.recommendations.contracts import FeedbackCreateRequest
from yield_improvement.recommendations.storage import (
    FeedbackStorageError,
    FeedbackStore,
    InvalidStateTransitionError,
    UnsafeIdentifierError,
)


def test_valid_feedback_transitions(tmp_path):
    store = FeedbackStore(root_dir=tmp_path)
    ds_id = "test_dataset"
    rec_id = "REC-PROCESS.LOT_VARIATION"

    # Initial state is PROPOSED
    assert store.get_current_status(ds_id, rec_id) == "PROPOSED"

    # 1. Transition: PROPOSED -> ACCEPTED_FOR_INVESTIGATION
    req1 = FeedbackCreateRequest(
        new_status="ACCEPTED_FOR_INVESTIGATION",
        engineer="Lead Test Eng",
        investigation_notes="Accepted for lot tool tracking review.",
    )
    r1 = store.record_feedback(ds_id, rec_id, req1)
    assert r1.previous_status == "PROPOSED"
    assert r1.new_status == "ACCEPTED_FOR_INVESTIGATION"
    assert store.get_current_status(ds_id, rec_id) == "ACCEPTED_FOR_INVESTIGATION"

    # 2. Transition: ACCEPTED_FOR_INVESTIGATION -> IN_PROGRESS
    req2 = FeedbackCreateRequest(
        new_status="IN_PROGRESS",
        engineer="Process Eng",
        investigation_notes="Comparing chamber run logs.",
        evidence_collected=["MES tool history log"],
    )
    r2 = store.record_feedback(ds_id, rec_id, req2)
    assert r2.previous_status == "ACCEPTED_FOR_INVESTIGATION"
    assert r2.new_status == "IN_PROGRESS"

    # 3. Transition: IN_PROGRESS -> CONFIRMED
    req3 = FeedbackCreateRequest(
        new_status="CONFIRMED",
        engineer="Process Eng",
        investigation_notes="Chamber B thermal controller thermocouple failure identified.",
        investigation_conclusion="Thermocouple calibration drifted by 8 deg C.",
        hypothesis_confirmed=True,
    )
    r3 = store.record_feedback(ds_id, rec_id, req3)
    assert r3.previous_status == "IN_PROGRESS"
    assert r3.new_status == "CONFIRMED"
    assert r3.hypothesis_confirmed is True

    # 4. Transition: CONFIRMED -> CLOSED
    req4 = FeedbackCreateRequest(
        new_status="CLOSED",
        engineer="QA Manager",
        investigation_notes="Investigation closed. Tool PM scheduled under engineering governance.",
    )
    r4 = store.record_feedback(ds_id, rec_id, req4)
    assert r4.previous_status == "CONFIRMED"
    assert r4.new_status == "CLOSED"

    # Verify history audit length
    history = store.get_history(ds_id, rec_id)
    assert len(history) == 4
    assert [h.new_status for h in history] == [
        "ACCEPTED_FOR_INVESTIGATION",
        "IN_PROGRESS",
        "CONFIRMED",
        "CLOSED",
    ]


def test_invalid_state_transition_rejected(tmp_path):
    store = FeedbackStore(root_dir=tmp_path)
    ds_id = "test_dataset"
    rec_id = "REC-PROCESS.LOT_VARIATION"

    # Attempting to jump directly from PROPOSED to CONFIRMED must fail
    req_invalid = FeedbackCreateRequest(
        new_status="CONFIRMED",
        engineer="Eng",
        investigation_notes="Jumping straight to confirmed without investigation.",
        investigation_conclusion="Hypothesis confirmed without testing.",
    )
    with pytest.raises(InvalidStateTransitionError):
        store.record_feedback(ds_id, rec_id, req_invalid)


def test_confirmed_requires_investigation_conclusion(tmp_path):
    store = FeedbackStore(root_dir=tmp_path)
    ds_id = "test_dataset"
    rec_id = "REC-PROCESS.LOT_VARIATION"

    # Move to IN_PROGRESS first
    store.record_feedback(
        ds_id,
        rec_id,
        FeedbackCreateRequest(
            new_status="ACCEPTED_FOR_INVESTIGATION",
            engineer="Eng",
            investigation_notes="Accepted",
        ),
    )
    store.record_feedback(
        ds_id,
        rec_id,
        FeedbackCreateRequest(
            new_status="IN_PROGRESS",
            engineer="Eng",
            investigation_notes="In progress",
        ),
    )

    # Attempting CONFIRMED without investigation_conclusion must fail
    req_no_conclusion = FeedbackCreateRequest(
        new_status="CONFIRMED",
        engineer="Eng",
        investigation_notes="Confirmed without conclusion notes",
        investigation_conclusion=None,
    )
    with pytest.raises(FeedbackStorageError):
        store.record_feedback(ds_id, rec_id, req_no_conclusion)


def test_unsafe_identifiers_rejected(tmp_path):
    store = FeedbackStore(root_dir=tmp_path)
    req = FeedbackCreateRequest(
        new_status="ACCEPTED_FOR_INVESTIGATION",
        engineer="Eng",
        investigation_notes="Testing path traversal",
    )

    # Traversal in dataset_id
    with pytest.raises(UnsafeIdentifierError):
        store.record_feedback("../evil", "REC-1", req)

    # Traversal in recommendation_id
    with pytest.raises(UnsafeIdentifierError):
        store.record_feedback("valid_ds", "../evil_rec", req)


def test_feedback_cannot_mutate_safety_invariants(tmp_path):
    store = FeedbackStore(root_dir=tmp_path)
    ds_id = "test_dataset"
    rec_id = "REC-PROCESS.LOT_VARIATION"

    req = FeedbackCreateRequest(
        new_status="ACCEPTED_FOR_INVESTIGATION",
        engineer="Eng",
        investigation_notes="Accepted",
    )
    record = store.record_feedback(ds_id, rec_id, req)
    assert record.production_action == "FORBIDDEN"
    assert record.production_authorized is False
    assert record.safety_eligible_production_rate == 0.0
