"""
Comprehensive Unit, Integration, and Advanced Adversarial Tests for Isolated Saga Contracts.
Contracts tested:
- TestToken.sol
- TestAMM.sol (with unique sagaId isolation)
- TestSagaVault.sol

Covers:
1. Compilation artifacts verification.
2. Happy-path 3-step saga execution (approve -> swapWithSagaId -> deposit).
3. Forced-failure 3-step saga execution with exact multi-token approval direction and allowance reconciliation.
4. Adversarial: Two swaps in opposite directions (TKA -> TKB and TKB -> TKA) proving mutual isolation.
5. Adversarial: Partial unwinds (e.g. 40% then 60%) with replay prevention on remaining delta.
6. Adversarial: Overlapping swaps across distinct users.
7. Adversarial: Replay attempt after partial unwind (attempting to overdraw debt).
8. Adversarial: Unwind attempt using tokens acquired outside the recorded swap (faucet tokens).
9. Adversarial: Unauthorized third-party unwind attempt.
10. Adversarial: Insufficient pool liquidity on swap.
11. Adversarial: Unauthorized pool liquidity withdrawal attempt.
12. Adversarial: Vault failure non-persistence (subsequent deposits succeed).
13. Adversarial: Vault unauthorized withdrawal exceeding share balance.
14. Complete balance delta and multi-token allowance reconciliation.
"""

import json
from pathlib import Path
import pytest
from web3 import Web3, EthereumTesterProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_FILE = REPO_ROOT / "assets" / "contracts" / "compiled_contracts.json"


@pytest.fixture(scope="module")
def artifacts():
    assert ARTIFACTS_FILE.exists(), "compiled_contracts.json must exist. Run scripts/compile_contracts.py"
    with open(ARTIFACTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def eth_env(artifacts):
    w3 = Web3(EthereumTesterProvider())
    accounts = w3.eth.accounts
    deployer = accounts[0]
    user_a = accounts[1]
    user_b = accounts[2]

    token_a_def = artifacts["TestToken"]
    token_b_def = artifacts["TestToken"]
    amm_def = artifacts["TestAMM"]
    vault_def = artifacts["TestSagaVault"]

    # Deploy Token A (Initial supply: 1,000,000 * 10^18)
    TokenA = w3.eth.contract(abi=token_a_def["abi"], bytecode=token_a_def["bytecode"])
    tx_hash_a = TokenA.constructor("Test Token A", "TKA", 1_000_000 * 10**18).transact({"from": deployer})
    receipt_a = w3.eth.wait_for_transaction_receipt(tx_hash_a)
    token_a = w3.eth.contract(address=receipt_a.contractAddress, abi=token_a_def["abi"])

    # Deploy Token B (Initial supply: 1,000,000 * 10^18)
    TokenB = w3.eth.contract(abi=token_b_def["abi"], bytecode=token_b_def["bytecode"])
    tx_hash_b = TokenB.constructor("Test Token B", "TKB", 1_000_000 * 10**18).transact({"from": deployer})
    receipt_b = w3.eth.wait_for_transaction_receipt(tx_hash_b)
    token_b = w3.eth.contract(address=receipt_b.contractAddress, abi=token_b_def["abi"])

    # Deploy AMM with Token A and Token B
    AMM = w3.eth.contract(abi=amm_def["abi"], bytecode=amm_def["bytecode"])
    tx_hash_amm = AMM.constructor(token_a.address, token_b.address).transact({"from": deployer})
    receipt_amm = w3.eth.wait_for_transaction_receipt(tx_hash_amm)
    amm = w3.eth.contract(address=receipt_amm.contractAddress, abi=amm_def["abi"])

    # Fund AMM with pool liquidity (10,000 TKA and 10,000 TKB)
    token_a.functions.approve(amm.address, 10_000 * 10**18).transact({"from": deployer})
    token_b.functions.approve(amm.address, 10_000 * 10**18).transact({"from": deployer})
    amm.functions.supplyLiquidity(10_000 * 10**18, 10_000 * 10**18).transact({"from": deployer})

    # Deploy TestSagaVault for Token B asset
    Vault = w3.eth.contract(abi=vault_def["abi"], bytecode=vault_def["bytecode"])
    tx_hash_vault = Vault.constructor(token_b.address).transact({"from": deployer})
    receipt_vault = w3.eth.wait_for_transaction_receipt(tx_hash_vault)
    vault = w3.eth.contract(address=receipt_vault.contractAddress, abi=vault_def["abi"])

    # Give user_a 500 TKA via faucet
    token_a.functions.faucet(500 * 10**18).transact({"from": user_a})
    # Give user_b 500 TKB via faucet
    token_b.functions.faucet(500 * 10**18).transact({"from": user_b})

    return {
        "w3": w3,
        "deployer": deployer,
        "user_a": user_a,
        "user_b": user_b,
        "token_a": token_a,
        "token_b": token_b,
        "amm": amm,
        "vault": vault,
    }


def test_compiled_artifacts_validity(artifacts):
    for name in ["TestToken", "TestAMM", "TestSagaVault"]:
        assert name in artifacts, f"{name} must be in compiled artifacts"
        data = artifacts[name]
        assert data["bytecode"].startswith("0x") and len(data["bytecode"]) > 100
        assert isinstance(data["abi"], list) and len(data["abi"]) > 0


def test_three_step_saga_success_flow(eth_env):
    """Scenario 1: Happy Path with unique sagaId"""
    w3 = eth_env["w3"]
    user = eth_env["user_a"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]
    vault = eth_env["vault"]

    initial_tka = token_a.functions.balanceOf(user).call()
    assert initial_tka == 500 * 10**18
    swap_amount = 100 * 10**18
    saga_id = Web3.keccak(text="saga_run_success_001")

    # Step 1: Approve 100 TKA to AMM
    tx_app = token_a.functions.approve(amm.address, swap_amount).transact({"from": user})
    receipt_app = w3.eth.wait_for_transaction_receipt(tx_app)
    assert receipt_app.status == 1
    assert token_a.functions.allowance(user, amm.address).call() == swap_amount

    # Step 2: Swap 100 TKA -> 100 TKB with unique sagaId
    tx_swap = amm.functions.swapWithSagaId(saga_id, token_a.address, token_b.address, swap_amount, swap_amount).transact({"from": user})
    receipt_swap = w3.eth.wait_for_transaction_receipt(tx_swap)
    assert receipt_swap.status == 1
    assert token_a.functions.balanceOf(user).call() == 400 * 10**18
    assert token_b.functions.balanceOf(user).call() == swap_amount
    assert token_a.functions.allowance(user, amm.address).call() == 0

    # Step 3: Approve 100 TKB to Vault and Deposit
    token_b.functions.approve(vault.address, swap_amount).transact({"from": user})
    tx_dep = vault.functions.deposit(swap_amount).transact({"from": user})
    receipt_dep = w3.eth.wait_for_transaction_receipt(tx_dep)
    assert receipt_dep.status == 1
    assert token_b.functions.balanceOf(user).call() == 0
    assert vault.functions.userShares(user).call() == swap_amount
    assert token_b.functions.allowance(user, vault.address).call() == 0


def test_three_step_saga_forced_failure_and_compensation(eth_env):
    """
    Scenario 2: Forced Failure & Reverse LIFO Compensation with exact multi-token approval direction.
    Verifies:
    1. Forward approval: User approves AMM for TKA.
    2. Forward swap: AMM pulls TKA, gives TKB.
    3. Step 3: User approves Vault for TKB, calls depositWithFailFlag(forceFail=True) -> REVERTS.
    4. Compensation 1: User approves AMM for TKB, calls unwindSwapWithSagaId -> AMM pulls TKB, returns TKA.
    5. Compensation 2: Revoke residual allowances on Token A and Token B.
    """
    w3 = eth_env["w3"]
    user = eth_env["user_a"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]
    vault = eth_env["vault"]

    initial_tka = token_a.functions.balanceOf(user).call()
    swap_amount = 100 * 10**18
    buffered_allowance = 150 * 10**18  # Buffered to test residual revocation
    saga_id = Web3.keccak(text="saga_run_failure_002")

    # Step 1: Forward Approve TKA -> AMM
    token_a.functions.approve(amm.address, buffered_allowance).transact({"from": user})
    assert token_a.functions.allowance(user, amm.address).call() == buffered_allowance

    # Step 2: Forward Swap TKA -> TKB
    amm.functions.swapWithSagaId(saga_id, token_a.address, token_b.address, swap_amount, swap_amount).transact({"from": user})
    assert token_a.functions.allowance(user, amm.address).call() == 50 * 10**18  # 50 unspent residual
    assert token_b.functions.balanceOf(user).call() == swap_amount

    # Step 3: User approves Vault for TKB, then attempts deposit with forced failure
    token_b.functions.approve(vault.address, swap_amount).transact({"from": user})
    assert token_b.functions.allowance(user, vault.address).call() == swap_amount

    with pytest.raises(Exception) as exc_info:
        vault.functions.depositWithFailFlag(swap_amount, True).transact({"from": user})
    assert "DELIBERATE_FORCED_FAILURE" in str(exc_info.value) or "revert" in str(exc_info.value).lower()

    # Pre-compensation State Verification:
    # - User holds 100 TKB (unspent)
    # - Vault shares = 0 (unmutated)
    # - Allowance on Vault = 100 TKB (unconsumed because of revert)
    # - Allowance on AMM for TKA = 50 TKA (residual)
    assert vault.functions.userShares(user).call() == 0
    assert token_b.functions.balanceOf(user).call() == swap_amount
    assert token_b.functions.allowance(user, vault.address).call() == swap_amount
    assert token_a.functions.allowance(user, amm.address).call() == 50 * 10**18

    # --- COMPENSATION STEP 1: UNWIND SWAP (Reverse Step 2) ---
    # Direction: User must approve AMM to pull TKB!
    token_b.functions.approve(amm.address, swap_amount).transact({"from": user})
    assert token_b.functions.allowance(user, amm.address).call() == swap_amount

    tx_unwind = amm.functions.unwindSwapWithSagaId(saga_id, swap_amount).transact({"from": user})
    rec_unwind = w3.eth.wait_for_transaction_receipt(tx_unwind)
    assert rec_unwind.status == 1

    # Post-unwind verification:
    # - AMM consumed all 100 TKB allowance
    # - User TKB balance is back to 0
    # - User TKA balance is restored to initial 500 TKA
    assert token_b.functions.allowance(user, amm.address).call() == 0
    assert token_b.functions.balanceOf(user).call() == 0
    assert token_a.functions.balanceOf(user).call() == initial_tka

    # --- COMPENSATION STEP 2: REVOKE RESIDUAL ALLOWANCES (Reverse Step 1 & Clean Vault) ---
    # Revoke residual 50 TKA allowance to AMM
    token_a.functions.approve(amm.address, 0).transact({"from": user})
    assert token_a.functions.allowance(user, amm.address).call() == 0

    # Clean up stranded Vault allowance on Token B
    token_b.functions.approve(vault.address, 0).transact({"from": user})
    assert token_b.functions.allowance(user, vault.address).call() == 0

    # Final Invariant Check
    assert token_a.functions.balanceOf(user).call() == initial_tka
    assert token_b.functions.balanceOf(user).call() == 0
    assert vault.functions.userShares(user).call() == 0
    assert token_a.functions.allowance(user, amm.address).call() == 0
    assert token_b.functions.allowance(user, amm.address).call() == 0
    assert token_b.functions.allowance(user, vault.address).call() == 0


def test_adversarial_two_swaps_opposite_directions(eth_env):
    """
    User executes two swaps in opposite directions under different sagaIds:
    Saga A: 50 TKA -> 50 TKB
    Saga B: 20 TKB -> 20 TKA
    Proves that Saga A and Saga B maintain isolated compensation debt.
    """
    user = eth_env["user_a"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    saga_a = Web3.keccak(text="saga_opposite_A")
    saga_b = Web3.keccak(text="saga_opposite_B")

    # Saga A: Swap 50 TKA -> 50 TKB
    token_a.functions.approve(amm.address, 50 * 10**18).transact({"from": user})
    amm.functions.swapWithSagaId(saga_a, token_a.address, token_b.address, 50 * 10**18, 50 * 10**18).transact({"from": user})

    # Saga B: Swap 20 TKB -> 20 TKA
    token_b.functions.approve(amm.address, 20 * 10**18).transact({"from": user})
    amm.functions.swapWithSagaId(saga_b, token_b.address, token_a.address, 20 * 10**18, 20 * 10**18).transact({"from": user})

    # Unwind Saga A: Requires 50 TKB, returns 50 TKA
    # User currently has 30 TKB (received 50, spent 20 in Saga B). User mints 20 TKB from faucet to have 50.
    token_b.functions.faucet(20 * 10**18).transact({"from": user})
    token_b.functions.approve(amm.address, 50 * 10**18).transact({"from": user})
    amm.functions.unwindSwapWithSagaId(saga_a, 50 * 10**18).transact({"from": user})

    # Saga A is now fully unwound; cannot unwind Saga A again
    with pytest.raises(Exception) as exc_info:
        amm.functions.unwindSwapWithSagaId(saga_a, 1).transact({"from": user})
    assert "exceeds remaining saga output" in str(exc_info.value) or "revert" in str(exc_info.value).lower()

    # Saga B remains independently unwindable! Unwind Saga B: return 20 TKA, get 20 TKB back
    token_a.functions.approve(amm.address, 20 * 10**18).transact({"from": user})
    amm.functions.unwindSwapWithSagaId(saga_b, 20 * 10**18).transact({"from": user})


def test_adversarial_partial_unwinds_and_replay_prevention(eth_env):
    """
    User swaps 100 tokens, then performs partial unwinds:
    - 40% unwind (succeeds)
    - 60% unwind (succeeds)
    - Replay attempt for any further amount (must fail)
    """
    user = eth_env["user_a"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    saga_id = Web3.keccak(text="saga_partial_unwind")
    total_amount = 100 * 10**18

    token_a.functions.approve(amm.address, total_amount).transact({"from": user})
    amm.functions.swapWithSagaId(saga_id, token_a.address, token_b.address, total_amount, total_amount).transact({"from": user})

    # Approve AMM for total TKB
    token_b.functions.approve(amm.address, total_amount).transact({"from": user})

    # Partial Unwind 1: 40 TKB
    amm.functions.unwindSwapWithSagaId(saga_id, 40 * 10**18).transact({"from": user})

    # Attempt to unwind 70 TKB (40 + 70 = 110 > 100) -> MUST FAIL
    with pytest.raises(Exception) as exc_info:
        amm.functions.unwindSwapWithSagaId(saga_id, 70 * 10**18).transact({"from": user})
    assert "exceeds remaining saga output" in str(exc_info.value) or "revert" in str(exc_info.value).lower()

    # Partial Unwind 2: Remaining 60 TKB -> MUST SUCCEED
    amm.functions.unwindSwapWithSagaId(saga_id, 60 * 10**18).transact({"from": user})

    # Replay attempt for even 1 wei -> MUST FAIL
    with pytest.raises(Exception) as exc_info:
        amm.functions.unwindSwapWithSagaId(saga_id, 1).transact({"from": user})
    assert "exceeds remaining saga output" in str(exc_info.value) or "revert" in str(exc_info.value).lower()


def test_adversarial_overlapping_swaps_different_users(eth_env):
    """User A and User B execute concurrent swaps; unwinding User A's saga does not affect User B."""
    user_a = eth_env["user_a"]
    user_b = eth_env["user_b"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    saga_a = Web3.keccak(text="saga_user_A")
    saga_b = Web3.keccak(text="saga_user_B")

    # User A swaps 50 TKA -> 50 TKB
    token_a.functions.approve(amm.address, 50 * 10**18).transact({"from": user_a})
    amm.functions.swapWithSagaId(saga_a, token_a.address, token_b.address, 50 * 10**18, 50 * 10**18).transact({"from": user_a})

    # User B swaps 50 TKB -> 50 TKA
    token_b.functions.approve(amm.address, 50 * 10**18).transact({"from": user_b})
    amm.functions.swapWithSagaId(saga_b, token_b.address, token_a.address, 50 * 10**18, 50 * 10**18).transact({"from": user_b})

    # User A unwinds saga_a
    token_b.functions.approve(amm.address, 50 * 10**18).transact({"from": user_a})
    amm.functions.unwindSwapWithSagaId(saga_a, 50 * 10**18).transact({"from": user_a})

    # User B's saga_b is completely intact and can still be unwound by User B
    token_a.functions.approve(amm.address, 50 * 10**18).transact({"from": user_b})
    amm.functions.unwindSwapWithSagaId(saga_b, 50 * 10**18).transact({"from": user_b})


def test_adversarial_unwind_using_tokens_outside_recorded_swap(eth_env):
    """
    User acquires tokens from an external faucet and attempts to unwind without a matching sagaId,
    or using someone else's sagaId.
    """
    user_b = eth_env["user_b"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    # Non-existent sagaId
    fake_saga = Web3.keccak(text="fabricated_saga_id")
    token_b.functions.approve(amm.address, 100 * 10**18).transact({"from": user_b})
    with pytest.raises(Exception) as exc_info:
        amm.functions.unwindSwapWithSagaId(fake_saga, 100 * 10**18).transact({"from": user_b})
    assert "saga record not found" in str(exc_info.value) or "revert" in str(exc_info.value).lower()


def test_adversarial_unauthorized_unwind_attempt(eth_env):
    """User B attempts to unwind User A's valid sagaId."""
    user_a = eth_env["user_a"]
    user_b = eth_env["user_b"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    saga_a = Web3.keccak(text="saga_user_A_private")
    token_a.functions.approve(amm.address, 50 * 10**18).transact({"from": user_a})
    amm.functions.swapWithSagaId(saga_a, token_a.address, token_b.address, 50 * 10**18, 50 * 10**18).transact({"from": user_a})

    # User B tries to unwind User A's saga
    token_b.functions.approve(amm.address, 50 * 10**18).transact({"from": user_b})
    with pytest.raises(Exception) as exc_info:
        amm.functions.unwindSwapWithSagaId(saga_a, 50 * 10**18).transact({"from": user_b})
    assert "caller is not saga initiator" in str(exc_info.value) or "revert" in str(exc_info.value).lower()


def test_adversarial_insufficient_liquidity(eth_env):
    """Attempting to swap more tokens than available in pool reserves must revert."""
    user = eth_env["user_a"]
    token_a = eth_env["token_a"]
    token_b = eth_env["token_b"]
    amm = eth_env["amm"]

    pool_tkb = token_b.functions.balanceOf(amm.address).call()
    excessive_amount = pool_tkb + (1000 * 10**18)
    saga_id = Web3.keccak(text="excessive_swap")

    token_a.functions.faucet(excessive_amount).transact({"from": user})
    token_a.functions.approve(amm.address, excessive_amount).transact({"from": user})

    with pytest.raises(Exception) as exc_info:
        amm.functions.swapWithSagaId(saga_id, token_a.address, token_b.address, excessive_amount, excessive_amount).transact({"from": user})
    assert "insufficient pool liquidity" in str(exc_info.value) or "revert" in str(exc_info.value).lower()


def test_adversarial_unauthorized_liquidity_drain(eth_env):
    """Non-owner caller attempts to drain liquidity from TestAMM."""
    user = eth_env["user_a"]
    amm = eth_env["amm"]

    with pytest.raises(Exception) as exc_info:
        amm.functions.withdrawLiquidity(100 * 10**18, 100 * 10**18).transact({"from": user})
    assert "caller is not the owner" in str(exc_info.value) or "revert" in str(exc_info.value).lower()


def test_adversarial_vault_no_persistent_failure(eth_env):
    """Verifies that deliberate failure in depositWithFailFlag is strictly ephemeral."""
    user = eth_env["user_a"]
    token_b = eth_env["token_b"]
    vault = eth_env["vault"]

    deposit_amt = 25 * 10**18
    token_b.functions.faucet(deposit_amt * 2).transact({"from": user})
    token_b.functions.approve(vault.address, deposit_amt * 2).transact({"from": user})

    # Deliberate failure call reverts
    with pytest.raises(Exception):
        vault.functions.depositWithFailFlag(deposit_amt, True).transact({"from": user})

    # Immediate standard deposit call succeeds
    tx = vault.functions.deposit(deposit_amt).transact({"from": user})
    rec = eth_env["w3"].eth.wait_for_transaction_receipt(tx)
    assert rec.status == 1
    assert vault.functions.userShares(user).call() >= deposit_amt


def test_adversarial_vault_excessive_withdraw(eth_env):
    """User attempts to withdraw more shares than they have deposited."""
    user = eth_env["user_a"]
    vault = eth_env["vault"]

    user_shares = vault.functions.userShares(user).call()
    with pytest.raises(Exception) as exc_info:
        vault.functions.withdraw(user_shares + (100 * 10**18)).transact({"from": user})
    assert "insufficient shares" in str(exc_info.value) or "revert" in str(exc_info.value).lower()
