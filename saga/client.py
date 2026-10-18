"""
Pharos Atlantic Testnet RPC & Simulation Client.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from saga.models import StepAction, TransactionReceipt
from saga.retry import PermanentError, TransientError

EXPECTED_CHAIN_ID = 688689
DEFAULT_RPC_URL = "https://atlantic.dplabs-internal.com"
DEFAULT_MCP_URL = "https://mcp.pharos.xyz/mcp"

# Baseline gas consumption for simulated actions
SIMULATED_GAS_TABLE = {
    StepAction.ERC20_APPROVE.value: 45000,
    StepAction.SWAP_EXACT_TOKENS.value: 115000,
    StepAction.VAULT_DEPOSIT.value: 85000,
    StepAction.ERC20_REVOKE_APPROVAL.value: 25000,
    StepAction.UNWIND_SWAP.value: 110000,
    StepAction.VAULT_WITHDRAW.value: 65000,
}


class PharosClient:
    """Client for querying Pharos Atlantic Testnet and generating deterministic sandbox receipts."""

    def __init__(
        self,
        rpc_url: str = DEFAULT_RPC_URL,
        mcp_url: str = DEFAULT_MCP_URL,
        simulate_only: bool = True,
        timeout: float = 8.0,
    ):
        self.rpc_url = rpc_url
        self.mcp_url = mcp_url
        self.simulate_only = simulate_only
        self.timeout = timeout
        self._mock_receipts: Dict[str, TransactionReceipt] = {}
        self._nonce_counter: int = 1

    def _rpc_call_urllib(self, method: str, params: list[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "PharosSagaExecutor/0.1.0"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            if "error" in res_json:
                raise TransientError(f"RPC Error: {res_json['error']}")
            return res_json.get("result")

    def _rpc_call_curl_fallback(self, method: str, params: list[Any]) -> Any:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        })
        cmd = [
            "curl.exe",
            "-s",
            "--max-time", str(int(self.timeout)),
            "-H", "Content-Type: application/json",
            "-d", payload,
            self.rpc_url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + 2)
        if proc.returncode != 0:
            raise TransientError(f"Curl fallback failed: {proc.stderr}")
        res_json = json.loads(proc.stdout)
        if "error" in res_json:
            raise TransientError(f"RPC Error: {res_json['error']}")
        return res_json.get("result")

    def rpc_call(self, method: str, params: Optional[list[Any]] = None) -> Any:
        """Execute read-only JSON-RPC request with curl fallback on Windows network resolution errors."""
        params = params or []
        try:
            return self._rpc_call_urllib(method, params)
        except (urllib.error.URLError, TimeoutError, OSError):
            # Attempt curl fallback which often resolves IPv4/IPv6 dual stack cleanly
            try:
                return self._rpc_call_curl_fallback(method, params)
            except Exception as e:
                raise TransientError(f"Failed to query Pharos RPC ({self.rpc_url}): {e}")

    def get_chain_id(self) -> int:
        """Fetch chain ID from RPC and verify it matches Atlantic Testnet (688689)."""
        result = self.rpc_call("eth_chainId")
        chain_id = int(result, 16)
        if chain_id != EXPECTED_CHAIN_ID:
            raise PermanentError(
                f"Security guardrail tripped: Connected chain ID {chain_id} does not match "
                f"Atlantic Testnet ({EXPECTED_CHAIN_ID}). Execution halted."
            )
        return chain_id

    def get_block_number(self) -> int:
        """Fetch current block height."""
        result = self.rpc_call("eth_blockNumber")
        return int(result, 16)

    def get_gas_price(self) -> int:
        """Fetch current gas price in Wei."""
        result = self.rpc_call("eth_gasPrice")
        return int(result, 16)

    def generate_simulated_receipt(
        self,
        action: str,
        contract: str,
        block_number: int,
        revert: bool = False,
        simulated_error: Optional[str] = None,
    ) -> TransactionReceipt:
        """
        Generate a deterministic synthetic transaction receipt for safe sandbox execution.
        Receipt hash is explicitly prefixed with 0xsim_ to prevent confusion with real on-chain hashes.
        """
        raw_hash = hashlib.sha256(
            f"{action}:{contract}:{block_number}:{self._nonce_counter}:{time.time()}".encode("utf-8")
        ).hexdigest()
        self._nonce_counter += 1

        tx_hash = f"0xsim_{raw_hash[:36]}"
        gas_used = SIMULATED_GAS_TABLE.get(action, 60000)
        status = 0 if revert else 1

        receipt = TransactionReceipt(
            tx_hash=tx_hash,
            status=status,
            block_number=block_number,
            gas_used=gas_used,
            cumulative_gas_used=gas_used,
            effective_gas_price_wei=10_000_000_000,  # 10 Gwei
            logs=[
                {
                    "address": contract,
                    "event": f"{action}_EXECUTED",
                    "status": "REVERTED" if revert else "SUCCESS",
                    "note": simulated_error or "Simulated log emission",
                }
            ],
            is_simulated=True,
            simulated_note=simulated_error or "Simulated sandbox execution (zero gas cost)",
        )
        self._mock_receipts[tx_hash] = receipt
        return receipt

    def poll_receipt(self, tx_hash: str, timeout: float = 5.0) -> TransactionReceipt:
        """
        Poll and verify receipt existence and status.
        In simulation mode, verifies stored synthetic receipt.
        """
        if tx_hash in self._mock_receipts:
            receipt = self._mock_receipts[tx_hash]
            if receipt.status != 1:
                raise PermanentError(
                    f"Receipt barrier failed for {tx_hash}: execution reverted (status={receipt.status})."
                )
            return receipt

        # If checking a real transaction (when not in local mock table)
        if not self.simulate_only:
            start_time = time.time()
            while time.time() - start_time < timeout:
                res = self.rpc_call("eth_getTransactionReceipt", [tx_hash])
                if res:
                    status = int(res.get("status", "0x0"), 16)
                    receipt = TransactionReceipt(
                        tx_hash=tx_hash,
                        status=status,
                        block_number=int(res.get("blockNumber", "0x0"), 16),
                        gas_used=int(res.get("gasUsed", "0x0"), 16),
                        cumulative_gas_used=int(res.get("cumulativeGasUsed", "0x0"), 16),
                        effective_gas_price_wei=int(res.get("effectiveGasPrice", "0x0"), 16),
                        logs=res.get("logs", []),
                        is_simulated=False,
                        simulated_note=None,
                    )
                    if receipt.status != 1:
                        raise PermanentError(f"On-chain transaction reverted for {tx_hash}.")
                    return receipt
                time.sleep(0.5)

        raise PermanentError(f"Transaction receipt not found or expired for hash {tx_hash}.")
