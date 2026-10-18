"""
Unit tests for retry coordination, backoff mathematics, and error classification.
"""

from saga.models import RetryConfig
from saga.retry import PermanentError, RetryCoordinator, TransientError


def test_calculate_delay_exponential_growth():
    config = RetryConfig(
        base_delay_seconds=0.5,
        backoff_factor=2.0,
        max_delay_seconds=10.0,
        jitter=False,
    )
    coordinator = RetryCoordinator(config=config)

    assert coordinator.calculate_delay(0) == 0.5
    assert coordinator.calculate_delay(1) == 1.0
    assert coordinator.calculate_delay(2) == 2.0
    assert coordinator.calculate_delay(3) == 4.0


def test_calculate_delay_max_cap():
    config = RetryConfig(
        base_delay_seconds=2.0,
        backoff_factor=3.0,
        max_delay_seconds=5.0,
        jitter=False,
    )
    coordinator = RetryCoordinator(config=config)

    # 2.0 * (3 ** 2) = 18.0 -> capped at 5.0
    assert coordinator.calculate_delay(2) == 5.0


def test_calculate_delay_with_jitter():
    config = RetryConfig(
        base_delay_seconds=1.0,
        backoff_factor=2.0,
        max_delay_seconds=10.0,
        jitter=True,
    )
    # Inject deterministic random function returning 0.5
    coordinator = RetryCoordinator(config=config, random_func=lambda: 0.5)

    # Base delay = 1.0; jitter = 0.5 * 1.0 * 0.5 = 0.25 -> total 1.25
    delay = coordinator.calculate_delay(0)
    assert delay == 1.25


def test_injectable_sleep_records_history():
    slept = []
    coordinator = RetryCoordinator(
        config=RetryConfig(base_delay_seconds=0.1, jitter=False),
        sleep_func=lambda d: slept.append(d),
    )

    coordinator.wait(0)
    coordinator.wait(1)
    assert len(slept) == 2
    assert slept == [0.1, 0.2]


def test_error_classification_transient():
    coordinator = RetryCoordinator()

    assert coordinator.is_retryable(TransientError("Network drop"))
    assert coordinator.is_retryable("HTTP 429 Rate Limit Exceeded")
    assert coordinator.is_retryable("503 Service Unavailable")
    assert coordinator.is_retryable("Connection timeout polling receipt")
    assert coordinator.is_retryable("nonce too low in tx pool")
    assert coordinator.is_retryable("temporary network error")


def test_error_classification_permanent():
    coordinator = RetryCoordinator()

    assert not coordinator.is_retryable(PermanentError("Execution reverted"))
    assert not coordinator.is_retryable("execution reverted: INSUFFICIENT_BALANCE")
    assert not coordinator.is_retryable("invalid opcode encountered")
    assert not coordinator.is_retryable("unauthorized sender")
    assert not coordinator.is_retryable("chain_id_mismatch")
