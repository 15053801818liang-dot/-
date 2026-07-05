"""MACD 指标（用于背驰判定的力度度量）。

纯标准库实现的经典 MACD：
- DIF = EMA(close, 12) - EMA(close, 26)
- DEA = EMA(DIF, 9)
- HIST（柱） = 2 * (DIF - DEA)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MACDResult:
    dif: List[float]
    dea: List[float]
    hist: List[float]


def ema(values: List[float], period: int) -> List[float]:
    """指数移动平均。首值以第一个样本初始化。"""
    if not values:
        return []
    k = 2.0 / (period + 1)
    out: List[float] = []
    prev = values[0]
    for i, v in enumerate(values):
        prev = v if i == 0 else v * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDResult:
    """计算 MACD 三条线。"""
    if not closes:
        return MACDResult(dif=[], dea=[], hist=[])
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    hist = [2.0 * (d - e) for d, e in zip(dif, dea)]
    return MACDResult(dif=dif, dea=dea, hist=hist)


def area(hist: List[float], start: int, end: int, positive: bool) -> float:
    """统计 [start, end] 区间内 MACD 柱的面积（力度）。

    positive=True 取红柱（>0）面积，False 取绿柱（<0）面积的绝对值。
    区间下标做边界裁剪，保证健壮。
    """
    if not hist:
        return 0.0
    lo = max(0, min(start, end))
    hi = min(len(hist) - 1, max(start, end))
    total = 0.0
    for i in range(lo, hi + 1):
        h = hist[i]
        if positive and h > 0:
            total += h
        elif not positive and h < 0:
            total += -h
    return total
