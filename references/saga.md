# Pharos Saga Executor — Skill Reference & Command Specification

**Skill ID**: `pharos-saga-executor`
**Version**: `0.1.0`
**Network**: Pharos Atlantic Testnet (`Chain ID: 688689`)
**Standard**: Pharos SkillEngine v0.1.0

---

## 1. Overview

The `pharos-saga-executor` coordinates multi-step dependent on-chain transaction sequences on Pharos Network. It mitigates partial execution risk and unattended stranded capital by enforcing:
1. **Pre-flight dependency verification**: Ensuring prior steps succeeded with confirmed on-chain receipts before dispatching child steps.
2. **Bounded exponential backoff retries**: Handling transient RPC errors, network drops, and gas spikes with random jitter.
3. **Strict LIFO compensation rollbacks**: Unwinding completed steps in exact reverse order when a permanent failure occurs.
4. **Manual Recovery Safeguard**: Trapping and capturing stranded states in an emergency snapshot if a compensating action fails (`MANUAL_RECOVERY_REQUIRED`).
5. **Fail-Closed Security**: Disallowing execution upon malformed receipts, configuration inconsistencies, or untrusted network endpoints.

---

## 2. CLI Command Interfaces

### 2.1 Demo Suite (`saga demo`)
Executes the dual-outcome demonstration required by Pharos Agent Arena Task 6:
- **Scenario A (Happy Path)**: Sequential 3/3 confirmation (`approve -> swap -> deposit`).
- **Scenario B (Forced Failure)**: Injected Step 3 revert triggering reverse LIFO compensation (`unwind swap -> revoke allowance`).

```bash
python scripts/saga.py demo [--json] [--verbose]
```

### 2.2 Workflow Execution (`saga run`)
Runs a single workflow pass with optional failure injection for testing resilience:

```bash
python scripts/saga.py run [--saga assets/sagas/approve_swap_deposit.json] \
                           [--force-fail-step {1,2,3}] \
                           [--fail-compensation] \
                           [--simulate] \
                           [--json] \
                           [--max-retries 3]
```

### 2.3 Interactive DAG Visualizer (`saga server`)
Starts the zero-dependency local REST/SSE server powering the interactive web visualizer:

```bash
python scripts/saga_server.py [--port 8080] [--host 127.0.0.1]
```

---

## 3. Output Schema & State Enums

### 3.1 Saga Status Enums
- `INITIALIZED`: Pipeline initialized, prerequisites verified.
- `EXECUTING`: Forward transaction steps in progress.
- `COMPLETED`: All dependent steps confirmed via transaction receipts.
- `COMPENSATING`: Reversible failure encountered; LIFO rollback underway.
- `ROLLED_BACK`: All prior steps successfully unwound in reverse order.
- `MANUAL_RECOVERY_REQUIRED`: A compensating step failed; assets stranded; emergency snapshot dumped.
- `ABORTED`: Pipeline aborted before state changes occurred.

### 3.2 Step Status Enums
- `PENDING`: Step queued, awaiting prerequisite confirmation.
- `EXECUTING`: Transaction submitted, polling receipt barrier.
- `CONFIRMED`: Receipt confirmed on-chain (`status == 1`).
- `RETRIED`: Transient failure encountered, retry attempt scheduled.
- `FAILED`: Permanent failure or max retries exceeded.
- `COMPENSATING`: Compensation transaction executing.
- `COMPENSATED`: Prior action unwound successfully.
- `COMPENSATION_FAILED`: Rollback failed; human intervention required.

### 3.3 JSON Trace Schema
```json
{
  "saga_id": "approve_swap_deposit_v1",
  "status": "COMPLETED",
  "started_at": "2026-10-18T10:30:00Z",
  "completed_at": "2026-10-18T10:30:04Z",
  "total_gas_used": 147520,
  "steps_total": 3,
  "steps_succeeded": 3,
  "steps_compensated": 0,
  "state_history": [
    { "timestamp": "...", "state": "INITIALIZED", "details": "..." },
    { "timestamp": "...", "state": "EXECUTING", "step_id": "step_1_approve" }
  ],
  "steps": [
    {
      "step_id": "step_1_approve",
      "status": "CONFIRMED",
      "attempts": 1,
      "tx_hash": "0xsim_...",
      "receipt": { "status": 1, "block_number": 31569442, "gas_used": 45000 }
    }
  ]
}
```

---

## 4. Error Codes & Recovery Matrix

| Code | Type | Action | Engine Response |
|---|---|---|---|
| `TIMEOUT` | Transient | Retry with backoff | Sleep $base \times 2^{attempt} + jitter$, retry up to `max_retries` |
| `RATE_LIMIT_429` | Transient | Retry with backoff | Exponential backoff pause, then retry |
| `NETWORK_ERROR` | Transient | Retry with backoff | Bounded reconnect attempt |
| `INSUFFICIENT_FUNDS` | Permanent | Abort / Rollback | Halt immediately; initiate LIFO compensation of completed steps |
| `CONTRACT_REVERT` | Permanent | Rollback | Halt forward execution; trigger reverse compensation |
| `COMPENSATION_REVERT` | Critical | Lock State | Transition to `MANUAL_RECOVERY_REQUIRED`, dump `recovery-snapshot.json` |
