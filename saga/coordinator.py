"""
Saga Coordinator managing sequential execution, receipt barriers, retries, and reverse LIFO compensation.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from saga.client import PharosClient
from saga.models import (
    RetryConfig,
    SagaExecutionLog,
    SagaStatus,
    StateTransitionEvent,
    StepRecord,
    StepStatus,
)
from saga.retry import PermanentError, RetryCoordinator, TransientError
from saga.state import SagaStateMachine
from saga.steps import BaseSagaStep

logger = logging.getLogger("saga.coordinator")


class SagaCoordinator:
    """Orchestrates forward multi-step transactions and reverse compensation rollbacks."""

    def __init__(
        self,
        saga_id: str,
        title: str,
        steps: List[BaseSagaStep],
        client: Optional[PharosClient] = None,
        retry_config: Optional[RetryConfig] = None,
        sleep_func: Optional[Callable[[float], None]] = None,
        random_func: Optional[Callable[[], float]] = None,
        on_event: Optional[Callable[[StateTransitionEvent], None]] = None,
    ):
        self.saga_id = saga_id
        self.title = title
        self.steps = steps
        self.client = client or PharosClient(simulate_only=True)
        self.retry_coordinator = RetryCoordinator(
            config=retry_config or RetryConfig(),
            sleep_func=sleep_func,
            random_func=random_func,
        )
        self.state_machine = SagaStateMachine(
            saga_id=saga_id,
            title=title,
            network="atlantic",
            chain_id=688689,
        )
        self.on_event = on_event

        # Populate step records in state machine
        self.step_records: dict[str, StepRecord] = {}
        for s in self.steps:
            rec = s.to_record()
            rec.max_retries = self.retry_coordinator.config.max_retries
            self.step_records[s.step_id] = rec
            self.state_machine.log.steps.append(rec)
        self.state_machine.log.total_steps = len(self.steps)

    def _notify_event(self, event: StateTransitionEvent) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.warning(f"Error in on_event callback: {e}")

    def _execute_single_step_with_retry(
        self,
        step: BaseSagaStep,
        record: StepRecord,
        current_block: int,
    ) -> bool:
        """Executes a single forward step honoring bounded retries and exponential backoff."""
        attempt = 0
        max_retries = self.retry_coordinator.config.max_retries

        while attempt <= max_retries:
            attempt += 1
            record.attempts = attempt

            try:
                # Transition to EXECUTING
                self.state_machine.transition_step(
                    record,
                    StepStatus.EXECUTING,
                    reason=f"Executing forward action attempt {attempt}/{max_retries + 1}",
                    attempt=attempt,
                )
                self._notify_event(self.state_machine.log.state_history[-1])

                # Execute forward action
                receipt = step.execute_forward(self.client, current_block)

                # Poll / verify receipt barrier
                verified_receipt = self.client.poll_receipt(receipt.tx_hash)

                # Step successfully confirmed
                record.receipt = verified_receipt
                record.tx_hash = verified_receipt.tx_hash
                self.state_machine.log.total_gas_used += verified_receipt.gas_used

                self.state_machine.transition_step(
                    record,
                    StepStatus.CONFIRMED,
                    reason=f"Receipt barrier verified on block #{verified_receipt.block_number} ({verified_receipt.gas_used} gas)",
                    attempt=attempt,
                    tx_hash=verified_receipt.tx_hash,
                )
                self._notify_event(self.state_machine.log.state_history[-1])
                return True

            except Exception as err:
                record.error = str(err)
                is_retryable = self.retry_coordinator.is_retryable(err)

                if is_retryable and attempt <= max_retries:
                    self.state_machine.transition_step(
                        record,
                        StepStatus.RETRIED,
                        reason=f"Transient failure on attempt {attempt}: {err}. Retrying...",
                        attempt=attempt,
                    )
                    self._notify_event(self.state_machine.log.state_history[-1])

                    # Exponential backoff with jitter
                    self.retry_coordinator.wait(attempt - 1)
                else:
                    # Permanent failure or retries exhausted
                    self.state_machine.transition_step(
                        record,
                        StepStatus.FAILED,
                        reason=f"Step failed permanently (attempt {attempt}/{max_retries + 1}): {err}",
                        attempt=attempt,
                    )
                    self._notify_event(self.state_machine.log.state_history[-1])
                    return False

        return False

    def _execute_compensation_rollback(
        self,
        completed_steps: List[BaseSagaStep],
        current_block: int,
    ) -> bool:
        """
        Rollback completed steps in strict reverse order (LIFO).
        If any compensation step fails, halts and triggers MANUAL_RECOVERY_REQUIRED.
        """
        self.state_machine.transition_saga(
            SagaStatus.COMPENSATING,
            reason=f"Initiating reverse LIFO compensation for {len(completed_steps)} completed steps.",
        )
        self._notify_event(self.state_machine.log.state_history[-1])

        # Reverse order compensation (LIFO)
        for step in reversed(completed_steps):
            record = self.step_records[step.step_id]

            self.state_machine.transition_step(
                record,
                StepStatus.COMPENSATING,
                reason=f"Unwinding {step.name} via compensating action.",
            )
            self._notify_event(self.state_machine.log.state_history[-1])

            try:
                comp_receipt = step.execute_compensation(self.client, current_block)
                verified_comp = self.client.poll_receipt(comp_receipt.tx_hash)

                record.compensation_receipt = verified_comp
                self.state_machine.log.total_gas_used += verified_comp.gas_used
                self.state_machine.log.steps_compensated += 1

                self.state_machine.transition_step(
                    record,
                    StepStatus.COMPENSATED,
                    reason=f"Compensating action confirmed on block #{verified_comp.block_number}.",
                    tx_hash=verified_comp.tx_hash,
                )
                self._notify_event(self.state_machine.log.state_history[-1])

            except Exception as comp_err:
                record.compensation_error = str(comp_err)
                self.state_machine.transition_step(
                    record,
                    StepStatus.COMPENSATION_FAILED,
                    reason=f"CRITICAL: Compensation failed for {step.name}: {comp_err}",
                )
                self._notify_event(self.state_machine.log.state_history[-1])

                # Trigger emergency state snapshot
                self.state_machine.transition_saga(
                    SagaStatus.MANUAL_RECOVERY_REQUIRED,
                    reason=f"Compensation step {step.step_id} failed. Halting to preserve stranded assets.",
                )
                self._notify_event(self.state_machine.log.state_history[-1])
                self.state_machine.export_recovery_snapshot()
                return False

        self.state_machine.transition_saga(
            SagaStatus.ROLLED_BACK,
            reason="All prior completed steps successfully compensated in reverse order.",
        )
        self._notify_event(self.state_machine.log.state_history[-1])
        return True

    def execute(self, current_block: Optional[int] = None) -> SagaExecutionLog:
        """
        Execute the full saga workflow.
        Returns the finalized SagaExecutionLog.
        """
        block = current_block or 31569442

        # Transition saga to EXECUTING
        self.state_machine.transition_saga(
            SagaStatus.EXECUTING,
            reason="Starting sequential forward step execution pipeline.",
        )
        self._notify_event(self.state_machine.log.state_history[-1])

        completed_steps: List[BaseSagaStep] = []

        for step in self.steps:
            record = self.step_records[step.step_id]

            # Verify prerequisite dependencies
            for dep_id in step.requires:
                dep_record = self.step_records.get(dep_id)
                if not dep_record or dep_record.status != StepStatus.CONFIRMED:
                    record.error = f"Prerequisite dependency '{dep_id}' was not confirmed."
                    self.state_machine.transition_step(
                        record,
                        StepStatus.FAILED,
                        reason=f"Prerequisite dependency '{dep_id}' was not confirmed.",
                    )
                    self._notify_event(self.state_machine.log.state_history[-1])
                    self._execute_compensation_rollback(completed_steps, block)
                    return self.state_machine.log

            # Execute forward step
            success = self._execute_single_step_with_retry(step, record, block)

            if success:
                completed_steps.append(step)
                self.state_machine.log.steps_succeeded += 1
            else:
                # Forward step failed; halt and initiate compensation rollback
                self._execute_compensation_rollback(completed_steps, block)
                return self.state_machine.log

        # All steps succeeded
        self.state_machine.transition_saga(
            SagaStatus.COMPLETED,
            reason=f"All {len(self.steps)} dependent steps verified and confirmed.",
        )
        self._notify_event(self.state_machine.log.state_history[-1])
        return self.state_machine.log
