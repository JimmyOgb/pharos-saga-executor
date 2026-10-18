"""
Unit tests for reverse-order LIFO compensation rollback.
"""

from saga.coordinator import SagaCoordinator
from saga.models import SagaStatus, StepStatus
from saga.steps import ApproveStep, DepositStep, SwapStep


def test_forced_step_3_failure_reverse_lifo_rollback():
    # Step 1: OK, Step 2: OK, Step 3: Fails permanently
    step1 = ApproveStep()
    step2 = SwapStep()
    step3 = DepositStep(force_fail=True)

    event_order = []
    coordinator = SagaCoordinator(
        saga_id="test_step3_rollback",
        title="Forced Step 3 Failure",
        steps=[step1, step2, step3],
        sleep_func=lambda d: None,
        on_event=lambda ev: event_order.append(f"{ev.step_id}:{ev.to_state}"),
    )

    log = coordinator.execute()

    assert log.status == SagaStatus.ROLLED_BACK
    assert log.steps[0].status == StepStatus.COMPENSATED
    assert log.steps[1].status == StepStatus.COMPENSATED
    assert log.steps[2].status == StepStatus.FAILED
    assert log.steps_compensated == 2

    # Verify LIFO order: step_2_swap must be compensating BEFORE step_1_approve
    step2_comp_idx = event_order.index("step_2_swap:step_2_swap:COMPENSATING")
    step1_comp_idx = event_order.index("step_1_approve:step_1_approve:COMPENSATING")
    assert step2_comp_idx < step1_comp_idx, "Step 2 must be compensated before Step 1 in LIFO order"


def test_forced_step_2_failure_unwinds_only_step_1():
    step1 = ApproveStep()
    step2 = SwapStep(force_fail=True)
    step3 = DepositStep()

    coordinator = SagaCoordinator(
        saga_id="test_step2_rollback",
        title="Forced Step 2 Failure",
        steps=[step1, step2, step3],
        sleep_func=lambda d: None,
    )

    log = coordinator.execute()

    assert log.status == SagaStatus.ROLLED_BACK
    assert log.steps[0].status == StepStatus.COMPENSATED  # Step 1 unwound
    assert log.steps[1].status == StepStatus.FAILED       # Step 2 failed
    assert log.steps[2].status == StepStatus.PENDING      # Step 3 never touched
    assert log.steps_compensated == 1


def test_forced_step_1_failure_no_completed_steps():
    step1 = ApproveStep(force_fail=True)
    step2 = SwapStep()
    step3 = DepositStep()

    coordinator = SagaCoordinator(
        saga_id="test_step1_rollback",
        title="Forced Step 1 Failure",
        steps=[step1, step2, step3],
        sleep_func=lambda d: None,
    )

    log = coordinator.execute()

    assert log.status == SagaStatus.ROLLED_BACK
    assert log.steps[0].status == StepStatus.FAILED
    assert log.steps[1].status == StepStatus.PENDING
    assert log.steps[2].status == StepStatus.PENDING
    assert log.steps_compensated == 0
