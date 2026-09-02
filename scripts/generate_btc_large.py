#!/usr/bin/env python3
"""生成大规模 BTC 5m 演示 CSV（随机游走 + 周期转折，用于压测）。"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def generate_rows(n: int, seed: int = 42) -> list[dict]:
    random.seed(seed)
    price = 42000.0
    rows: list[dict] = []
    for i in range(n):
        drift = random.gauss(0, 0.0012)
        if i % 500 == 0:
            drift += random.choice([-0.02, 0.02])
        price = max(1000.0, price * (1.0 + drift))
        spread = price * 0.001
        high = price + spread * random.random()
        low = price - spread * random.random()
        open_p = (high + low) / 2
        rows.append(
            {
                "timestamp": f"2024-01-01T{i:06d}",
                "open": round(open_p, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(price, 2),
                "volume": round(100 + random.random() * 50, 2),
            }
        )
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Generate large BTCUSDT 5m CSV")
    p.add_argument("-n", "--rows", type=int, default=100_000, help="number of bars")
    p.add_argument("-o", "--output", default="data/BTCUSDT_5m_large.csv")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows(args.rows, args.seed)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} bars -> {out.resolve()}")


if __name__ == "__main__":
    main()
