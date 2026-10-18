"""
Data models and state definitions for Pharos Saga Executor.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SagaStatus(str, Enum):
    """Lifecycle statuses for the overall Saga workflow."""
    INITIALIZED = "INITIALIZED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    ROLLED_BACK = "ROLLED_BACK"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"
    ABORTED = "ABORTED"


class StepStatus(str, Enum):
    """Lifecycle statuses for individual saga steps."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    CONFIRMED = "CONFIRMED"
    RETRIED = "RETRIED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"
    SKIPPED = "SKIPPED"


class StepAction(str, Enum):
    """Canonical action types supported by the saga engine."""
    ERC20_APPROVE = "ERC20_APPROVE"
    SWAP_EXACT_TOKENS = "SWAP_EXACT_TOKENS"
    VAULT_DEPOSIT = "VAULT_DEPOSIT"
    ERC20_REVOKE_APPROVAL = "ERC20_REVOKE_APPROVAL"
    UNWIND_SWAP = "UNWIND_SWAP"
    VAULT_WITHDRAW = "VAULT_WITHDRAW"


@dataclass
class TransactionReceipt:
    """Receipt representation for verified or simulated on-chain transactions."""
    tx_hash: str
    status: int  # 1 for success, 0 for revert
    block_number: int
    gas_used: int
    cumulative_gas_used: int
    effective_gas_price_wei: int
    logs: List[Dict[str, Any]] = field(default_factory=list)
    is_simulated: bool = True
    simulated_note: Optional[str] = "Simulated receipt (zero gas spent, safe sandbox)"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StateTransitionEvent:
    """Record of a single state transition in the saga audit trail."""
    timestamp: str
    from_state: str
    to_state: str
    step_id: Optional[str] = None
    attempt: int = 1
    reason: Optional[str] = None
    tx_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StepRecord:
    """Audit record for a step's execution lifecycle."""
    step_id: str
    order: int
    name: str
    action: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    max_retries: int = 3
    contract: Optional[str] = None
    tx_hash: Optional[str] = None
    receipt: Optional[TransactionReceipt] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    is_compensation: bool = False
    compensated_by: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    compensation_receipt: Optional[TransactionReceipt] = None
    compensation_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        if self.receipt:
            d["receipt"] = self.receipt.to_dict()
        if self.compensation_receipt:
            d["compensation_receipt"] = self.compensation_receipt.to_dict()
        return d


@dataclass
class RetryConfig:
    """Retry policy configuration for transient errors."""
    max_retries: int = 3
    base_delay_seconds: float = 0.5
    backoff_factor: float = 2.0
    max_delay_seconds: float = 5.0
    jitter: bool = True
    retryable_error_codes: List[str] = field(
        default_factory=lambda: [
            "TIMEOUT",
            "NETWORK_ERROR",
            "RATE_LIMIT_429",
            "SERVER_ERROR_503",
            "NONCE_TOO_LOW",
            "GAS_SPIKE_TRANSIENT",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SagaExecutionLog:
    """Complete, machine-readable audit record of a saga run."""
    saga_id: str
    title: str
    network: str
    chain_id: int
    status: SagaStatus = SagaStatus.INITIALIZED
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    total_gas_used: int = 0
    total_steps: int = 0
    steps_succeeded: int = 0
    steps_compensated: int = 0
    steps: List[StepRecord] = field(default_factory=list)
    state_history: List[StateTransitionEvent] = field(default_factory=list)
    recovery_snapshot_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "saga_id": self.saga_id,
            "title": self.title,
            "network": self.network,
            "chain_id": self.chain_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_gas_used": self.total_gas_used,
            "total_steps": self.total_steps,
            "steps_succeeded": self.steps_succeeded,
            "steps_compensated": self.steps_compensated,
            "steps": [s.to_dict() for s in self.steps],
            "state_history": [e.to_dict() for e in self.state_history],
            "recovery_snapshot_path": self.recovery_snapshot_path,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
