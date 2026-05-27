"""
Spike 003: Price Update Publisher (simulates Celery task)

Publishes fake price updates to Redis pub/sub channels.
Simulates what a Celery Beat task would do when polling Polymarket
or when an admin edits house market odds.

Run from xpredict/backend:
  uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_publisher.py

Modes:
  --burst     Publish 100 updates in rapid succession (backpressure test)
  --multi     Publish to 5 different markets simultaneously
  (default)   Publish to market-001 every 1-3 seconds
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time

import redis

REDIS_URL = "redis://localhost:6379/0"
CHANNEL_PREFIX = "prices:"


def make_price_update(market_id: str, yes_price: float) -> dict:
    no_price = round(1.0 - yes_price, 4)
    return {
        "type": "price_update",
        "market_id": market_id,
        "yes_price": str(round(yes_price, 4)),
        "no_price": str(round(no_price, 4)),
        "volume_24h": str(round(random.uniform(10000, 500000), 2)),
        "ts": time.time(),
    }


def publish_steady(r: redis.Redis, market_id: str = "market-001") -> None:
    price = 0.5
    seq = 0
    print(f"Publishing to {CHANNEL_PREFIX}{market_id} every 1-3s (Ctrl+C to stop)")
    try:
        while True:
            drift = random.uniform(-0.05, 0.05)
            price = max(0.01, min(0.99, price + drift))
            data = make_price_update(market_id, price)
            data["seq"] = seq

            channel = f"{CHANNEL_PREFIX}{market_id}"
            listeners = r.publish(channel, json.dumps(data))
            print(
                f"  [{seq:04d}] {channel} -> YES={data['yes_price']} "
                f"NO={data['no_price']} (listeners={listeners})"
            )
            seq += 1
            time.sleep(random.uniform(1.0, 3.0))
    except KeyboardInterrupt:
        print(f"\nStopped after {seq} messages")


def publish_burst(r: redis.Redis, market_id: str = "market-001", count: int = 100) -> None:
    print(f"Burst: {count} messages to {CHANNEL_PREFIX}{market_id}")
    price = 0.5
    t0 = time.time()
    for seq in range(count):
        drift = random.uniform(-0.03, 0.03)
        price = max(0.01, min(0.99, price + drift))
        data = make_price_update(market_id, price)
        data["seq"] = seq
        r.publish(f"{CHANNEL_PREFIX}{market_id}", json.dumps(data))
    elapsed = time.time() - t0
    print(f"  Done: {count} messages in {elapsed:.3f}s ({count / elapsed:.0f} msg/s)")


def publish_multi(r: redis.Redis, n_markets: int = 5) -> None:
    markets = [f"market-{i:03d}" for i in range(1, n_markets + 1)]
    prices = {m: 0.5 for m in markets}
    seq = 0
    print(f"Multi-market: publishing to {n_markets} markets every 0.5-2s")
    try:
        while True:
            market = random.choice(markets)
            drift = random.uniform(-0.05, 0.05)
            prices[market] = max(0.01, min(0.99, prices[market] + drift))
            data = make_price_update(market, prices[market])
            data["seq"] = seq

            listeners = r.publish(f"{CHANNEL_PREFIX}{market}", json.dumps(data))
            print(f"  [{seq:04d}] {market} -> YES={data['yes_price']} (listeners={listeners})")
            seq += 1
            time.sleep(random.uniform(0.5, 2.0))
    except KeyboardInterrupt:
        print(f"\nStopped after {seq} messages across {n_markets} markets")


def main() -> None:
    parser = argparse.ArgumentParser(description="Spike 003: Price publisher")
    parser.add_argument("--burst", action="store_true", help="Burst mode: 100 rapid messages")
    parser.add_argument("--multi", action="store_true", help="Multi-market mode: 5 markets")
    parser.add_argument("--market", default="market-001", help="Market ID (default: market-001)")
    args = parser.parse_args()

    r = redis.from_url(REDIS_URL)
    try:
        r.ping()
    except redis.ConnectionError:
        print("ERROR: Cannot connect to Redis at localhost:6379")
        print("Make sure docker-compose is running: docker compose up -d redis")
        sys.exit(1)

    print("=" * 60)
    print(" Spike 003: Price Publisher (simulates Celery task)")
    print(f" Redis: {REDIS_URL}")
    print("=" * 60)

    if args.burst:
        publish_burst(r, args.market)
    elif args.multi:
        publish_multi(r)
    else:
        publish_steady(r, args.market)


if __name__ == "__main__":
    main()
