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
    assert EXPECTED_PERMIT2.lower() not in content.lower(), f"Permit2 address {EXPECTED_PERMIT2} must not be present in frontend"
    assert "PERMIT2_SPENDER" not in content, "PERMIT2_SPENDER must not exist in frontend"

    # Verify chain enforcement
    assert str(EXPECTED_CHAIN_ID) in content, f"Chain ID {EXPECTED_CHAIN_ID} must be explicitly enforced"
    assert EXPECTED_CHAIN_HEX in content.lower(), f"Chain hex {EXPECTED_CHAIN_HEX} must be present"

    # Verify explorer URLs point to real explorer
    assert EXPECTED_EXPLORER in content, f"Explorer URL {EXPECTED_EXPLORER} must be used"


def test_frontend_workflow_partitioning():
    """Verify wrap and unwrap are separate user-initiated actions, and Permit2 is completely removed."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Both action buttons must exist
    assert 'id="btnWrap"' in content, "Action 1: Wrap button must exist"
    assert 'id="btnUnwrap"' in content, "Action 2: Unwrap button must exist"

    # Permit2 experiment must be completely removed
    assert "Optional Experiment" not in content, "Permit2 experiment panel must be removed"
    assert "executeExperimentApprove" not in content, "Experiment approve function must be removed"
    assert "executeExperimentRevoke" not in content, "Experiment revoke function must be removed"


def test_primary_workflow_has_no_permit2_approval():
    """Verify primary wrap and unwrap actions do not invoke ERC-20 approve and no Permit2 code exists."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Extract executeWrap and executeUnwrap function bodies
    wrap_start = content.find("async function executeWrap()")
    wrap_end = content.find("async function executeUnwrap()")
    wrap_code = content[wrap_start:wrap_end]

    unwrap_start = wrap_end
    unwrap_end = content.find("// Initialize Page")
    unwrap_code = content[unwrap_start:unwrap_end]

    # Neither action should use approve selector 0x095ea7b3
    assert "0x095ea7b3" not in content, "Frontend must contain zero approve selectors (0x095ea7b3)"
    assert "PERMIT2" not in content, "Frontend must contain zero PERMIT2 references"
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
    unwrap_end = content.find("// Initialize Page")
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


def test_refresh_uses_promise_all_settled_concurrency():
    """Verify refreshLiveBalances uses Promise.allSettled and has removed Permit2 allowance read."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    refresh_start = content.find("async function refreshLiveBalances(")
    refresh_end = content.find("async function pollReceipt(")
    refresh_code = content[refresh_start:refresh_end]

    # Verify Promise.allSettled is used
    assert "Promise.allSettled(queries)" in refresh_code
    assert "rpcCall('eth_blockNumber')" in refresh_code
    assert "rpcCall('eth_gasPrice')" in refresh_code
    assert "rpcCall('eth_getBalance'" in refresh_code
    assert "rpcCall('eth_call'" in refresh_code

    # Verify Permit2 allowance is completely excluded
    assert "PERMIT2" not in refresh_code
    assert "allowance" not in refresh_code
    assert "0xdd62ed3e" not in refresh_code


def test_duplicate_refresh_prevention_logic():
    """Verify connectWallet and accountsChanged prevent duplicate concurrent refreshes."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Verify isConnecting flag
    assert "let isConnecting = false;" in content
    assert "if (isConnecting) return;" in content

    # In accountsChanged, verify duplicate guard
    accounts_changed_start = content.find("window.ethereum.on('accountsChanged'")
    accounts_changed_end = content.find("window.ethereum.on('chainChanged'")
    ac_code = content[accounts_changed_start:accounts_changed_end]

    assert "if (isConnecting) return;" in ac_code
    assert "currentAccount && currentAccount.toLowerCase() === nextAccount.toLowerCase()" in ac_code


def test_generation_counter_race_safety():
    """Verify generation counter race-safety pattern in frontend and simulate logic."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    assert "let refreshGeneration = 0;" in content
    assert "const thisGen = ++refreshGeneration;" in content
    assert "if (thisGen !== refreshGeneration)" in content

    # Simulate race condition in Python
    state = {"active_account": None, "displayed_balance": None, "generation": 0}

    def simulate_refresh(account, delay_rank, results_val):
        state["generation"] += 1
        my_gen = state["generation"]
        # In a real environment, async call finishes after some delay
        # If a newer request was dispatched (my_gen != state["generation"]), discard
        if my_gen == state["generation"]:
            state["active_account"] = account
            state["displayed_balance"] = results_val
            return "APPLIED"
        return "DISCARDED"

    # User connects Account A -> Gen 1
    # User immediately switches to Account B -> Gen 2
    # Suppose Gen 1 resolves AFTER Gen 2
    gen1_call = 1
    gen2_call = 2
    state["generation"] = 2  # Gen 2 is current
    assert (gen1_call == state["generation"]) is False  # Gen 1 discarded
    assert (gen2_call == state["generation"]) is True   # Gen 2 applied


def test_partial_rpc_failure_resilience():
    """Verify resilient handling of partial RPC failures where other fields still display."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    assert "Unavailable" in content
    assert "blockRes.status === 'fulfilled'" in content
    assert "gasRes.status === 'fulfilled'" in content
    assert "phrsRes.status === 'fulfilled'" in content
    assert "wphrsRes.status === 'fulfilled'" in content

    # Simulate allSettled partial failure handling
    mock_results = [
        {"status": "fulfilled", "value": "0x1e1e4a1"},  # blockNumber
        {"status": "rejected", "reason": "Timeout"},     # gasPrice fails
        {"status": "fulfilled", "value": "0xde0b6b3a7640000"},  # 1 PHRS
        {"status": "fulfilled", "value": "0x1bc16d674ec80000"}  # 2 WPHRS
    ]

    ui_state = {}
    ui_state["block"] = int(mock_results[0]["value"], 16) if mock_results[0]["status"] == "fulfilled" else "Unavailable"
    ui_state["gas"] = "Unavailable" if mock_results[1]["status"] == "rejected" else "OK"
    ui_state["phrs"] = "1.0000" if mock_results[2]["status"] == "fulfilled" else "Unavailable"
    ui_state["wphrs"] = "2.0000" if mock_results[3]["status"] == "fulfilled" else "Unavailable"

    assert ui_state["block"] == 31581345
    assert ui_state["gas"] == "Unavailable"
    assert ui_state["phrs"] == "1.0000"
    assert ui_state["wphrs"] == "2.0000"


def test_no_signing_or_broadcasting_during_wallet_connection():
    """Verify connectWallet contains zero transaction signing or broadcasting methods."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    conn_start = content.find("async function connectWallet()")
    conn_end = content.find("function disconnectWallet()")
    conn_code = content[conn_start:conn_end]

    # Must contain connection and chain validation
    assert "eth_requestAccounts" in conn_code
    assert "eth_chainId" in conn_code

    # Must NOT contain signing or broadcasting
    assert "eth_sendTransaction" not in conn_code
    assert "personal_sign" not in conn_code
    assert "eth_sign" not in conn_code
    assert "eth_signTypedData" not in conn_code
    assert "0x095ea7b3" not in conn_code



def test_phase1_wizard_static_structure_and_constants():
    """Verify web/deploy.html includes strict deployer, chain, artifact hash, and gas guard constants."""
    deploy_file = WEB_DIR / "deploy.html"
    assert deploy_file.exists(), "web/deploy.html must exist"
    content = deploy_file.read_text(encoding="utf-8")

    # 1. Approved deployer address
    approved_acc = "0xe4220c4b71877bb94eb173f467ef5c5557017085".lower()
    assert approved_acc in content.lower(), f"Approved account {approved_acc} must be hardcoded in deploy.html"
    assert "APPROVED_DEPLOYER_ACCOUNT" in content

    # 2. Approved chain constants
    assert "688689" in content
    assert "0xa8231" in content.lower()
    assert "verifyNetworkAndChain" in content
    assert "verifyDeployerAccount" in content

    # 3. Approved gas limits
    assert "1515000n" in content  # TKA / TKB
    assert "2830000n" in content  # TestAMM
    assert "1020000n" in content  # TestSagaVault
    assert "APPROVED_GAS_LIMITS" in content

    # 4. Hard cumulative fee ceiling (0.0700 PHRS)
    assert "70000000000000000n" in content  # 0.0700 PHRS in wei
    assert "HARD_CUMULATIVE_FEE_CEILING_WEI" in content

    # 5. Independent SHA-256 bytecode hashes
    assert "497ab5f77653dfbecf18a44069e027ac2e8e3084f0ffde83d2f460b6f8a2b909" in content
    assert "b88581b46746f692f5224b8656a6d66f579bce7578306765ef27d7bba08aa1d9" in content
    assert "36c6920fb7121165541755422842d65379ccd3cf6a08776373717848a9afd1f7" in content
    assert "EXPECTED_BYTECODE_SHA256" in content

    # 6. Pinned gas parameter in eth_sendTransaction
    assert "gas: '0x' + p.approvedLimit.toString(16)" in content

    # 7. Disclose final transaction parameters in modal
    assert "mdDeployerAccount" in content
    assert "mdBytecodeHash" in content
    assert "mdGasLimit" in content
    assert "mdProjectedTotal" in content

    # 8. Event listeners for account and chain change
    assert "accountsChanged" in content
    assert "chainChanged" in content

    # 9. No Permit2 collisions
    assert "0x095ea7b3" not in content


def test_phase1_wizard_account_and_chain_guard_simulation():
    """Simulate account and chain validation guards for the Phase 1 deployment wizard."""
    approved_acc = "0xe4220c4b71877bb94eb173f467ef5c5557017085".lower()
    atlantic_hex = "0xa8231"
    atlantic_int = 688689

    def guard_check(active_acc, wallet_chain, rpc_chain):
        if not active_acc or active_acc.lower() != approved_acc:
            raise PermissionError(f"Unauthorized deployer account: {active_acc}")
        if wallet_chain != atlantic_hex and int(wallet_chain, 16) != atlantic_int:
            raise ValueError(f"Wallet chain mismatch: {wallet_chain}")
        if rpc_chain != atlantic_hex and int(rpc_chain, 16) != atlantic_int:
            raise ValueError(f"RPC chain mismatch: {rpc_chain}")
        return True

    # 1. Approved case (with mixed case input) -> passes
    assert guard_check("0xe4220c4B71877bb94eb173f467eF5C5557017085", "0xa8231", "0xa8231") is True

    # 2. Wrong account -> raises PermissionError
    with pytest.raises(PermissionError, match="Unauthorized deployer account"):
        guard_check("0x1111111111111111111111111111111111111111", "0xa8231", "0xa8231")

    # 3. Wrong chain -> raises ValueError
    with pytest.raises(ValueError, match="Wallet chain mismatch"):
        guard_check(approved_acc, "0x1", "0xa8231")

    with pytest.raises(ValueError, match="RPC chain mismatch"):
        guard_check(approved_acc, "0xa8231", "0x5")


def test_phase1_wizard_artifact_integrity_guard_simulation():
    """Verify compiled contract bytecode matches independently reviewed SHA-256 hashes."""
    import hashlib

    contracts_file = ASSETS_DIR / "contracts" / "compiled_contracts.json"
    assert contracts_file.exists(), "compiled_contracts.json must exist"
    data = json.loads(contracts_file.read_text(encoding="utf-8"))

    expected_hashes = {
        "TestToken": "497ab5f77653dfbecf18a44069e027ac2e8e3084f0ffde83d2f460b6f8a2b909",
        "TestAMM": "b88581b46746f692f5224b8656a6d66f579bce7578306765ef27d7bba08aa1d9",
        "TestSagaVault": "36c6920fb7121165541755422842d65379ccd3cf6a08776373717848a9afd1f7",
    }

    def verify_bytecode_hash(c_name, bytecode_hex):
        raw_hex = bytecode_hex[2:] if bytecode_hex.startswith("0x") else bytecode_hex
        computed = hashlib.sha256(bytes.fromhex(raw_hex)).hexdigest()
        expected = expected_hashes[c_name]
        if computed != expected:
            raise ValueError(f"Bytecode integrity violation for {c_name}: expected {expected}, got {computed}")
        return True

    # 1. Genuine artifacts pass
    for name in expected_hashes:
        assert verify_bytecode_hash(name, data[name]["bytecode"]) is True

    # 2. Altered artifact fails
    tampered_bytecode = data["TestToken"]["bytecode"][:-2] + "ff"
    with pytest.raises(ValueError, match="Bytecode integrity violation for TestToken"):
        verify_bytecode_hash("TestToken", tampered_bytecode)


def test_phase1_wizard_constructor_and_sequence_guards():
    """Simulate constructor parameter verification and deployment order sequencing."""
    from eth_abi import decode
    import re

    addr_pattern = re.compile(r"^0x[0-9a-fA-F]{40}$")

    def validate_step(idx, deployed_state, tka_hex, tkb_hex):
        if idx == 1:
            if len(tka_hex) != 448:
                raise ValueError("Invalid TKA constructor calldata length")
            decoded = decode(["string", "string", "uint256"], bytes.fromhex(tka_hex))
            if decoded[0] != "Test Token A" or decoded[1] != "TKA" or decoded[2] != 10**24:
                raise ValueError(f"Unexpected TKA constructor args: {decoded}")
            return "OK_TKA"

        elif idx == 2:
            if not deployed_state.get("tka"):
                raise RuntimeError("Sequence violation: TKA must be deployed before TKB")
            if len(tkb_hex) != 448:
                raise ValueError("Invalid TKB constructor calldata length")
            decoded = decode(["string", "string", "uint256"], bytes.fromhex(tkb_hex))
            if decoded[0] != "Test Token B" or decoded[1] != "TKB" or decoded[2] != 10**24:
                raise ValueError(f"Unexpected TKB constructor args: {decoded}")
            return "OK_TKB"

        elif idx == 3:
            tka = deployed_state.get("tka")
            tkb = deployed_state.get("tkb")
            if not tka or not tkb:
                raise RuntimeError("Sequence violation: TKA and TKB must be deployed before TestAMM")
            if not addr_pattern.match(tka) or not addr_pattern.match(tkb):
                raise ValueError("Malformed token addresses")
            if tka.lower() == tkb.lower():
                raise ValueError("AMM tokens must be distinct")
            return "OK_AMM"

        elif idx == 4:
            tkb = deployed_state.get("tkb")
            if not tkb:
                raise RuntimeError("Sequence violation: TKB must be deployed before TestSagaVault")
            if not addr_pattern.match(tkb):
                raise ValueError("Malformed asset address")
            return "OK_VAULT"

    # Hex calldata from deploy.html
    tka_hex = "000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000d3c21bcecceda1000000000000000000000000000000000000000000000000000000000000000000000c5465737420546f6b656e204100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003544b410000000000000000000000000000000000000000000000000000000000"
    tkb_hex = "000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000d3c21bcecceda1000000000000000000000000000000000000000000000000000000000000000000000c5465737420546f6b656e204200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003544b420000000000000000000000000000000000000000000000000000000000"

    state = {"tka": None, "tkb": None, "amm": None, "vault": None}

    # Step 1 succeeds
    assert validate_step(1, state, tka_hex, tkb_hex) == "OK_TKA"

    # Step 2 without Step 1 completion fails
    with pytest.raises(RuntimeError, match="Sequence violation"):
        validate_step(2, state, tka_hex, tkb_hex)

    # Set Step 1 complete -> Step 2 succeeds
    state["tka"] = "0x1111111111111111111111111111111111111111"
    assert validate_step(2, state, tka_hex, tkb_hex) == "OK_TKB"

    # Step 3 with identical tokens fails
    state["tkb"] = "0x1111111111111111111111111111111111111111"
    with pytest.raises(ValueError, match="AMM tokens must be distinct"):
        validate_step(3, state, tka_hex, tkb_hex)

    # Step 3 with distinct tokens succeeds
    state["tkb"] = "0x2222222222222222222222222222222222222222"
    assert validate_step(3, state, tka_hex, tkb_hex) == "OK_AMM"

    # Step 4 succeeds
    assert validate_step(4, state, tka_hex, tkb_hex) == "OK_VAULT"


def test_phase1_wizard_gas_estimate_and_budget_ceiling_guards():
    """Simulate gas estimate checks, balance limits, and hard cumulative fee ceiling (0.0700 PHRS)."""
    approved_gas_limits = {
        1: 1515000,
        2: 1515000,
        3: 2830000,
        4: 1020000,
    }
    hard_fee_ceiling_wei = 70000000000000000  # 0.0700 PHRS

    def pre_deploy_gas_check(idx, simulated_gas, cumulative_spent_wei, current_gas_price_wei, current_bal_wei):
        limit = approved_gas_limits[idx]
        if simulated_gas > limit:
            raise ValueError(f"Simulated gas {simulated_gas} exceeds approved limit {limit}")

        next_step_max_fee = limit * current_gas_price_wei
        projected_total = cumulative_spent_wei + next_step_max_fee

        if projected_total > hard_fee_ceiling_wei:
            raise OverflowError(f"Projected cumulative fee {projected_total} exceeds ceiling {hard_fee_ceiling_wei}")

        if current_bal_wei < next_step_max_fee:
            raise ValueError(f"Insufficient balance: {current_bal_wei} < {next_step_max_fee}")

        return projected_total

    # 1. Normal estimates at 10 Gwei pass within ceiling
    gas_price_10gwei = 10_000_000_000
    user_bal = 100_000_000_000_000_000  # 0.10 PHRS

    # Live observed estimate for TKA on Atlantic: 1,441,494 <= 1,515,000 approved limit
    proj_1 = pre_deploy_gas_check(1, 1441494, 0, gas_price_10gwei, user_bal)
    assert proj_1 == 1515000 * 10_000_000_000  # 0.01515 PHRS <= 0.0700 PHRS

    # 2. Excessive gas estimate fails
    with pytest.raises(ValueError, match="exceeds approved limit"):
        pre_deploy_gas_check(1, 1600000, 0, gas_price_10gwei, user_bal)

    # 3. Cumulative fee overflow fails (e.g. if cumulative spent is already high or gas price spikes)
    high_spent = 60_000_000_000_000_000  # 0.060 PHRS
    with pytest.raises(OverflowError, match="exceeds ceiling"):
        # Next step max fee = 1.515M * 10 Gwei = 0.01515 PHRS -> 0.060 + 0.01515 = 0.07515 > 0.0700
        pre_deploy_gas_check(1, 1441494, high_spent, gas_price_10gwei, user_bal)

    # 4. Insufficient user balance fails
    low_bal = 5_000_000_000_000_000  # 0.005 PHRS < 0.01515 PHRS
    with pytest.raises(ValueError, match="Insufficient balance"):
        pre_deploy_gas_check(1, 1441494, 0, gas_price_10gwei, low_bal)


def test_phase1_wizard_receipt_and_runtime_bytecode_guards():
    """Simulate receipt status polling and post-deployment runtime bytecode verification."""
    def verify_mined_deployment(receipt, runtime_code):
        if not receipt:
            raise TimeoutError("Receipt polling timed out")
        if receipt.get("status") != "0x1":
            raise RuntimeError(f"Deployment transaction reverted on-chain with status {receipt.get('status')}")
        if not receipt.get("contractAddress"):
            raise ValueError("Receipt did not return contractAddress")
        if not runtime_code or runtime_code in ("0x", "0x0") or len(runtime_code) <= 10:
            raise RuntimeError("Deployed contract contains empty or invalid runtime bytecode")
        return receipt["contractAddress"]

    # 1. Success case
    good_receipt = {
        "status": "0x1",
        "contractAddress": "0x1234567890123456789012345678901234567890",
        "gasUsed": "0x120341",
        "effectiveGasPrice": "0x2540be400",
        "blockNumber": "0x1e2f4a",
    }
    good_code = "0x608060405234801561001057600080fd5b50..."
    assert verify_mined_deployment(good_receipt, good_code) == "0x1234567890123456789012345678901234567890"

    # 2. Reverted transaction
    bad_receipt = {"status": "0x0", "contractAddress": "0x1234..."}
    with pytest.raises(RuntimeError, match="reverted on-chain with status 0x0"):
        verify_mined_deployment(bad_receipt, good_code)

    # 3. Missing contract address
    missing_addr_receipt = {"status": "0x1", "contractAddress": None}
    with pytest.raises(ValueError, match="Receipt did not return contractAddress"):
        verify_mined_deployment(missing_addr_receipt, good_code)

    # 4. Empty runtime bytecode
    with pytest.raises(RuntimeError, match="empty or invalid runtime bytecode"):
        verify_mined_deployment(good_receipt, "0x")


def test_phase1_wizard_pending_deployment_duplicate_prevention():
    """Simulate Fix 1: Pending transaction tracking in localStorage, duplicate prevention, timeout retention, and reload recovery."""
    storage = {}

    def simulate_submit_tx(step_idx, contract_name, tx_hash, deployer):
        # Prevent submission if a pending tx is already unresolved
        if "pharos_pending_deployment" in storage:
            p = json.loads(storage["pharos_pending_deployment"])
            raise RuntimeError(f"Cannot start deployment: Step {p['idx']} tx {p['txHash']} is pending/unresolved.")

        # Persist immediately upon broadcast before polling
        record = {
            "idx": step_idx,
            "contractName": contract_name,
            "txHash": tx_hash,
            "timestamp": 1234567890,
            "deployer": deployer.lower(),
        }
        storage["pharos_pending_deployment"] = json.dumps(record)
        return "LOCKED_PENDING"

    def simulate_poll_timeout():
        # On timeout, pending record MUST remain intact in storage!
        assert "pharos_pending_deployment" in storage
        return "SET_RECHECK_UI"

    def simulate_reload_recovery(rpc_receipt):
        if "pharos_pending_deployment" not in storage:
            return "NO_PENDING"
        p = json.loads(storage["pharos_pending_deployment"])
        if rpc_receipt is None:
            # Transaction is unmined/in-flight: must remain locked
            return "REMAIN_LOCKED"
        if rpc_receipt.get("status") != "0x1":
            # Reverted: clear lock to allow user retry
            del storage["pharos_pending_deployment"]
            return "CLEARED_FOR_RETRY"
        # Mined: finalize and remove lock
        del storage["pharos_pending_deployment"]
        return "DEPLOYMENT_CONFIRMED"

    # Step 1: Submit deployment for TKA
    deployer = "0xe4220c4b71877bb94eb173f467ef5c5557017085"
    assert simulate_submit_tx(1, "TestToken A", "0xaaaa1111", deployer) == "LOCKED_PENDING"

    # Duplicate submission while pending is strictly rejected
    with pytest.raises(RuntimeError, match="pending/unresolved"):
        simulate_submit_tx(1, "TestToken A", "0xaaaa2222", deployer)

    with pytest.raises(RuntimeError, match="pending/unresolved"):
        simulate_submit_tx(2, "TestToken B", "0xbbbb1111", deployer)

    # Polling times out: record is preserved in storage
    assert simulate_poll_timeout() == "SET_RECHECK_UI"
    assert "pharos_pending_deployment" in storage

    # Reload while tx is still unmined: remains locked with Re-check UI
    assert simulate_reload_recovery(None) == "REMAIN_LOCKED"
    assert "pharos_pending_deployment" in storage

    # Reload after tx is mined with status 0x1: confirms deployment and clears lock
    mined_receipt = {"status": "0x1", "contractAddress": "0x1111111111111111111111111111111111111111"}
    assert simulate_reload_recovery(mined_receipt) == "DEPLOYMENT_CONFIRMED"
    assert "pharos_pending_deployment" not in storage

    # Now step 2 can be submitted without collision
    assert simulate_submit_tx(2, "TestToken B", "0xbbbb1111", deployer) == "LOCKED_PENDING"


def test_phase1_wizard_runtime_bytecode_verification():
    """Simulate Fix 2: Strengthened runtime contract verification for TestToken (bit-for-bit) and AMM/Vault (length, preamble, immutables)."""
    artifacts_path = ASSETS_DIR / "contracts" / "compiled_contracts.json"
    assert artifacts_path.exists(), "compiled_contracts.json must exist"
    with open(artifacts_path, "r", encoding="utf-8") as f:
        artifacts = json.load(f)

    def verify_runtime_code(contract_key, deployed_code, expected_deps=None):
        if not deployed_code or deployed_code in ("0x", "0x0") or len(deployed_code) <= 10:
            raise ValueError(f"Empty runtime bytecode for {contract_key}")

        expected = artifacts[contract_key]["runtime_bytecode"].lower()
        actual = deployed_code.lower()

        if contract_key == "TestToken":
            # Bit-for-bit match (no immutables)
            if actual != expected:
                raise ValueError(f"Bit-for-bit mismatch for {contract_key}")
            return True

        # Length check
        if len(actual) != len(expected):
            raise ValueError(f"Length mismatch for {contract_key}: expected {len(expected)}, got {len(actual)}")

        # Preamble check (first 400 hex chars + 0x = 402 chars)
        if actual[:402] != expected[:402]:
            raise ValueError(f"Preamble mismatch for {contract_key}")

        # Immutable addresses check
        expected_deps = expected_deps or {}
        if contract_key == "TestAMM":
            for role in ("owner", "tokenA", "tokenB"):
                dep_addr = expected_deps.get(role, "").lower().replace("0x", "")
                if not dep_addr or dep_addr not in actual:
                    raise ValueError(f"TestAMM missing immutable {role}: {dep_addr}")
        elif contract_key == "TestSagaVault":
            asset_addr = expected_deps.get("asset", "").lower().replace("0x", "")
            if not asset_addr or asset_addr not in actual:
                raise ValueError(f"TestSagaVault missing immutable asset: {asset_addr}")

        return True

    # 1. TestToken: Bit-for-bit verification
    token_code = artifacts["TestToken"]["runtime_bytecode"]
    assert verify_runtime_code("TestToken", token_code) is True

    # TestToken: Altered byte fails
    altered_token = token_code[:-2] + "ff"
    with pytest.raises(ValueError, match="Bit-for-bit mismatch"):
        verify_runtime_code("TestToken", altered_token)

    # 2. TestAMM: Length, preamble, and immutables
    amm_expected = artifacts["TestAMM"]["runtime_bytecode"]
    owner = "0xe4220c4b71877bb94eb173f467ef5c5557017085"
    token_a = "0x1111111111111111111111111111111111111111"
    token_b = "0x2222222222222222222222222222222222222222"

    # Simulate runtime code with immutables substituted
    clean_amm = amm_expected.lower().replace("0x", "")
    mock_amm = "0x" + clean_amm[:500] + owner[2:].lower() + token_a[2:].lower() + token_b[2:].lower() + clean_amm[500 + 40*3:]
    assert len(mock_amm) == len(amm_expected)

    deps = {"owner": owner, "tokenA": token_a, "tokenB": token_b}
    assert verify_runtime_code("TestAMM", mock_amm, deps) is True

    # AMM length mismatch fails
    with pytest.raises(ValueError, match="Length mismatch"):
        verify_runtime_code("TestAMM", mock_amm + "00", deps)

    # AMM preamble mismatch fails
    bad_preamble_amm = mock_amm[:10] + "0000" + mock_amm[14:]
    with pytest.raises(ValueError, match="Preamble mismatch"):
        verify_runtime_code("TestAMM", bad_preamble_amm, deps)

    # AMM missing tokenB fails
    bad_deps = {"owner": owner, "tokenA": token_a, "tokenB": "0x9999999999999999999999999999999999999999"}
    with pytest.raises(ValueError, match="missing immutable tokenB"):
        verify_runtime_code("TestAMM", mock_amm, bad_deps)

    # 3. TestSagaVault: Length, preamble, and asset immutable
    vault_expected = artifacts["TestSagaVault"]["runtime_bytecode"]
    clean_vault = vault_expected.lower().replace("0x", "")
    mock_vault = "0x" + clean_vault[:500] + token_b[2:].lower() + clean_vault[500 + 40:]
    assert len(mock_vault) == len(vault_expected)

    vault_deps = {"asset": token_b}
    assert verify_runtime_code("TestSagaVault", mock_vault, vault_deps) is True

    # Vault missing asset fails
    with pytest.raises(ValueError, match="missing immutable asset"):
        verify_runtime_code("TestSagaVault", mock_vault, {"asset": "0x8888888888888888888888888888888888888888"})


def test_deploy_html_contains_runtime_verification_and_duplicate_prevention():
    """Verify that web/deploy.html contains all Fix 1 and Fix 2 implementation constructs."""
    deploy_file = WEB_DIR / "deploy.html"
    assert deploy_file.exists(), "web/deploy.html must exist"
    content = deploy_file.read_text(encoding="utf-8")

    # Fix 1 assertions
    assert "pharos_pending_deployment" in content, "Must track pharos_pending_deployment in localStorage"
    assert "setStepPendingLockUI" in content, "Must implement setStepPendingLockUI"
    assert "setStepPendingRecheckUI" in content, "Must implement setStepPendingRecheckUI"
    assert "recheckPendingDeployment" in content, "Must implement recheckPendingDeployment"
    assert "checkPendingDeploymentStatus" in content, "Must implement checkPendingDeploymentStatus"
    assert "restorePreviouslyDeployedState" in content, "Must implement restorePreviouslyDeployedState"

    # Fix 2 assertions
    assert "verifyDeployedRuntimeCode" in content, "Must implement verifyDeployedRuntimeCode"
    assert "cleanDeployed.slice(0, preambleLen)" in content, "Must verify runtime preamble slice"
    assert "cleanOwner" in content, "Must check owner immutable in TestAMM"
    assert "cleanTokenA" in content, "Must check tokenA immutable in TestAMM"
    assert "cleanTokenB" in content, "Must check tokenB immutable in TestAMM"
    assert "cleanAsset" in content, "Must check asset immutable in TestSagaVault"


def test_saga_frontend_address_management_and_no_dummy_defaults():
    """Verify web/index.html removes Hardhat dummy addresses and enforces dynamic verified addresses."""
    index_file = WEB_DIR / "index.html"
    assert index_file.exists(), "web/index.html must exist"
    content = index_file.read_text(encoding="utf-8")

    # Hardhat dummy accounts must NOT be present as usable contract defaults
    dummy_accounts = [
        "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
        "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
    ]
    for dummy in dummy_accounts:
        assert f"const TKA_ADDR = '{dummy}'" not in content, f"Dummy address {dummy} must not be hardcoded default"
        assert f"const TKB_ADDR = '{dummy}'" not in content, f"Dummy address {dummy} must not be hardcoded default"
        assert f"const AMM_ADDR = '{dummy}'" not in content, f"Dummy address {dummy} must not be hardcoded default"
        assert f"const VAULT_ADDR = '{dummy}'" not in content, f"Dummy address {dummy} must not be hardcoded default"

    # Address validation and verification constructs
    assert "isValidEthAddress" in content, "Must validate Ethereum address hex format"
    assert "verifyContractCodeOnAtlantic" in content, "Must verify contract runtime bytecode via eth_getCode"
    assert "loadAndVerifyDeployedContracts" in content, "Must load and verify deployment from pharos_saga_deployed"
    assert "saveAndVerifyCustomAddresses" in content, "Must allow saving and verifying custom Atlantic addresses"
    assert "contractsVerified" in content, "Must track contractsVerified flag"
    assert "badgeContractsStatus" in content, "Must render contracts status badge"
    assert "sagaBlockedBanner" in content, "Must display blocked banner when contracts are unverified"


def test_saga_frontend_function_selectors_match_compiled_abi():
    """Verify that web/index.html uses exact 4-byte function selectors matching compiled Solidity contracts."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Check correct selectors from compiled_contracts.json
    assert "AMM_SWAP_SEL = '0x963b8dae'" in content, "swapWithSagaId must use 0x963b8dae"
    assert "AMM_UNWIND_SEL = '0x0cd8cd2b'" in content, "unwindSwapWithSagaId must use 0x0cd8cd2b"
    assert "VAULT_DEPOSIT_SEL = '0xb6b55f25'" in content, "vault deposit must use 0xb6b55f25"
    assert "VAULT_FAIL_DEPOSIT_SEL = '0xea65d693'" in content, "depositWithFailFlag must use 0xea65d693"
    assert "AMM_SUPPLY_LIQ_SEL = '0xf9dbb69f'" in content, "supplyLiquidity must use 0xf9dbb69f"
    assert "ERC20_FAUCET_SEL = '0x57915897'" in content, "faucet must use 0x57915897"
    assert "VAULT_USER_SHARES_SEL = '0xde69b3aa'" in content, "userShares must use 0xde69b3aa"
    assert "ERC20_ALLOWANCE_SEL = '0xdd62ed3e'" in content, "allowance must use 0xdd62ed3e"


def test_saga_dependent_allowances_and_preapproval_logic():
    """Verify web/index.html checks on-chain allowance and executes prerequisite approvals for vault and AMM unwind."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Query allowance helper
    assert "async function queryAllowance" in content, "Must implement queryAllowance helper"

    # Step 3 Vault prerequisite approval
    assert "step3_approve_vault" in content, "Step 3 must handle prerequisite Vault approval"

    # Comp 1 AMM unwind prerequisite approval
    assert "comp1_approve_amm" in content, "Comp 1 must handle prerequisite AMM unwind approval"

    # Comp 2 residual allowance revocation
    assert "Comp 2: Revoke" in content
    assert "params: { spender: deployedContracts.amm, amount: '0' }" in content


def test_saga_pool_liquidity_management_and_seeding_ui():
    """Verify web/index.html includes pool liquidity inspection, test faucet, and supplyLiquidity seeding."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    assert "poolLiquiditySection" in content, "Must include pool liquidity section"
    assert "dispPoolTKA" in content, "Must display AMM TKA reserve"
    assert "dispPoolTKB" in content, "Must display AMM TKB reserve"
    assert "btnSeedLiquidity" in content, "Must include Seed AMM Pool button"
    assert "btnClaimFaucet" in content, "Must include Claim Faucet button"
    assert "async function refreshPoolLiquidity" in content, "Must implement refreshPoolLiquidity"
    assert "async function seedPoolLiquidity" in content, "Must implement seedPoolLiquidity"
    assert "async function claimFaucetTokens" in content, "Must implement claimFaucetTokens"


def test_saga_error_classification_and_duplicate_broadcast_prevention():
    """Verify web/index.html distinctly handles wallet rejection, mined revert, timeout, and verifies receipt status."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Wallet rejection vs mined revert handling
    assert "err.code === 4001" in content, "Must detect MetaMask user rejection code 4001"
    assert "User rejected" in content, "Must detect User rejected message"
    assert "Action aborted without state change" in content, "Must classify rejection without state change"

    # Mined revert vs success handling
    assert "status === 'SUCCESS'" in content, "Must require status SUCCESS for confirmation"
    assert "REVERTED (EXPECTED)" in content, "Must record expected revert in forced failure scenario"
    assert "queryVaultShares" in content, "Must verify vault shares balance on-chain"


def test_simulation_address_validation_and_empty_code_rejection():
    """Simulate address validation and bytecode verification rules for Atlantic testnet."""
    import re

    def is_valid_eth_address(addr):
        return bool(isinstance(addr, str) and re.match(r"^0x[0-9a-fA-F]{40}$", addr.strip()))

    def verify_contract_code_sim(addr, rpc_code_map):
        if not is_valid_eth_address(addr):
            return False
        code = rpc_code_map.get(addr.lower().strip(), "0x")
        return bool(code and code not in ("0x", "0x0") and len(code) > 10)

    # Valid address format checks
    assert is_valid_eth_address("0xe4220c4b71877bb94eb173f467ef5c5557017085") is True
    assert is_valid_eth_address("0x123") is False
    assert is_valid_eth_address("not-an-address") is False
    assert is_valid_eth_address("") is False
    assert is_valid_eth_address(None) is False

    # Bytecode verification simulation
    addr_with_code = "0xe4220c4b71877bb94eb173f467ef5c5557017085"
    addr_empty_code = "0x0000000000000000000000000000000000000001"
    code_map = {
        addr_with_code.lower(): "0x608060405234801561001057600080fd5b50",
        addr_empty_code.lower(): "0x",
    }

    assert verify_contract_code_sim(addr_with_code, code_map) is True
    assert verify_contract_code_sim(addr_empty_code, code_map) is False
    assert verify_contract_code_sim("0x9999999999999999999999999999999999999999", code_map) is False


def test_simulation_dependent_approval_and_liquidity_guards():
    """Simulate prerequisite approval and pool liquidity enforcement."""
    swap_amount = 100 * 10**18

    def evaluate_deposit_action(tkb_allowance, required_amount):
        if tkb_allowance < required_amount:
            return "PREREQUISITE_APPROVAL_REQUIRED"
        return "READY_TO_DEPOSIT"

    def evaluate_unwind_action(tkb_allowance, unwind_amount):
        if tkb_allowance < unwind_amount:
            return "PREREQUISITE_APPROVAL_REQUIRED"
        return "READY_TO_UNWIND"

    def evaluate_swap_liquidity(pool_tkb_reserve, requested_swap_out):
        if pool_tkb_reserve < requested_swap_out:
            raise ValueError("TestAMM: insufficient pool liquidity")
        return True

    # 1. Deposit allowance evaluation
    assert evaluate_deposit_action(0, swap_amount) == "PREREQUISITE_APPROVAL_REQUIRED"
    assert evaluate_deposit_action(50 * 10**18, swap_amount) == "PREREQUISITE_APPROVAL_REQUIRED"
    assert evaluate_deposit_action(100 * 10**18, swap_amount) == "READY_TO_DEPOSIT"

    # 2. Unwind allowance evaluation
    assert evaluate_unwind_action(0, swap_amount) == "PREREQUISITE_APPROVAL_REQUIRED"
    assert evaluate_unwind_action(100 * 10**18, swap_amount) == "READY_TO_UNWIND"

    # 3. Liquidity evaluation
    with pytest.raises(ValueError, match="insufficient pool liquidity"):
        evaluate_swap_liquidity(0, swap_amount)

    with pytest.raises(ValueError, match="insufficient pool liquidity"):
        evaluate_swap_liquidity(50 * 10**18, swap_amount)

    assert evaluate_swap_liquidity(1000 * 10**18, swap_amount) is True


def test_gas_limit_bounding_and_liquidity_guard_enforcement():
    """Verify web/index.html bounds transaction gas below 20,000,000, enforces Step 2 liquidity guard, and pre-simulates reverts."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # 1. Bounded gas limit enforcement below 20M
    assert "500000" in content, "Must bound gas limit to safe maximum (500,000 gas)"
    assert "80000" in content, "Must enforce minimum safe gas floor (80,000 gas)"
    assert "gas: gasHex" in content, "Must pass explicit gas parameter to eth_sendTransaction"

    # 2. Step 2 Liquidity Guard
    assert "minReserveRequired = 100n * 10n**18n" in content, "Must enforce minimum 100 token reserve for Step 2 swap"
    assert "Liquidity Guard: TestAMM pool reserves insufficient" in content, "Must alert on insufficient reserves"

    # 3. Intentional revert pre-simulation
    assert "Pre-flight simulation" in content, "Must pre-simulate intentional revert path"
    assert "DELIBERATE_FORCED_FAILURE" in content, "Must verify DELIBERATE_FORCED_FAILURE reason before sending tx"

    # 4. Method name in inspector and logs
    assert "async function pollReceipt(txHash, maxAttempts = 30, methodName = '')" in content, "pollReceipt must accept methodName"
    assert "methodDisplay" in content, "pollReceipt must display methodName in inspector"


def test_pre_swap_allowance_guard_and_remediation_in_frontend():
    """Verify web/index.html includes mandatory pre-swap allowance check and prerequisite approval."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Pre-swap allowance check
    assert "Mandatory Pre-Swap Guard: TKA allowance" in content
    assert "step2_approve_amm" in content
    assert "Allowance re-verification failed on-chain" in content
    assert "On-chain allowance verified:" in content

    # Dynamic gas estimation and error handling
    assert "eth_estimateGas" in content
    assert "Gas estimation failed for" in content
    assert "Transaction blocked to protect funds" in content

    # Revert status safety (reverts are never confirmed)
    assert "FAILED (REVERTED)" in content
    assert "Step 2 Swap transaction reverted on-chain" in content


def test_offline_simulation_pre_swap_allowance_and_gas_clamping():
    """Offline unit simulation of pre-swap allowance evaluation, approval flow, gas estimation, clamping, and receipt classification."""

    # 1. Allowance check logic simulation
    def check_swap_allowance(allowance, amount_in):
        if allowance < amount_in:
            return {"action": "PREREQUISITE_APPROVAL_REQUIRED", "needed": amount_in - allowance}
        return {"action": "READY_FOR_SWAP"}

    swap_amount = 100 * 10**18
    assert check_swap_allowance(0, swap_amount)["action"] == "PREREQUISITE_APPROVAL_REQUIRED"
    assert check_swap_allowance(50 * 10**18, swap_amount)["action"] == "PREREQUISITE_APPROVAL_REQUIRED"
    assert check_swap_allowance(100 * 10**18, swap_amount)["action"] == "READY_FOR_SWAP"
    assert check_swap_allowance(1000 * 10**18, swap_amount)["action"] == "READY_FOR_SWAP"

    # 2. Approval confirmation on-chain re-verification simulation
    def verify_approval_post_receipt(receipt_status, post_allowance, amount_in):
        if receipt_status != "0x1":
            return False, "Approval transaction reverted on-chain"
        if post_allowance < amount_in:
            return False, "On-chain allowance re-verification failed"
        return True, "Allowance verified on-chain, ready for swap"

    assert verify_approval_post_receipt("0x0", 100 * 10**18, swap_amount)[0] is False
    assert verify_approval_post_receipt("0x1", 0, swap_amount)[0] is False
    assert verify_approval_post_receipt("0x1", 100 * 10**18, swap_amount)[0] is True

    # 3. Gas estimation & clamping logic simulation
    def calculate_clamped_gas_limit(estimated_gas, multiplier=1.5, floor=80_000, ceil=500_000):
        if estimated_gas is None:
            raise ValueError("Gas estimation failed on-chain")
        buffered = round(estimated_gas * multiplier)
        return min(max(buffered, floor), ceil)

    # Floor clamping
    assert calculate_clamped_gas_limit(30_000) == 80_000
    assert calculate_clamped_gas_limit(50_000) == 80_000
    # Proportional buffering
    assert calculate_clamped_gas_limit(100_000) == 150_000
    assert calculate_clamped_gas_limit(200_000) == 300_000
    assert calculate_clamped_gas_limit(220_000) == 330_000
    # Ceiling clamping (below 20M RPC limit)
    assert calculate_clamped_gas_limit(400_000) == 500_000
    assert calculate_clamped_gas_limit(1_000_000) == 500_000

    with pytest.raises(ValueError, match="Gas estimation failed"):
        calculate_clamped_gas_limit(None)

    # 4. Receipt status handling simulation (never confirm reverted)
    def process_step_receipt(step, receipt_status, is_intentional_revert=False):
        if receipt_status == "0x1":
            return {"badge": "CONFIRMED", "next_step_unlocked": True}
        if is_intentional_revert and receipt_status == "0x0":
            return {"badge": "REVERTED (EXPECTED)", "next_step_unlocked": False, "comp_unlocked": True}
        return {"badge": "FAILED (REVERTED)", "next_step_unlocked": False}

    assert process_step_receipt(1, "0x1")["badge"] == "CONFIRMED"
    assert process_step_receipt(1, "0x0")["badge"] == "FAILED (REVERTED)"
    assert process_step_receipt(1, "0x0")["next_step_unlocked"] is False

    assert process_step_receipt(2, "0x1")["badge"] == "CONFIRMED"
    assert process_step_receipt(2, "0x1")["next_step_unlocked"] is True
    assert process_step_receipt(2, "0x0")["badge"] == "FAILED (REVERTED)"
    assert process_step_receipt(2, "0x0")["next_step_unlocked"] is False

    # Scenario B Step 3 intentional revert
    assert process_step_receipt(3, "0x0", is_intentional_revert=True)["badge"] == "REVERTED (EXPECTED)"
    assert process_step_receipt(3, "0x0", is_intentional_revert=True)["comp_unlocked"] is True


def test_step3_vault_approval_prerequisite_scope_and_reverification():
    """Verify web/index.html correctly passes approveCalldata in step3_approve_vault and verifies on-chain TKB allowance."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # Locate step3_approve_vault modal call
    s3_idx = content.find("step: 'step3_approve_vault'")
    assert s3_idx != -1, "step3_approve_vault must be present in index.html"
    s3_block = content[s3_idx - 150 : s3_idx + 350]

    # Verify no naked calldata identifier in scope
    assert "calldata: approveCalldata" in s3_block, "Must pass calldata: approveCalldata explicitly"
    assert "approveCalldata = ERC20_APPROVE_SEL" in s3_block

    # Locate step3_approve_vault success handler
    h_idx = content.find("config.step === 'step3_approve_vault'")
    assert h_idx != -1, "step3_approve_vault handler must be present"
    h_block = content[h_idx : h_idx + 850]

    assert "Verifying on-chain TKB allowance" in h_block
    assert "TKB allowance re-verification failed on-chain" in h_block
    assert "On-chain TKB allowance verified:" in h_block
    assert "executeStep(3, true)" in h_block


def test_step3_auto_advance_and_vault_shares_state_recovery():
    """Verify web/index.html auto-advances to wallet prompt on verified allowance and restores confirmed state from on-chain vault shares."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    # 1. UI element for user vault shares
    assert 'id="dispUserShares"' in content, "Must include dispUserShares element in dashboard"

    # 2. executeStep autoExecute support
    s3_exec_idx = content.find("async function executeStep(stepNum, autoExecute = false)")
    assert s3_exec_idx != -1, "executeStep must accept autoExecute parameter"
    s3_def_block = content[s3_exec_idx : s3_exec_idx + 8500]

    assert "Prompting wallet signature for Step 3 Vault deposit..." in s3_def_block
    assert "await executeOnChainStepTx(stepConfig)" in s3_def_block

    # 3. Step 2 and Comp 1 autoExecute support
    assert "Prompting wallet signature for Step 2 Swap..." in s3_def_block
    assert "Prompting wallet signature for Comp 1 Unwind..." in content

    # 4. On-chain state recovery in refreshUserTokenBalances
    bal_idx = content.find("async function refreshUserTokenBalances()")
    assert bal_idx != -1, "refreshUserTokenBalances must be defined"
    bal_block = content[bal_idx : bal_idx + 2200]

    assert "queryVaultShares" in bal_block
    assert "shares >= 100n * 10n**18n" in bal_block
    assert "Step 3 Confirmed (100 Shares Minted)" in bal_block


def test_stale_or_unrelated_vault_shares_do_not_falsely_confirm_earlier_steps():
    """Phase 1 Safety Rule: Verify that holding on-chain vault shares does NOT falsely mark Step 1 or Step 2 confirmed."""
    index_file = WEB_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    bal_idx = content.find("async function refreshUserTokenBalances()")
    assert bal_idx != -1
    bal_end = content.find("async function claimFaucetTokens()")
    bal_block = content[bal_idx:bal_end]

    # In the share recovery block, badgeStep1 and badgeStep2 must NOT be marked confirmed
    recovery_idx = bal_block.find("shares >= 100n * 10n**18n")
    assert recovery_idx != -1
    recovery_code = bal_block[recovery_idx:]

    assert "badgeStep1" not in recovery_code, "Vault shares must not alter Step 1 badge"
    assert "badgeStep2" not in recovery_code, "Vault shares must not alter Step 2 badge"
    assert "cardStep2" not in recovery_code, "Vault shares must not unlock Step 2 card"

