"""
Unit tests for step execution, dependency checks, and receipt verification barriers.
"""

from saga.client import PharosClient
from saga.coordinator import SagaCoordinator
from saga.models import RetryConfig, SagaStatus, StepStatus
from saga.steps import ApproveStep, DepositStep, SwapStep


def test_single_approve_step_forward_execution():
    client = PharosClient(simulate_only=True)
    step = ApproveStep()
    receipt = step.execute_forward(client, current_block=31569442)

    assert receipt.status == 1
    assert receipt.tx_hash.startswith("0xsim_")
    assert receipt.gas_used == 45000
    assert receipt.is_simulated is True


def test_full_pipeline_happy_path_success():
    steps = [ApproveStep(), SwapStep(), DepositStep()]
    slept = []
    coordinator = SagaCoordinator(
        saga_id="test_happy_path",
        title="Happy Path",
        steps=steps,
        sleep_func=lambda d: slept.append(d),
    )

    log = coordinator.execute()

    assert log.status == SagaStatus.COMPLETED
    assert log.steps_succeeded == 3
    assert log.steps_compensated == 0
    assert log.total_gas_used == 45000 + 115000 + 85000  # 245,000

    for s in log.steps:
        assert s.status == StepStatus.CONFIRMED
        assert s.receipt is not None
        assert s.receipt.status == 1


def test_dependency_enforcement_missing_prior_step():
    # Only supply Step 2 (Swap) which requires Step 1 (Approve)
    steps = [SwapStep()]
    coordinator = SagaCoordinator(
        saga_id="test_dep_failure",
        title="Dependency Check",
        steps=steps,
        sleep_func=lambda d: None,
    )

    log = coordinator.execute()
    # Step 2 must fail immediately due to unconfirmed prerequisite
    assert log.status == SagaStatus.ROLLED_BACK
    assert log.steps[0].status == StepStatus.FAILED
    assert "Prerequisite dependency 'step_1_approve' was not confirmed" in (log.steps[0].error or "")


def test_transient_retry_and_recovery():
    # Step 1 has 2 transient failures, then succeeds on attempt 3
    slept = []
    step1 = ApproveStep(transient_fail_count=2)
    step2 = SwapStep()
    step3 = DepositStep()

    coordinator = SagaCoordinator(
        saga_id="test_transient_recovery",
        title="Transient Recovery",
        steps=[step1, step2, step3],
        retry_config=RetryConfig(max_retries=3, base_delay_seconds=0.1, jitter=False),
        sleep_func=lambda d: slept.append(d),
    )

    log = coordinator.execute()

    assert log.status == SagaStatus.COMPLETED
    assert log.steps[0].status == StepStatus.CONFIRMED
    assert log.steps[0].attempts == 3
    assert len(slept) == 2  # Slept twice during retries
