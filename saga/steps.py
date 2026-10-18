"""
Saga step implementations with forward actions, reverse compensation handlers, and deterministic failure injection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from saga.client import PharosClient
from saga.models import StepAction, StepRecord, StepStatus, TransactionReceipt
from saga.retry import PermanentError, TransientError


class BaseSagaStep(ABC):
    """Abstract base class for all forward and compensating saga steps."""

    def __init__(
        self,
        step_id: str,
        order: int,
        name: str,
        action: StepAction,
        contract: str,
        params: Dict[str, Any],
        requires: Optional[List[str]] = None,
        force_fail: bool = False,
        force_fail_compensation: bool = False,
        transient_fail_count: int = 0,
    ):
        self.step_id = step_id
        self.order = order
        self.name = name
        self.action = action
        self.contract = contract
        self.params = params
        self.requires = requires or []
        self.force_fail = force_fail
        self.force_fail_compensation = force_fail_compensation
        self.transient_fail_count = transient_fail_count
        self._transient_attempt_counter = 0

    def to_record(self) -> StepRecord:
        return StepRecord(
            step_id=self.step_id,
            order=self.order,
            name=self.name,
            action=self.action.value,
            contract=self.contract,
            status=StepStatus.PENDING,
        )

    @abstractmethod
    def execute_forward(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        """Executes the forward step action and returns confirmed transaction receipt."""
        pass

    @abstractmethod
    def execute_compensation(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        """Executes the reverse compensating action to unwind this step."""
        pass


class ApproveStep(BaseSagaStep):
    """Step 1: Approve ERC20 token allowance for downstream protocol."""

    def __init__(
        self,
        step_id: str = "step_1_approve",
        order: int = 1,
        token_contract: str = "0xcfC8330f4BCAB529c625D12781b1C19466A9Fc8B",
        spender: str = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        amount: int = 1_000_000_000,  # 1,000 USDC
        force_fail: bool = False,
        force_fail_compensation: bool = False,
        transient_fail_count: int = 0,
    ):
        super().__init__(
            step_id=step_id,
            order=order,
            name="Approve Token Allowance",
            action=StepAction.ERC20_APPROVE,
            contract=token_contract,
            params={"spender": spender, "amount": amount},
            requires=[],
            force_fail=force_fail,
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_fail_count,
        )

    def execute_forward(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        if self._transient_attempt_counter < self.transient_fail_count:
            self._transient_attempt_counter += 1
            raise TransientError(
                f"RPC node 503 Service Unavailable (transient attempt {self._transient_attempt_counter}/{self.transient_fail_count})"
            )

        if self.force_fail:
            receipt = client.generate_simulated_receipt(
                self.action.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="INSUFFICIENT_ALLOWANCE_OR_REVERT",
            )
            raise PermanentError(f"Step 1 '{self.name}' permanently reverted on-chain.")

        receipt = client.generate_simulated_receipt(
            self.action.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt

    def execute_compensation(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        """Compensating action: Revoke approval by setting allowance to 0."""
        if self.force_fail_compensation:
            client.generate_simulated_receipt(
                StepAction.ERC20_REVOKE_APPROVAL.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="COMPENSATION_REVOKE_FAILED",
            )
            raise PermanentError(f"Critical: Failed to revoke approval for {self.contract}.")

        receipt = client.generate_simulated_receipt(
            StepAction.ERC20_REVOKE_APPROVAL.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt


class SwapStep(BaseSagaStep):
    """Step 2: Execute token swap through DEX router."""

    def __init__(
        self,
        step_id: str = "step_2_swap",
        order: int = 2,
        router_contract: str = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        token_in: str = "0xcfC8330f4BCAB529c625D12781b1C19466A9Fc8B",
        token_out: str = "0x838800b758277CC111B2d48Ab01e5E164f8E9471",
        amount_in: int = 1_000_000_000,
        min_amount_out: int = 500_000_000_000_000_000,
        requires: Optional[List[str]] = None,
        force_fail: bool = False,
        force_fail_compensation: bool = False,
        transient_fail_count: int = 0,
    ):
        super().__init__(
            step_id=step_id,
            order=order,
            name="Execute Token Swap",
            action=StepAction.SWAP_EXACT_TOKENS,
            contract=router_contract,
            params={
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": amount_in,
                "min_amount_out": min_amount_out,
            },
            requires=requires or ["step_1_approve"],
            force_fail=force_fail,
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_fail_count,
        )

    def execute_forward(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        if self._transient_attempt_counter < self.transient_fail_count:
            self._transient_attempt_counter += 1
            raise TransientError(
                f"Slippage boundary transient gas spike (attempt {self._transient_attempt_counter}/{self.transient_fail_count})"
            )

        if self.force_fail:
            client.generate_simulated_receipt(
                self.action.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="EXCESSIVE_SLIPPAGE_REVERT",
            )
            raise PermanentError(f"Step 2 '{self.name}' permanently reverted on-chain.")

        receipt = client.generate_simulated_receipt(
            self.action.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt

    def execute_compensation(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        """Compensating action: Unwind swap by trading token_out back to token_in."""
        if self.force_fail_compensation:
            client.generate_simulated_receipt(
                StepAction.UNWIND_SWAP.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="UNWIND_SWAP_REVERTED_INSUFFICIENT_LIQUIDITY",
            )
            raise PermanentError(f"Critical: Failed to unwind swap on {self.contract}.")

        receipt = client.generate_simulated_receipt(
            StepAction.UNWIND_SWAP.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt


class DepositStep(BaseSagaStep):
    """Step 3: Deposit swapped token into vault."""

    def __init__(
        self,
        step_id: str = "step_3_deposit",
        order: int = 3,
        vault_contract: str = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        token: str = "0x838800b758277CC111B2d48Ab01e5E164f8E9471",
        amount: int = 500_000_000_000_000_000,
        requires: Optional[List[str]] = None,
        force_fail: bool = False,
        force_fail_compensation: bool = False,
        transient_fail_count: int = 0,
    ):
        super().__init__(
            step_id=step_id,
            order=order,
            name="Deposit into Vault",
            action=StepAction.VAULT_DEPOSIT,
            contract=vault_contract,
            params={"token": token, "amount": amount},
            requires=requires or ["step_2_swap"],
            force_fail=force_fail,
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_fail_count,
        )

    def execute_forward(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        if self._transient_attempt_counter < self.transient_fail_count:
            self._transient_attempt_counter += 1
            raise TransientError(
                f"RPC node timeout polling pool state (attempt {self._transient_attempt_counter}/{self.transient_fail_count})"
            )

        if self.force_fail:
            client.generate_simulated_receipt(
                self.action.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="VAULT_CAP_EXCEEDED_OR_PAUSED",
            )
            raise PermanentError(f"Step 3 '{self.name}' permanently reverted: VAULT_CAP_EXCEEDED.")

        receipt = client.generate_simulated_receipt(
            self.action.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt

    def execute_compensation(self, client: PharosClient, current_block: int) -> TransactionReceipt:
        """Compensating action: Withdraw deposited asset back to wallet."""
        if self.force_fail_compensation:
            client.generate_simulated_receipt(
                StepAction.VAULT_WITHDRAW.value,
                self.contract,
                current_block,
                revert=True,
                simulated_error="VAULT_WITHDRAWAL_LOCK_REVERT",
            )
            raise PermanentError(f"Critical: Failed to withdraw from vault {self.contract}.")

        receipt = client.generate_simulated_receipt(
            StepAction.VAULT_WITHDRAW.value,
            self.contract,
            current_block,
            revert=False,
        )
        return receipt
