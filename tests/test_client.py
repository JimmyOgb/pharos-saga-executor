"""
Unit tests for PharosClient, Atlantic testnet RPC rules, and simulation receipts.
"""

import pytest
from saga.client import EXPECTED_CHAIN_ID, SIMULATED_GAS_TABLE, PharosClient
from saga.models import StepAction
from saga.retry import PermanentError


def test_chain_id_constant():
    assert EXPECTED_CHAIN_ID == 688689


def test_simulated_receipt_structure():
    client = PharosClient(simulate_only=True)
    receipt = client.generate_simulated_receipt(
        action=StepAction.ERC20_APPROVE.value,
        contract="0xcfC8330f4BCAB529c625D12781b1C19466A9Fc8B",
        block_number=31569442,
    )

    assert receipt.tx_hash.startswith("0xsim_")
    assert receipt.status == 1
    assert receipt.block_number == 31569442
    assert receipt.gas_used == 45000
    assert receipt.is_simulated is True
    assert "Simulated sandbox execution" in (receipt.simulated_note or "")


def test_poll_receipt_success():
    client = PharosClient(simulate_only=True)
    receipt = client.generate_simulated_receipt(
        action=StepAction.SWAP_EXACT_TOKENS.value,
        contract="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        block_number=31569443,
    )

    verified = client.poll_receipt(receipt.tx_hash)
    assert verified.tx_hash == receipt.tx_hash
    assert verified.status == 1
    assert verified.gas_used == 115000


def test_poll_receipt_revert_raises_permanent_error():
    client = PharosClient(simulate_only=True)
    receipt = client.generate_simulated_receipt(
        action=StepAction.VAULT_DEPOSIT.value,
        contract="0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        block_number=31569444,
        revert=True,
    )

    with pytest.raises(PermanentError) as exc_info:
        client.poll_receipt(receipt.tx_hash)
    assert "execution reverted" in str(exc_info.value)


def test_poll_receipt_unknown_hash_raises():
    client = PharosClient(simulate_only=True)
    with pytest.raises(PermanentError) as exc_info:
        client.poll_receipt("0xsim_nonexistent_hash")
    assert "not found" in str(exc_info.value)


def test_gas_table_has_all_actions():
    for action in StepAction:
        assert action.value in SIMULATED_GAS_TABLE
        assert SIMULATED_GAS_TABLE[action.value] > 0
