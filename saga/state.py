"""
State machine coordinator with strict transition validation, audit logging, and recovery snapshots.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from saga.models import (
    SagaExecutionLog,
    SagaStatus,
    StateTransitionEvent,
    StepRecord,
    StepStatus,
)

# Matrix of legal saga-level transitions
LEGAL_SAGA_TRANSITIONS: Dict[SagaStatus, List[SagaStatus]] = {
    SagaStatus.INITIALIZED: [SagaStatus.EXECUTING, SagaStatus.ABORTED],
    SagaStatus.EXECUTING: [SagaStatus.COMPLETED, SagaStatus.COMPENSATING],
    SagaStatus.COMPENSATING: [SagaStatus.ROLLED_BACK, SagaStatus.MANUAL_RECOVERY_REQUIRED],
    SagaStatus.COMPLETED: [],
    SagaStatus.ROLLED_BACK: [],
    SagaStatus.MANUAL_RECOVERY_REQUIRED: [],
    SagaStatus.ABORTED: [],
}

# Matrix of legal step-level transitions
LEGAL_STEP_TRANSITIONS: Dict[StepStatus, List[StepStatus]] = {
    StepStatus.PENDING: [StepStatus.EXECUTING, StepStatus.SKIPPED, StepStatus.FAILED],
    StepStatus.EXECUTING: [StepStatus.CONFIRMED, StepStatus.RETRIED, StepStatus.FAILED],
    StepStatus.RETRIED: [StepStatus.EXECUTING, StepStatus.FAILED],
    StepStatus.CONFIRMED: [StepStatus.COMPENSATING],
    StepStatus.FAILED: [],
    StepStatus.COMPENSATING: [StepStatus.COMPENSATED, StepStatus.COMPENSATION_FAILED],
    StepStatus.COMPENSATED: [],
    StepStatus.COMPENSATION_FAILED: [],
    StepStatus.SKIPPED: [],
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""
    pass


class SagaStateMachine:
    """Enforces valid state transitions and logs an immutable audit trail."""

    def __init__(self, saga_id: str, title: str, network: str = "atlantic", chain_id: int = 688689):
        self.log = SagaExecutionLog(
            saga_id=saga_id,
            title=title,
            network=network,
            chain_id=chain_id,
            status=SagaStatus.INITIALIZED,
        )
        self._record_transition(
            from_state="NONE",
            to_state=SagaStatus.INITIALIZED.value,
            reason="Pipeline initialized",
        )

    @property
    def current_status(self) -> SagaStatus:
        return self.log.status

    def _record_transition(
        self,
        from_state: str,
        to_state: str,
        step_id: Optional[str] = None,
        attempt: int = 1,
        reason: Optional[str] = None,
        tx_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = StateTransitionEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_state=from_state,
            to_state=to_state,
            step_id=step_id,
            attempt=attempt,
            reason=reason,
            tx_hash=tx_hash,
            metadata=metadata or {},
        )
        self.log.state_history.append(event)

    def transition_saga(self, new_status: SagaStatus, reason: Optional[str] = None) -> None:
        """Transition overall saga status if the transition is legal."""
        current = self.log.status
        allowed = LEGAL_SAGA_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal saga transition from {current.value} to {new_status.value}. Allowed: {[s.value for s in allowed]}"
            )

        self._record_transition(
            from_state=current.value,
            to_state=new_status.value,
            reason=reason,
        )
        self.log.status = new_status
        if new_status in (SagaStatus.COMPLETED, SagaStatus.ROLLED_BACK, SagaStatus.MANUAL_RECOVERY_REQUIRED, SagaStatus.ABORTED):
            self.log.completed_at = datetime.now(timezone.utc).isoformat()

    def transition_step(
        self,
        step: StepRecord,
        new_status: StepStatus,
        reason: Optional[str] = None,
        attempt: int = 1,
        tx_hash: Optional[str] = None,
    ) -> None:
        """Transition step status if the transition is legal."""
        current = step.status
        allowed = LEGAL_STEP_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal step transition for '{step.step_id}' from {current.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        self._record_transition(
            from_state=f"{step.step_id}:{current.value}",
            to_state=f"{step.step_id}:{new_status.value}",
            step_id=step.step_id,
            attempt=attempt,
            reason=reason,
            tx_hash=tx_hash,
        )
        step.status = new_status

    def export_recovery_snapshot(self, output_dir: Optional[Path | str] = None) -> Path:
        """
        Dumps the entire execution log and stranded asset states into a critical recovery file.
        Invoked when MANUAL_RECOVERY_REQUIRED is reached.
        """
        target_dir = Path(output_dir) if output_dir else Path.cwd()
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"saga-recovery-snapshot-{self.log.saga_id}-{timestamp_str}.json"
        filepath = target_dir / filename

        snapshot_data = {
            "title": "CRITICAL EMERGENCY RECOVERY SNAPSHOT — MANUAL INTERVENTION REQUIRED",
            "warning": "A compensating step in the saga failed. On-chain state may be partially altered. Review immediately.",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "execution_log": self.log.to_dict(),
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)

        self.log.recovery_snapshot_path = str(filepath)
        return filepath
