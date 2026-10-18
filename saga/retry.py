"""
Retry coordination with exponential backoff, jitter, and error classification.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

from saga.models import RetryConfig


class TransientError(Exception):
    """Exception class indicating a temporary, retryable condition."""
    def __init__(self, message: str, code: str = "TRANSIENT_ERROR"):
        super().__init__(message)
        self.code = code


class PermanentError(Exception):
    """Exception class indicating an unrecoverable condition requiring compensation or abort."""
    def __init__(self, message: str, code: str = "PERMANENT_ERROR"):
        super().__init__(message)
        self.code = code


class RetryCoordinator:
    """Coordinates retries with exponential backoff, full jitter, and deterministic clock hooks."""

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        sleep_func: Optional[Callable[[float], None]] = None,
        random_func: Optional[Callable[[], float]] = None,
    ):
        self.config = config or RetryConfig()
        self.sleep_func = sleep_func or time.sleep
        self.random_func = random_func or random.random
        self.sleep_history: list[float] = []

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given 0-indexed attempt number.
        Formula: min(max_delay, base_delay * (backoff_factor ** attempt)) + jitter
        """
        if attempt < 0:
            return 0.0

        exponential = self.config.base_delay_seconds * (
            self.config.backoff_factor ** attempt
        )
        capped = min(self.config.max_delay_seconds, exponential)

        if self.config.jitter:
            # Full jitter formula: random value between 0 and capped
            jitter_amount = self.random_func() * capped * 0.5
            delay = capped + jitter_amount
        else:
            delay = capped

        return delay

    def wait(self, attempt: int) -> float:
        """Calculate delay and invoke the sleep function, recording wait duration."""
        delay = self.calculate_delay(attempt)
        self.sleep_history.append(delay)
        self.sleep_func(delay)
        return delay

    def is_retryable(self, error: Exception | str) -> bool:
        """
        Classifies an error as transient (retryable) or permanent.
        Checks known error codes, exception types, and error message substrings.
        """
        if isinstance(error, TransientError):
            return True
        if isinstance(error, PermanentError):
            return False

        error_str = str(error).upper()

        # Permanent failure indicators
        permanent_indicators = [
            "INSUFFICIENT",
            "REVERT",
            "INVALID_OPCODE",
            "UNAUTHORIZED",
            "FORBIDDEN",
            "PARSE_ERROR",
            "CONFIG_INVALID",
            "CHAIN_ID_MISMATCH",
            "COMPENSATION_FAILED",
            "PERMANENT",
        ]
        for indicator in permanent_indicators:
            if indicator in error_str:
                return False

        # Transient failure indicators
        transient_indicators = [
            "TIMEOUT",
            "TIMED OUT",
            "429",
            "503",
            "502",
            "504",
            "RATE_LIMIT",
            "CONNECTION_RESET",
            "CONNECTION REFUSED",
            "NONCE_TOO_LOW",
            "NONCE TOO LOW",
            "REPLACEMENT TRANSACTION UNDERPRICED",
            "GAS_SPIKE",
            "NETWORK_ERROR",
            "TEMPORARY",
        ]
        for indicator in transient_indicators:
            if indicator in error_str:
                return True

        return False
