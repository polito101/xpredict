"""
Spike 003: Automated WebSocket Test Client

Tests:
1. Connection + message receipt
2. End-to-end latency (publisher -> Redis -> server -> client)
3. Multi-client broadcast (5 clients on same market)
4. Auto-reconnect simulation
5. Burst backpressure (100 rapid messages)
6. Cross-market isolation

Run from xpredict/backend:
  uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_test.py

Requires: server running on :8099, publisher running or this script publishes its own
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from contextlib import asynccontextmanager

import redis
import websockets

SERVER_URL = "ws://localhost:8099/ws/prices/{market_id}"
REDIS_URL = "redis://localhost:6379/0"
CHANNEL_PREFIX = "prices:"


def publish_price(r: redis.Redis, market_id: str, yes_price: float, seq: int) -> float:
    ts = time.time()
    data = {
        "type": "price_update",
        "market_id": market_id,
        "yes_price": str(round(yes_price, 4)),
        "no_price": str(round(1 - yes_price, 4)),
        "volume_24h": "100000",
        "ts": ts,
        "seq": seq,
    }
    r.publish(f"{CHANNEL_PREFIX}{market_id}", json.dumps(data))
    return ts


@asynccontextmanager
async def ws_connect(market_id: str):
    url = SERVER_URL.format(market_id=market_id)
    async with websockets.connect(url) as ws:
        yield ws


async def test_1_basic_connection():
    """Test basic WebSocket connection and message receipt."""
    print("\n[TEST 1] Basic connection + message receipt")
    r = redis.from_url(REDIS_URL)

    async with ws_connect("test-001") as ws:
        await asyncio.sleep(0.5)

        publish_price(r, "test-001", 0.65, seq=0)
        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(msg)

        assert data["type"] == "price_update", f"Expected price_update, got {data['type']}"
        assert data["yes_price"] == "0.65", f"Expected 0.65, got {data['yes_price']}"
        assert data["no_price"] == "0.35", f"Expected 0.35, got {data['no_price']}"
        assert "_latency_ms" in data, "Missing _latency_ms field"

        print(f"  OK: Received price update, latency={data['_latency_ms']}ms")
        print("  PASS")


async def test_2_latency():
    """Measure end-to-end latency over 20 messages."""
    print("\n[TEST 2] End-to-end latency (20 messages)")
    r = redis.from_url(REDIS_URL)
    latencies = []

    async with ws_connect("test-002") as ws:
        await asyncio.sleep(0.5)

        for i in range(20):
            t0 = time.time()
            publish_price(r, "test-002", 0.5 + i * 0.01, seq=i)
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            t1 = time.time()
            data = json.loads(msg)
            e2e_ms = (t1 - t0) * 1000
            server_ms = data.get("_latency_ms", 0)
            latencies.append(e2e_ms)

        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        avg = statistics.mean(latencies)

        print(f"  End-to-end latency (ms):")
        print(f"    avg={avg:.1f}  p50={p50:.1f}  p95={p95:.1f}  p99={p99:.1f}")
        print(f"    min={min(latencies):.1f}  max={max(latencies):.1f}")

        assert p95 < 100, f"p95 latency {p95:.1f}ms exceeds 100ms threshold"
        assert avg < 50, f"avg latency {avg:.1f}ms exceeds 50ms threshold"
        print("  PASS (p95 < 100ms, avg < 50ms)")


async def test_3_multi_client():
    """Test 5 concurrent clients on same market all receive broadcast."""
    print("\n[TEST 3] Multi-client broadcast (5 clients)")
    r = redis.from_url(REDIS_URL)
    received = {i: [] for i in range(5)}

    async def client_loop(client_id: int, ws):
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                if data.get("type") == "price_update":
                    received[client_id].append(data["seq"])
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass

    clients = []
    for i in range(5):
        ws = await websockets.connect(SERVER_URL.format(market_id="test-003"))
        clients.append(ws)

    await asyncio.sleep(0.5)

    tasks = [asyncio.create_task(client_loop(i, ws)) for i, ws in enumerate(clients)]

    for seq in range(10):
        publish_price(r, "test-003", 0.5, seq=seq)
        await asyncio.sleep(0.1)

    await asyncio.sleep(1)

    for t in tasks:
        t.cancel()
    for ws in clients:
        await ws.close()

    for i in range(5):
        count = len(received[i])
        print(f"  Client {i}: received {count}/10 messages")
        assert count >= 8, f"Client {i} received only {count}/10 messages"

    print("  PASS (all clients received >=8/10)")


async def test_4_cross_market_isolation():
    """Ensure messages for market-A don't leak to market-B subscriber."""
    print("\n[TEST 4] Cross-market isolation")
    r = redis.from_url(REDIS_URL)

    async with ws_connect("test-004-a") as ws_a, ws_connect("test-004-b") as ws_b:
        await asyncio.sleep(0.5)

        publish_price(r, "test-004-a", 0.7, seq=0)
        publish_price(r, "test-004-b", 0.3, seq=1)

        msg_a = json.loads(await asyncio.wait_for(ws_a.recv(), timeout=5.0))
        msg_b = json.loads(await asyncio.wait_for(ws_b.recv(), timeout=5.0))

        assert msg_a["yes_price"] == "0.7", f"Market A got wrong price: {msg_a['yes_price']}"
        assert msg_b["yes_price"] == "0.3", f"Market B got wrong price: {msg_b['yes_price']}"

        # Verify no cross-leak: wait briefly, nothing should arrive
        try:
            extra = await asyncio.wait_for(ws_a.recv(), timeout=1.0)
            extra_data = json.loads(extra)
            if extra_data.get("type") == "price_update":
                assert False, f"Market A received cross-market message: {extra_data}"
        except asyncio.TimeoutError:
            pass  # Expected

        print("  Market A received only its own prices")
        print("  Market B received only its own prices")
        print("  No cross-market leakage detected")
        print("  PASS")


async def test_5_burst():
    """Burst 100 messages rapidly, verify all received."""
    print("\n[TEST 5] Burst backpressure (100 rapid messages)")
    r = redis.from_url(REDIS_URL)
    received_seqs = []

    async with ws_connect("test-005") as ws:
        await asyncio.sleep(0.5)

        t0 = time.time()
        for seq in range(100):
            publish_price(r, "test-005", 0.5, seq=seq)
        publish_elapsed = time.time() - t0

        # Collect all messages with a generous timeout
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                data = json.loads(msg)
                if data.get("type") == "price_update":
                    received_seqs.append(data["seq"])
        except asyncio.TimeoutError:
            pass

        total_elapsed = time.time() - t0
        received = len(received_seqs)
        dropped = 100 - received
        in_order = all(received_seqs[i] <= received_seqs[i + 1] for i in range(len(received_seqs) - 1))

        print(f"  Published 100 messages in {publish_elapsed * 1000:.1f}ms")
        print(f"  Received {received}/100 in {total_elapsed:.2f}s")
        print(f"  Dropped: {dropped}")
        print(f"  In order: {in_order}")

        assert received >= 95, f"Too many dropped messages: {dropped}/100"
        print("  PASS (>=95% delivery)")


async def test_6_reconnect_simulation():
    """Simulate disconnect and verify new connection works."""
    print("\n[TEST 6] Reconnect simulation")
    r = redis.from_url(REDIS_URL)

    # First connection
    ws1 = await websockets.connect(SERVER_URL.format(market_id="test-006"))
    await asyncio.sleep(0.3)
    publish_price(r, "test-006", 0.5, seq=0)
    msg1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=5.0))
    print(f"  Connection 1: received seq={msg1['seq']}")

    # Force disconnect
    await ws1.close()
    print("  Connection 1: closed")
    await asyncio.sleep(0.5)

    # Reconnect
    ws2 = await websockets.connect(SERVER_URL.format(market_id="test-006"))
    await asyncio.sleep(0.3)
    publish_price(r, "test-006", 0.6, seq=1)
    msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5.0))
    print(f"  Connection 2: received seq={msg2['seq']}")
    await ws2.close()

    assert msg2["seq"] == 1, f"Expected seq=1 after reconnect, got {msg2['seq']}"
    print("  PASS (reconnect receives new messages)")


async def main():
    print("=" * 60)
    print(" Spike 003: WebSocket Price Streaming - Test Suite")
    print("=" * 60)

    # Pre-flight checks
    r = redis.from_url(REDIS_URL)
    try:
        r.ping()
    except redis.ConnectionError:
        print("ERROR: Redis not available at localhost:6379")
        return

    try:
        async with websockets.connect(SERVER_URL.format(market_id="preflight")):
            pass
    except Exception as e:
        print(f"ERROR: Cannot connect to WS server at localhost:8099: {e}")
        return

    print("Pre-flight: Redis OK, WS server OK")

    results = {}
    tests = [
        ("basic_connection", test_1_basic_connection),
        ("latency", test_2_latency),
        ("multi_client", test_3_multi_client),
        ("cross_market_isolation", test_4_cross_market_isolation),
        ("burst", test_5_burst),
        ("reconnect", test_6_reconnect_simulation),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
            results[name] = "PASS"
        except Exception as e:
            print(f"  FAIL: {e}")
            results[name] = f"FAIL: {e}"

    print("\n" + "=" * 60)
    print(" RESULTS")
    print("=" * 60)
    for name, result in results.items():
        status = "PASS" if result == "PASS" else "FAIL"
        icon = "OK" if status == "PASS" else "XX"
        print(f"  [{icon}] {name}: {result}")

    passed = sum(1 for r in results.values() if r == "PASS")
    total = len(results)
    print(f"\n  {passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
