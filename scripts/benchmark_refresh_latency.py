"""
Repeatable benchmark comparing old sequential RPC balance refresh vs new concurrent Promise.allSettled refresh.
Target: Pharos Atlantic Testnet RPC (https://atlantic.dplabs-internal.com)
"""

import time
import httpx
import asyncio

RPC_URL = "https://atlantic.dplabs-internal.com"
ACCOUNT = "0xe4220c4b71877bb94eb173f467ef5c5557017085"
WPHRS = "0x838800b758277CC111B2d48Ab01e5E164f8E9471"
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

def pad_addr(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")

def make_req(method: str, params: list, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

# Old baseline: 5 serial calls including Permit2 allowance
old_calls = [
    make_req("eth_blockNumber", []),
    make_req("eth_gasPrice", []),
    make_req("eth_getBalance", [ACCOUNT, "latest"]),
    make_req("eth_call", [{"to": WPHRS, "data": "0x70a08231" + pad_addr(ACCOUNT)}, "latest"]),
    make_req("eth_call", [{"to": WPHRS, "data": "0xdd62ed3e" + pad_addr(ACCOUNT) + pad_addr(PERMIT2)}, "latest"])
]

# New baseline: 4 concurrent calls without Permit2
new_calls = [
    make_req("eth_blockNumber", []),
    make_req("eth_gasPrice", []),
    make_req("eth_getBalance", [ACCOUNT, "latest"]),
    make_req("eth_call", [{"to": WPHRS, "data": "0x70a08231" + pad_addr(ACCOUNT)}, "latest"])
]

def benchmark_sequential_round(client: httpx.Client) -> float:
    t0 = time.perf_counter()
    for c in old_calls:
        resp = client.post(RPC_URL, json=c)
        resp.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0

async def benchmark_concurrent_round(client: httpx.AsyncClient) -> float:
    t0 = time.perf_counter()
    tasks = [client.post(RPC_URL, json=c) for c in new_calls]
    responses = await asyncio.gather(*tasks)
    for r in responses:
        r.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0

async def main():
    print("=== Pharos Saga Executor: RPC Refresh Latency Benchmark ===")
    print(f"Target RPC: {RPC_URL}")
    print(f"Account: {ACCOUNT}")
    print(f"WPHRS: {WPHRS}\n")

    iterations = 3
    seq_times = []
    conc_times = []

    with httpx.Client(timeout=15) as sync_client:
        for i in range(iterations):
            dt = benchmark_sequential_round(sync_client)
            seq_times.append(dt)
            print(f"Round {i+1} - Old Sequential (5 serial calls): {dt:.1f} ms")
            time.sleep(0.5)

    print()
    async with httpx.AsyncClient(timeout=15) as async_client:
        for i in range(iterations):
            dt = await benchmark_concurrent_round(async_client)
            conc_times.append(dt)
            print(f"Round {i+1} - New Concurrent (4 parallel calls): {dt:.1f} ms")
            time.sleep(0.5)

    avg_seq = sum(seq_times) / len(seq_times)
    avg_conc = sum(conc_times) / len(conc_times)
    delta_ms = avg_seq - avg_conc

    print("\n--- Summary Results ---")
    print(f"Old Sequential Mean: {avg_seq:.1f} ms (min: {min(seq_times):.1f} ms, max: {max(seq_times):.1f} ms)")
    print(f"New Concurrent Mean: {avg_conc:.1f} ms (min: {min(conc_times):.1f} ms, max: {max(conc_times):.1f} ms)")
    print(f"Average Wall-Clock Reduction: {delta_ms:.1f} ms ({(delta_ms/avg_seq)*100:.1f}% reduction)")

if __name__ == "__main__":
    asyncio.run(main())
