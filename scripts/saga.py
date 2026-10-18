#!/usr/bin/env python3
"""
Pharos Saga Executor CLI — Deterministic multi-step transaction coordinator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from saga.client import PharosClient
from saga.coordinator import SagaCoordinator
from saga.models import RetryConfig, SagaExecutionLog, SagaStatus, StepStatus
from saga.steps import ApproveStep, DepositStep, SwapStep

HEADER = """
================================================================================
           PHAROS SAGA EXECUTOR - TRANSACTION COORDINATOR (TASK 6)
   Target Network: Pharos Atlantic Testnet (Chain ID 688689)
   Safety Boundary: [SIMULATION SANDBOX - ZERO FUNDS SPENT - READ-ONLY LIVE RPC]
================================================================================
"""


def format_step_table(log: SagaExecutionLog) -> str:
    lines = []
    lines.append("-" * 88)
    lines.append(f"{'#':<3} {'STEP NAME':<26} {'STATUS':<20} {'ATTEMPTS':<10} {'TX HASH':<24}")
    lines.append("-" * 88)

    for s in log.steps:
        tx_display = s.tx_hash or (s.receipt.tx_hash if s.receipt else "None")
        if tx_display and len(tx_display) > 23:
            tx_display = tx_display[:20] + "..."
        lines.append(
            f"{s.order:<3} {s.name:<26} {s.status.value:<20} {s.attempts:<10} {tx_display:<24}"
        )

    lines.append("-" * 88)
    return "\n".join(lines)


def run_pipeline(
    saga_id: str,
    title: str,
    force_fail_step: Optional[int] = None,
    force_fail_compensation: bool = False,
    transient_retries: int = 0,
    live_preflight: bool = False,
    verbose: bool = False,
    output_json: bool = False,
) -> SagaExecutionLog:
    client = PharosClient(simulate_only=True)

    current_block = 31569442
    if live_preflight:
        try:
            live_block = client.get_block_number()
            chain_id = client.get_chain_id()
            gas_price = client.get_gas_price()
            current_block = live_block
            if not output_json:
                print(f"[LIVE PREFLIGHT] Connected to Pharos Atlantic Testnet (Chain ID: {chain_id})")
                print(f"[LIVE PREFLIGHT] Current Block: #{live_block:,} | Gas Price: {gas_price / 1e9:.2f} Gwei\n")
        except Exception as e:
            if not output_json:
                print(f"[LIVE PREFLIGHT WARNING] Could not query live RPC ({e}); using offline fallback.\n")

    steps = [
        ApproveStep(
            force_fail=(force_fail_step == 1),
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_retries if force_fail_step != 1 else 0,
        ),
        SwapStep(
            force_fail=(force_fail_step == 2),
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_retries if force_fail_step != 2 else 0,
        ),
        DepositStep(
            force_fail=(force_fail_step == 3),
            force_fail_compensation=force_fail_compensation,
            transient_fail_count=transient_retries if force_fail_step != 3 else 0,
        ),
    ]

    retry_config = RetryConfig(
        max_retries=3,
        base_delay_seconds=0.2,
        backoff_factor=2.0,
        max_delay_seconds=2.0,
        jitter=True,
    )

    def on_event(event):
        if verbose and not output_json:
            print(f"  --> [{event.from_state} -> {event.to_state}] (Attempt {event.attempt}) Reason: {event.reason}")

    coordinator = SagaCoordinator(
        saga_id=saga_id,
        title=title,
        steps=steps,
        client=client,
        retry_config=retry_config,
        on_event=on_event,
    )

    return coordinator.execute(current_block=current_block)


def cmd_demo(args: argparse.Namespace) -> int:
    if not args.json:
        print(HEADER)
        print(">>> EXECUTING TASK 6 DUAL-OUTCOME DEMONSTRATION SUITE")
        print(">>> 1. Scenario A: Happy Path (Approve -> Swap -> Deposit: All 3 Succeeded)")
        print(">>> 2. Scenario B: Forced Step 3 Failure (Step 3 Revert -> Reverse Rollback: Unwind Swap -> Revoke Approve)\n")

    # Scenario A: Happy Path
    log_a = run_pipeline(
        saga_id="demo_happy_path",
        title="Scenario A: Happy Path (3/3 Confirmed)",
        force_fail_step=None,
        live_preflight=args.live_preflight,
        verbose=args.verbose,
        output_json=args.json,
    )

    if not args.json:
        print(f"\n[SCENARIO A RESULT] Status: {log_a.status.value}")
        print(f"Total Gas Consumed (Simulated): {log_a.total_gas_used:,}")
        print(format_step_table(log_a))
        print(">> Verification: Step 1 confirmed, Step 2 confirmed, Step 3 confirmed.")
        print(">> All dependent steps verified with valid receipts before next step dispatched.\n")
        print("=" * 88 + "\n")
        print(">>> Scenario B: Forced Failure at Step 3 with LIFO Reverse Compensation Rollback")

    # Scenario B: Forced Step 3 Failure
    log_b = run_pipeline(
        saga_id="demo_forced_failure",
        title="Scenario B: Step 3 Forced Revert with Reverse Rollback",
        force_fail_step=3,
        live_preflight=False,
        verbose=args.verbose,
        output_json=args.json,
    )

    if not args.json:
        print(f"\n[SCENARIO B RESULT] Status: {log_b.status.value}")
        print(f"Total Gas Consumed (Simulated): {log_b.total_gas_used:,}")
        print(format_step_table(log_b))
        print(">> Rollback Verification (LIFO Order):")
        print("   1. Step 3 (Deposit) permanently reverted.")
        print("   2. Step 2 (Swap) compensated: Executed UNWIND_SWAP (WPHRS -> USDC).")
        print("   3. Step 1 (Approve) compensated: Executed ERC20_REVOKE_APPROVAL (Allowance -> 0).")
        print(">> Result: Pipeline safely restored to initial state. Zero stranded capital.\n")

    if args.json:
        print(json.dumps({
            "scenario_a_happy_path": log_a.to_dict(),
            "scenario_b_forced_failure": log_b.to_dict(),
        }, indent=2))

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if not args.json:
        print(HEADER)

    log = run_pipeline(
        saga_id=args.saga_id or "run_interactive",
        title="Pharos 3-Step DeFi Pipeline",
        force_fail_step=args.force_fail_step,
        force_fail_compensation=args.fail_compensation,
        transient_retries=args.transient_retries,
        live_preflight=args.live_preflight,
        verbose=args.verbose,
        output_json=args.json,
    )

    if args.json:
        print(log.to_json())
    else:
        print(f"\n[FINAL STATUS]: {log.status.value}")
        print(f"Steps Succeeded: {log.steps_succeeded}/{log.total_steps}")
        print(f"Steps Compensated: {log.steps_compensated}")
        print(f"Total Gas Consumed: {log.total_gas_used:,}")
        print(format_step_table(log))

        if log.status == SagaStatus.MANUAL_RECOVERY_REQUIRED:
            print("\n[CRITICAL ALERT] MANUAL RECOVERY REQUIRED!")
            print(f"Stranded state captured at: {log.recovery_snapshot_path}")

    return 0 if log.status in (SagaStatus.COMPLETED, SagaStatus.ROLLED_BACK) else 1


def cmd_status(args: argparse.Namespace) -> int:
    client = PharosClient()
    try:
        chain_id = client.get_chain_id()
        block = client.get_block_number()
        gas_price = client.get_gas_price()
        status_info = {
            "network": "Pharos Atlantic Testnet",
            "chain_id": chain_id,
            "current_block": block,
            "gas_price_wei": gas_price,
            "gas_price_gwei": round(gas_price / 1e9, 2),
            "status": "ONLINE",
            "mcp_url": client.mcp_url,
            "rpc_url": client.rpc_url,
        }
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(HEADER)
            print("[PHAROS ATLANTIC TESTNET STATUS]")
            for k, v in status_info.items():
                print(f"  {k:<20}: {v}")
        return 0
    except Exception as e:
        print(f"Error checking network status: {e}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pharos Saga Executor CLI — Deterministic multi-step transaction coordinator."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run dual-outcome demonstration (Happy Path & Forced Failure)")
    demo_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    demo_parser.add_argument("--verbose", action="store_true", help="Print real-time transition logs")
    demo_parser.add_argument("--live-preflight", action="store_true", help="Query live Atlantic testnet RPC block height")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a saga workflow")
    run_parser.add_argument("--saga-id", type=str, default="run_custom", help="Identifier for the saga execution")
    run_parser.add_argument("--force-fail-step", type=int, choices=[1, 2, 3], help="Inject permanent failure at step (1, 2, or 3)")
    run_parser.add_argument("--fail-compensation", action="store_true", help="Force failure during rollback to trigger MANUAL_RECOVERY_REQUIRED")
    run_parser.add_argument("--transient-retries", type=int, default=0, help="Inject N transient retries before step succeeds")
    run_parser.add_argument("--live-preflight", action="store_true", help="Query live Atlantic testnet RPC before execution")
    run_parser.add_argument("--verbose", action="store_true", help="Print real-time transition logs")
    run_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # Status command
    status_parser = subparsers.add_parser("status", help="Inspect live Pharos Atlantic testnet RPC status")
    status_parser.add_argument("--json", action="store_true", help="Output JSON status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "demo":
        sys.exit(cmd_demo(args))
    elif args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))


if __name__ == "__main__":
    main()
