#!/usr/bin/env python3
"""
Independent On-Chain Deployment Verifier for Pharos Atlantic Testnet.
Verifies receipt status, gas used, runtime bytecode, and constructor relationship getters.
"""

import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from saga.client import PharosClient

client = PharosClient()

TOKEN_A_SEL = "0x0fc63d10"  # tokenA()
TOKEN_B_SEL = "0x5f64b55b"  # tokenB()
ASSET_SEL   = "0x38d52e0f"  # asset()
SYMBOL_SEL  = "0x95d89b41"  # symbol()
NAME_SEL    = "0x06fdde03"  # name()

def verify_tx(tx_hash: str):
    print(f"\n--- Verifying Transaction: {tx_hash} ---")
    receipt = client.rpc_call("eth_getTransactionReceipt", [tx_hash])
    if not receipt:
        print(f"Receipt not found yet for {tx_hash}")
        return None

    status = int(receipt.get("status", "0x0"), 16)
    contract_addr = receipt.get("contractAddress")
    block_num = int(receipt.get("blockNumber", "0x0"), 16)
    gas_used = int(receipt.get("gasUsed", "0x0"), 16)
    eff_gas_price = int(receipt.get("effectiveGasPrice", "0x2540be400"), 16)
    fee_wei = gas_used * eff_gas_price
    fee_phrs = fee_wei / 10**18

    print(f"Status: {'SUCCESS (0x1)' if status == 1 else 'FAILED (0x0)'}")
    print(f"Contract Address: {contract_addr}")
    print(f"Block Number: #{block_num}")
    print(f"Gas Used: {gas_used:,}")
    print(f"Effective Gas Price: {eff_gas_price / 1e9:.2f} Gwei")
    print(f"Actual Fee Paid: {fee_phrs:.6f} PHRS ({fee_wei} wei)")

    # Verify runtime code
    if contract_addr:
        code = client.rpc_call("eth_getCode", [contract_addr, "latest"])
        code_bytes = (len(code) - 2) // 2 if code.startswith("0x") else len(code) // 2
        print(f"Runtime Code on Atlantic: {code_bytes} bytes ({'VERIFIED' if code_bytes > 10 else 'EMPTY'})")

    return {
        "tx_hash": tx_hash,
        "contract_address": contract_addr,
        "block_number": block_num,
        "status": status,
        "gas_used": gas_used,
        "effective_gas_price": eff_gas_price,
        "fee_phrs": fee_phrs,
        "fee_wei": fee_wei
    }

def verify_amm_getters(amm_addr: str, exp_tka: str, exp_tkb: str):
    print(f"\n--- Verifying TestAMM Getters at {amm_addr} ---")
    res_a = client.rpc_call("eth_call", [{"to": amm_addr, "data": TOKEN_A_SEL}, "latest"])
    res_b = client.rpc_call("eth_call", [{"to": amm_addr, "data": TOKEN_B_SEL}, "latest"])
    act_tka = "0x" + res_a[-40:].lower()
    act_tkb = "0x" + res_b[-40:].lower()
    print(f"tokenA(): {act_tka} (Expected: {exp_tka.lower()}) -> {'PASS' if act_tka == exp_tka.lower() else 'FAIL'}")
    print(f"tokenB(): {act_tkb} (Expected: {exp_tkb.lower()}) -> {'PASS' if act_tkb == exp_tkb.lower() else 'FAIL'}")

def verify_vault_getter(vault_addr: str, exp_tkb: str):
    print(f"\n--- Verifying TestSagaVault Getter at {vault_addr} ---")
    res = client.rpc_call("eth_call", [{"to": vault_addr, "data": ASSET_SEL}, "latest"])
    act_asset = "0x" + res[-40:].lower()
    print(f"asset(): {act_asset} (Expected: {exp_tkb.lower()}) -> {'PASS' if act_asset == exp_tkb.lower() else 'FAIL'}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tx = sys.argv[1]
        verify_tx(tx)
    else:
        print("Usage: python verify_onchain_deployment.py <tx_hash>")
