"""缠论分析门面：把 K 线 → 合并 → 分型 → 笔 → 中枢 → 买卖点 串成一条流水线。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .fractal import find_fractals
from .kline import process_inclusion
from .macd import MACDResult, macd
from .models import Bar, Fractal, MergedBar, Pivot, Stroke, StrokeStandard, TradePoint
from .pivot import find_pivots
from .signals import generate_trade_points
from .stroke import build_strokes


@dataclass
class ChanResult:
    """一次完整缠论分析的结果。"""

    bars: List[Bar]
    merged: List[MergedBar]
    fractals: List[Fractal]
    strokes: List[Stroke]
    pivots: List[Pivot]
    macd: MACDResult
    trade_points: List[TradePoint] = field(default_factory=list)


class ChanAnalyzer:
    """缠论分析器。

    ``stroke_standard`` 默认 ``NEW``（阿娇缠论 / 缠师新笔，A 股口径）。
    """

    def __init__(self, stroke_standard: StrokeStandard = StrokeStandard.NEW, min_gap: int | None = None):
        self.stroke_standard = stroke_standard
        self.min_gap = min_gap  # 兼容旧参数

    def analyze(self, bars: List[Bar]) -> ChanResult:
        merged = process_inclusion(bars)
        fractals = find_fractals(merged)
        strokes = build_strokes(
            fractals,
            merged,
            self.stroke_standard,
            min_gap=self.min_gap,
        )
        pivots = find_pivots(strokes)
        closes = [b.close if b.close else (b.high + b.low) / 2.0 for b in bars]
        macd_result = macd(closes)
        trade_points = generate_trade_points(strokes, pivots, macd_result.hist)
        return ChanResult(
            bars=bars,
            merged=merged,
            fractals=fractals,
            strokes=strokes,
            pivots=pivots,
            macd=macd_result,
            trade_points=trade_points,
        )


def bars_from_ohlc(rows: Sequence[Tuple[float, float, float, float]]) -> List[Bar]:
    """从 (open, high, low, close) 行序列构造 Bar 列表。"""
    bars: List[Bar] = []
    for i, (o, h, l, c) in enumerate(rows):
        bars.append(Bar(index=i, high=h, low=l, open=o, close=c))
    return bars


def bars_from_hl(rows: Sequence[Tuple[float, float]]) -> List[Bar]:
    """从 (high, low) 行序列构造 Bar 列表（close 取中值）。"""
    bars: List[Bar] = []
    for i, (h, l) in enumerate(rows):
        bars.append(Bar(index=i, high=h, low=l, close=(h + l) / 2.0))
    return bars


def analyze(
    bars: List[Bar],
    stroke_standard: StrokeStandard = StrokeStandard.NEW,
    min_gap: int | None = None,
) -> ChanResult:
    """便捷函数：一行完成分析（默认阿娇缠论新笔）。"""
    return ChanAnalyzer(stroke_standard=stroke_standard, min_gap=min_gap).analyze(bars)
