"""K 线数据加载 — 纯标准库 CSV，零外部依赖。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Sequence, Tuple

from .models import Bar


def bars_from_rows(rows: Sequence[Tuple[float, float, float, float]]) -> List[Bar]:
    """(open, high, low, close) → Bar 列表。"""
    bars: List[Bar] = []
    for i, (o, h, l, c) in enumerate(rows):
        bars.append(Bar(index=i, open=o, high=h, low=l, close=c))
    return bars


def load_csv(path: str | Path) -> List[Bar]:
    """加载 OHLCV CSV。必需列: open, high, low, close（volume 可选）。"""
    path = Path(path)
    bars: List[Bar] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            bars.append(
                Bar(
                    index=i,
                    open=float(row.get("open", row.get("Open", 0))),
                    high=float(row["high"] if "high" in row else row["High"]),
                    low=float(row["low"] if "low" in row else row["Low"]),
                    close=float(row["close"] if "close" in row else row["Close"]),
                    volume=float(row.get("volume", row.get("Volume", 0)) or 0),
                )
            )
    return bars


def save_csv(bars: List[Bar], path: str | Path) -> None:
    """将 Bar 序列写入 CSV artifact。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for b in bars:
            writer.writerow(
                {
                    "index": b.index,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
            )
