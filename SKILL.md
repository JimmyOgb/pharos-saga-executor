---
name: pharos-saga-executor
version: 0.1.0
description: Deterministic multi-step transaction coordinator with bounded retry policy, reverse-order compensation, and state machine auditability on Pharos Network.
author: JimmyOgb
license: MIT
network: atlantic
chain_id: 688689
standard: Pharos SkillEngine v0.1.0
---

# Pharos Saga Executor (`pharos-saga-executor`)

Deterministic multi-step transaction coordinator enforcing receipt verification barriers, bounded exponential backoff retries, and reverse LIFO compensation rollback on Pharos Network.

## Prerequisites

1. **Python Runtime**: Python `>= 3.9` (Zero third-party runtime dependencies required).
2. **Network Access**: HTTP connection to Pharos Atlantic Testnet JSON-RPC (`https://atlantic.dplabs-internal.com`) or Pharos Hosted MCP (`https://mcp.pharos.xyz/mcp`).
3. **Safety Guarantee**: Operates in simulation-first mode by default (`0xsim_...`). Zero private keys requested, stored, or broadcast.

---

## Network Configuration

| Parameter | Atlantic Testnet (Primary) | Pacific Mainnet (Restricted) |
|---|---|---|
| **Chain ID** | `688689` (`0xa8231`) | `688688` (`0xa8230`) |
| **JSON-RPC Endpoint** | `https://atlantic.dplabs-internal.com` | `https://pacific.dplabs-internal.com` |
| **Hosted Chain MCP** | `https://mcp.pharos.xyz/mcp` | N/A |
| **Block Explorer** | `https://atlantic.pharosscan.xyz` | `https://pharosscan.xyz` |
| **Native Currency** | `PHRS` (18 decimals) | `PHRS` (18 decimals) |
| **Execution Permission** | Allowed (Simulation & Read-Only) | Blocked (Fail-Closed) |

---

## Capability Index

| Capability | Command | Description |
|---|---|---|
| **Demo Suite** | `python scripts/saga.py demo` | Runs Happy Path (3/3 confirmed) and Forced Step 3 Failure (with LIFO rollback) side-by-side. |
| **Single Run** | `python scripts/saga.py run` | Executes a configurable saga pipeline with receipt barriers and backoff retries. |
| **Failure Injection** | `python scripts/saga.py run --force-fail-step 3` | Injects a deterministic failure at Step 1, 2, or 3 to test rollback resilience. |
| **Manual Recovery** | `python scripts/saga.py run --force-fail-step 3 --fail-compensation` | Tests critical handling when compensation fails (`MANUAL_RECOVERY_REQUIRED`). |
| **Interactive UI** | `python scripts/saga_server.py` | Launches local REST/SSE server and interactive browser DAG visualizer. |
| **Live Preflight** | `python scripts/saga.py run --live-preflight` | Inspects real block height and gas price on Atlantic Testnet before dispatch. |

---

## Safety Boundary & Write Pre-checks

Before any state transition is attempted:
1. **Network Guardrail**: Verifies network matches Atlantic Testnet (`688689`). Fails closed on Pacific Mainnet or unexpected chain IDs.
2. **Key Protection**: Disallows private key inputs. All simulated transactions produce traceable synthetic receipts prefixed with `0xsim_` and labelled `[SIMULATED]`.
3. **Receipt Barrier**: Every step requires confirmed execution (`status == 1`) before dependent successor steps are dispatched.
4. **Compensation Safety**: If a compensation step fails, execution halts and creates `saga-recovery-snapshot-<timestamp>.json` rather than continuing in an corrupted state.

---

## Skill Files & Manifest

- `SKILL.md`: Main entrypoint and capability index.
- `assets/networks.json`: Network RPC, MCP, and explorer definitions.
- `assets/tokens.json`: Verified Atlantic testnet ERC-20 tokens and protocol adapters.
- `assets/sagas/approve_swap_deposit.json`: Canonical 3-step saga specification.
- `references/saga.md`: Command specifications, output schemas, and error recovery matrices.
- `saga/`: Core Python saga engine.
- `scripts/`: Production CLI and visualizer server scripts.
- `web/`: Zero-cost interactive DAG visualizer.
- `tests/`: Automated test suite (35+ unit and integration tests).
