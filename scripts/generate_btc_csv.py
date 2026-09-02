#!/usr/bin/env python3
"""生成 BTCUSDT 5m 演示 CSV（合成数据，含清晰缠论结构）。"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chanlun.sample import synth_bars

# BTC 价位尺度下的转折序列：下降通道 + 底背驰 + 中枢突破
turning = [
    42000, 42000, 42000,
    40500, 41200, 39800, 40800, 39200, 40200, 38500, 39500, 38000,
    39000, 37500, 38500, 37000,
    38200,  # 反弹
    36500,  # 新低（力度衰减 → 底背驰区域）
    37800,
    36000,
]
bars = synth_bars(turning, seg_len=8, half_width=25.0)

out = Path(__file__).resolve().parents[1] / "data" / "BTCUSDT_5m.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
    w.writeheader()
    for i, b in enumerate(bars):
        w.writerow(
            {
                "timestamp": f"2024-01-01T{i:04d}",
                "open": round(b.open, 2),
                "high": round(b.high, 2),
                "low": round(b.low, 2),
                "close": round(b.close, 2),
                "volume": 100.0 + i,
            }
        )
print(f"wrote {len(bars)} bars -> {out}")
