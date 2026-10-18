"""
Unit tests for critical compensation failures and MANUAL_RECOVERY_REQUIRED transitions.
"""

from pathlib import Path
from saga.coordinator import SagaCoordinator
from saga.models import SagaStatus, StepStatus
from saga.steps import ApproveStep, DepositStep, SwapStep


def test_compensation_failure_triggers_manual_recovery():
    # Step 1: OK, Step 2: OK, Step 3: Fails forward
    # During compensation, Step 2 fails to unwind
    step1 = ApproveStep()
    step2 = SwapStep(force_fail_compensation=True)
    step3 = DepositStep(force_fail=True)

    coordinator = SagaCoordinator(
        saga_id="test_comp_failure",
        title="Compensation Failure Test",
        steps=[step1, step2, step3],
        sleep_func=lambda d: None,
    )

    log = coordinator.execute()

    # Must transition to MANUAL_RECOVERY_REQUIRED
    assert log.status == SagaStatus.MANUAL_RECOVERY_REQUIRED
    assert log.steps[2].status == StepStatus.FAILED
    assert log.steps[1].status == StepStatus.COMPENSATION_FAILED
    # Step 1 must NOT have been compensated, to prevent corrupting further state
    assert log.steps[0].status == StepStatus.CONFIRMED

    # Emergency snapshot must have been generated
    assert log.recovery_snapshot_path is not None
    snapshot_path = Path(log.recovery_snapshot_path)
    assert snapshot_path.exists()

    # Clean up snapshot file
    try:
        snapshot_path.unlink()
    except Exception:
        pass
