"""
Unit tests for SagaStateMachine, transition rules, and audit logging.
"""

import json
from pathlib import Path
import pytest
from saga.models import SagaStatus, StepRecord, StepStatus
from saga.state import InvalidStateTransitionError, SagaStateMachine


def test_initial_state():
    sm = SagaStateMachine(saga_id="test_init", title="Test Saga")
    assert sm.current_status == SagaStatus.INITIALIZED
    assert len(sm.log.state_history) == 1
    assert sm.log.state_history[0].to_state == "INITIALIZED"


def test_valid_saga_transitions():
    sm = SagaStateMachine(saga_id="test_flow", title="Test Flow")
    sm.transition_saga(SagaStatus.EXECUTING, reason="Started")
    assert sm.current_status == SagaStatus.EXECUTING

    sm.transition_saga(SagaStatus.COMPLETED, reason="Done")
    assert sm.current_status == SagaStatus.COMPLETED
    assert sm.log.completed_at is not None


def test_invalid_saga_transition_raises():
    sm = SagaStateMachine(saga_id="test_invalid", title="Test Invalid")
    # INITIALIZED cannot go directly to COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_saga(SagaStatus.COMPLETED)


def test_valid_step_transitions():
    sm = SagaStateMachine(saga_id="test_step", title="Test Step Flow")
    step = StepRecord(
        step_id="step_1",
        order=1,
        name="Step 1",
        action="ERC20_APPROVE",
        status=StepStatus.PENDING,
    )

    sm.transition_step(step, StepStatus.EXECUTING, reason="Running")
    assert step.status == StepStatus.EXECUTING

    sm.transition_step(step, StepStatus.CONFIRMED, reason="Confirmed on-chain")
    assert step.status == StepStatus.CONFIRMED

    sm.transition_step(step, StepStatus.COMPENSATING, reason="Rollback requested")
    assert step.status == StepStatus.COMPENSATING

    sm.transition_step(step, StepStatus.COMPENSATED, reason="Rollback finished")
    assert step.status == StepStatus.COMPENSATED


def test_invalid_step_transition_raises():
    sm = SagaStateMachine(saga_id="test_invalid_step", title="Test Step Invalid")
    step = StepRecord(
        step_id="step_1",
        order=1,
        name="Step 1",
        action="ERC20_APPROVE",
        status=StepStatus.PENDING,
    )
    # PENDING cannot go directly to CONFIRMED
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_step(step, StepStatus.CONFIRMED)


def test_log_serialization_to_dict_and_json():
    sm = SagaStateMachine(saga_id="test_serialize", title="Test Serialization")
    sm.transition_saga(SagaStatus.EXECUTING, reason="Executing")
    d = sm.log.to_dict()
    assert d["saga_id"] == "test_serialize"
    assert d["status"] == "EXECUTING"
    assert len(d["state_history"]) >= 2

    json_str = sm.log.to_json()
    parsed = json.loads(json_str)
    assert parsed["saga_id"] == "test_serialize"


def test_export_recovery_snapshot(tmp_path: Path):
    sm = SagaStateMachine(saga_id="test_recovery", title="Test Recovery")
    sm.transition_saga(SagaStatus.EXECUTING)
    sm.transition_saga(SagaStatus.COMPENSATING)
    sm.transition_saga(SagaStatus.MANUAL_RECOVERY_REQUIRED)

    snapshot_path = sm.export_recovery_snapshot(output_dir=tmp_path)
    assert snapshot_path.exists()
    assert "CRITICAL EMERGENCY RECOVERY SNAPSHOT" in snapshot_path.read_text(encoding="utf-8")
    assert sm.log.recovery_snapshot_path == str(snapshot_path)
