"""
Validation tests for Pharos SkillEngine v0.1.0 specification adherence.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_skill_manifest_exists_and_valid():
    skill_file = REPO_ROOT / "SKILL.md"
    assert skill_file.exists(), "SKILL.md is missing from root"
    content = skill_file.read_text(encoding="utf-8")

    # Verify YAML frontmatter fields
    assert "name: pharos-saga-executor" in content
    assert "chain_id: 688689" in content
    assert "standard: Pharos SkillEngine v0.1.0" in content
    assert "## Capability Index" in content
    assert "## Safety Boundary" in content


def test_networks_asset_valid():
    networks_file = REPO_ROOT / "assets" / "networks.json"
    assert networks_file.exists(), "assets/networks.json missing"
    data = json.loads(networks_file.read_text(encoding="utf-8"))

    assert "networks" in data
    assert "atlantic" in data["networks"]
    atlantic = data["networks"]["atlantic"]
    assert atlantic["chain_id"] == 688689
    assert atlantic["is_testnet"] is True
    assert "dplabs-internal.com" in atlantic["rpc_url"]


def test_tokens_asset_valid():
    tokens_file = REPO_ROOT / "assets" / "tokens.json"
    assert tokens_file.exists(), "assets/tokens.json missing"
    data = json.loads(tokens_file.read_text(encoding="utf-8"))

    assert data["chain_id"] == 688689
    tokens = data["tokens"]
    assert "USDC" in tokens
    assert tokens["USDC"]["address"] == "0xcfC8330f4BCAB529c625D12781b1C19466A9Fc8B"
    assert tokens["USDC"]["decimals"] == 6
    assert "WPHRS" in tokens


def test_saga_definition_valid():
    saga_file = REPO_ROOT / "assets" / "sagas" / "approve_swap_deposit.json"
    assert saga_file.exists(), "approve_swap_deposit.json missing"
    data = json.loads(saga_file.read_text(encoding="utf-8"))

    assert data["saga_id"] == "approve_swap_deposit_v1"
    assert data["chain_id"] == 688689
    steps = data["steps"]
    assert len(steps) == 3
    assert steps[0]["action"] == "ERC20_APPROVE"
    assert steps[1]["action"] == "SWAP_EXACT_TOKENS"
    assert steps[2]["action"] == "VAULT_DEPOSIT"


def test_reference_docs_exist():
    ref_file = REPO_ROOT / "references" / "saga.md"
    assert ref_file.exists(), "references/saga.md missing"
    content = ref_file.read_text(encoding="utf-8")

    assert "## 1. Overview" in content
    assert "## 2. CLI Command Interfaces" in content
    assert "## 3. Output Schema & State Enums" in content
    assert "## 4. Error Codes & Recovery Matrix" in content
