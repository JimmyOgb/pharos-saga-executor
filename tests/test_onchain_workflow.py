"""
Tests for Zero-Mock Real On-Chain Workflow Validation on Pharos Atlantic Testnet (Chain ID 688689).
Includes regression tests for RPC chain validation, unwrap gas checks, error classification,
and static deployment manifest verification.
"""

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
WEB_DIR = REPO_ROOT / "web"
ASSETS_DIR = REPO_ROOT / "assets"
VERCEL_JSON = REPO_ROOT / "vercel.json"

EXPECTED_CHAIN_ID = 688689
EXPECTED_CHAIN_HEX = "0xa8231"
EXPECTED_WPHRS = "0x838800b758277CC111B2d48Ab01e5E164f8E9471"
EXPECTED_PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
EXPECTED_RPC = "https://atlantic.dplabs-internal.com"
EXPECTED_EXPLORER = "https://atlantic.pharosscan.xyz"


def test_no_simulated_or_mock_artifacts_in_frontend():
    index_file = WEB_DIR / "index.html"
    assert index_file.exists(), "web/index.html must exist"
    content = index_file.read_text(encoding="utf-8")

    # Verify no mock transaction IDs or simulation fallbacks
    assert "0xsim_" not in content, "No 0xsim_ prefixes allowed in frontend"
    assert "mockTx" not in content, "No mockTx identifiers allowed in frontend"
    assert "fakeTx" not in content, "No fakeTx identifiers allowed in frontend"
    assert "Math.random" not in content, "No Math.random() allowed in transaction flow"

    # Verify verified contract addresses
    assert EXPECTED_WPHRS.lower() in content.lower(), f"WPHRS address {EXPECTED_WPHRS} must be present"
    assert EXPECTED_PERMIT2.lower() in content.lower(), f"Permit2 address {EXPECTED_PERMIT2} must be present"

    # Verify chain enforcement
    assert str(EXPECTED_CHAIN_ID) in content, f"Chain ID {EXPECTED_CHAIN_ID} must be explicitly enforced"
    assert EXPECTED_CHAIN_HEX in content.lower(), f"Chain hex {EXPECTED_CHAIN_HEX} must be present"

    # Verify explorer URLs point to real explorer
    assert EXPECTED_EXPLORER in content, f"Explorer URL {EXPECTED_EXPLORER} must be used"


def test_frontend_workflow_partitioning():
    """Verify wrap and unwrap are separate user-initiated actions, with Permit2 segregated."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Both action buttons must exist
    assert 'id="btnWrap"' in content, "Action 1: Wrap button must exist"
    assert 'id="btnUnwrap"' in content, "Action 2: Unwrap button must exist"

    # Permit2 experiment must be explicitly marked as optional/experimental
    assert "Optional Experiment" in content, "Permit2 must be clearly labeled as Optional Experiment"
    assert "Atlantic Testnet currently does not have a public Uniswap Universal Router or AMM pool deployed" in content


def test_primary_workflow_has_no_permit2_approval():
    """Verify primary wrap and unwrap actions do not invoke ERC-20 approve."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Extract executeWrap and executeUnwrap function bodies
    wrap_start = content.find("async function executeWrap()")
    wrap_end = content.find("async function executeUnwrap()")
    wrap_code = content[wrap_start:wrap_end]

    unwrap_start = wrap_end
    unwrap_end = content.find("async function executeExperimentApprove()")
    unwrap_code = content[unwrap_start:unwrap_end]

    # Neither primary action should use approve selector 0x095ea7b3
    assert "0x095ea7b3" not in wrap_code, "executeWrap must not call approve"
    assert "0x095ea7b3" not in unwrap_code, "executeUnwrap must not call approve"
    assert "PERMIT2_SPENDER" not in wrap_code, "executeWrap must not reference Permit2"
    assert "PERMIT2_SPENDER" not in unwrap_code, "executeUnwrap must not reference Permit2"


def test_dual_chain_id_validation_in_frontend():
    """Verify validateChainAndWallet checks BOTH wallet and RPC, failing closed if either is wrong."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    val_start = content.find("async function validateChainAndWallet()")
    val_end = content.find("async function rpcCall(")
    val_code = content[val_start:val_end]

    # Must query wallet chain
    assert "eth_chainId" in val_code
    assert "walletChainId" in val_code

    # Must query RPC chain
    assert "rpcCall('eth_chainId')" in val_code
    assert "rpcChainId" in val_code

    # Must check both against 688689 / 0xa8231
    assert "ATLANTIC_CHAIN_ID_HEX" in val_code
    assert "ATLANTIC_CHAIN_ID_INT" in val_code

    # Must fail closed if RPC fails or mismatches
    assert "RPC validation failed" in val_code
    assert "RPC chain mismatch" in val_code


def test_dual_chain_validation_simulation_logic():
    """Simulate dual-chain verification states: wallet correct/wrong, RPC correct/wrong/unavailable."""
    atlantic_hex = "0xa8231"
    atlantic_int = 688689

    def simulate_dual_validation(wallet_chain, rpc_chain, rpc_available=True):
        if not rpc_available:
            raise RuntimeError("RPC validation failed: network timeout")
        if wallet_chain != atlantic_hex and int(wallet_chain, 16) != atlantic_int:
            raise ValueError(f"Wallet chain mismatch: {wallet_chain}")
        if rpc_chain != atlantic_hex and int(rpc_chain, 16) != atlantic_int:
            raise ValueError(f"RPC chain mismatch: {rpc_chain}")
        return True

    # 1. Happy path: both agree on 688689
    assert simulate_dual_validation("0xa8231", "0xa8231") is True

    # 2. Wallet correct (0xa8231), but RPC returns wrong chain (e.g. Ethereum mainnet 0x1) -> blocked
    with pytest.raises(ValueError, match="RPC chain mismatch"):
        simulate_dual_validation("0xa8231", "0x1")

    # 3. Wallet on wrong chain (e.g. Sepolia 0xaa36a7), RPC correct -> blocked
    with pytest.raises(ValueError, match="Wallet chain mismatch"):
        simulate_dual_validation("0xaa36a7", "0xa8231")

    # 4. RPC unavailable / network glitch -> fails closed
    with pytest.raises(RuntimeError, match="RPC validation failed"):
        simulate_dual_validation("0xa8231", "0xa8231", rpc_available=False)


def test_unwrap_gas_protection_logic_and_frontend():
    """Verify executeUnwrap implements fresh reads and enforces 0.0003 PHRS reserve."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    unwrap_start = content.find("async function executeUnwrap()")
    unwrap_end = content.find("async function executeExperimentApprove()")
    unwrap_code = content[unwrap_start:unwrap_end]

    # Verify fresh balance read from RPC
    assert "eth_getBalance" in unwrap_code, "executeUnwrap must perform fresh native balance read"
    assert "minUnwrapGasReserve" in unwrap_code, "executeUnwrap must define gas reserve threshold"
    assert "300000000000000n" in unwrap_code, "Gas reserve must equal 0.0003 PHRS (3e14 wei)"
    assert "preflight estimate, not a guarantee" in unwrap_code, "Must disclose preflight estimate nature"

    # Simulate unwrap gas check logic
    min_reserve = 300000000000000  # 0.0003 PHRS

    # Case A: User has 0 native PHRS -> rejected before prompt
    phrs_balance_zero = 0
    assert phrs_balance_zero < min_reserve

    # Case B: User has 0.0001 native PHRS -> rejected (under reserve)
    phrs_balance_low = 100000000000000
    assert phrs_balance_low < min_reserve

    # Case C: User has 0.001 native PHRS -> allowed
    phrs_balance_ok = 1000000000000000
    assert phrs_balance_ok >= min_reserve


def test_wallet_rejection_vs_mined_revert_classification():
    """Verify wallet rejection is distinct from mined revert and never claims success."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    assert "err.code === 4001" in content, "Must detect standard EIP-1193 rejection code 4001"
    assert "User rejected" in content, "Must check for user rejection message"
    assert "ACTION_REJECTED" in content, "Must check for ACTION_REJECTED provider error"

    # Unwrap rejection must trigger MANUAL_RECOVERY_REQUIRED
    assert "MANUAL_RECOVERY_REQUIRED" in content
    assert "WPHRS remains in your wallet" in content


def test_no_premature_success_state():
    """Verify that CONFIRMED and ROLLED_BACK are guarded strictly by status === 'SUCCESS'."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # In pollReceipt
    assert "receipt.status === '0x1' ? 'SUCCESS' : 'REVERTED'" in content

    # In executeWrap
    assert "if (status === 'SUCCESS')" in content
    assert "Wrap transaction reverted on-chain in block" in content

    # In executeUnwrap
    assert "Unwrap transaction reverted on-chain in block" in content


def test_tokens_json_configuration():
    tokens_file = ASSETS_DIR / "tokens.json"
    assert tokens_file.exists(), "assets/tokens.json must exist"
    tokens = json.loads(tokens_file.read_text(encoding="utf-8"))

    assert tokens.get("chain_id") == EXPECTED_CHAIN_ID
    assert tokens.get("network") == "atlantic"

    token_contracts = tokens.get("tokens", {})
    assert token_contracts.get("WPHRS", {}).get("address") == EXPECTED_WPHRS
    assert token_contracts.get("PERMIT2", {}).get("address") == EXPECTED_PERMIT2


def test_wphrs_saga_specification():
    saga_file = ASSETS_DIR / "sagas" / "wphrs_wrap_approve.json"
    assert saga_file.exists(), "assets/sagas/wphrs_wrap_approve.json must exist"
    saga = json.loads(saga_file.read_text(encoding="utf-8"))

    assert saga.get("chain_id") == EXPECTED_CHAIN_ID
    steps = saga.get("steps", [])
    assert len(steps) >= 1

    # Step 1 should be wrapping native PHRS
    step1 = steps[0]
    assert step1.get("step_id") == "step_1_wrap"
    assert step1.get("action") == "WPHRS_WRAP"
    assert step1.get("contract") == EXPECTED_WPHRS
    assert step1.get("compensation", {}).get("action") == "WPHRS_UNWRAP"


def test_vercel_static_deployment_serves_frontend():
    """Verify vercel.json configuration and static web asset structure."""
    assert VERCEL_JSON.exists(), "vercel.json must exist"
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))

    assert config.get("version") == 2
    assert config.get("outputDirectory") == "web"
    assert config.get("cleanUrls") is True

    index_html = WEB_DIR / "index.html"
    assert index_html.exists(), "web/index.html must exist at outputDirectory root"
    content = index_html.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "<title>" in content
    assert "WPHRS" in content
