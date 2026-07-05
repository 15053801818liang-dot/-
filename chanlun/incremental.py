"""增量缠论分析 — 单遍 O(N) 喂入，尾部 O(1) 更新分型。

与全量 ``analyze()`` 结果一致，但避免重复扫描与中间列表膨胀。
"""

from __future__ import annotations

from typing import List, Optional

from .analyzer import ChanResult
from .fractal import find_fractals
from .kline import _current_direction, _has_inclusion
from .macd import MACDResult, macd
from .models import Bar, Direction, Fractal, FractalType, MergedBar, StrokeStandard
from .pivot import find_pivots
from .signals import generate_trade_points
from .stroke import build_strokes
from .stroke_rules import bottom_extreme_bar_index, top_extreme_bar_index


def _detect_fractal_at(merged: List[MergedBar], i: int) -> Optional[Fractal]:
    if i < 1 or i >= len(merged) - 1:
        return None
    left, mid, right = merged[i - 1], merged[i], merged[i + 1]
    is_top = (
        mid.high >= left.high
        and mid.high >= right.high
        and mid.low >= left.low
        and mid.low >= right.low
        and (mid.high > left.high or mid.high > right.high)
    )
    is_bottom = (
        mid.low <= left.low
        and mid.low <= right.low
        and mid.high <= left.high
        and mid.high <= right.high
        and (mid.low < left.low or mid.low < right.low)
    )
    if is_top and not is_bottom:
        tmp = Fractal(FractalType.TOP, i, i, mid.high, mid.low)
        return Fractal(
            FractalType.TOP, i, top_extreme_bar_index(tmp, merged), mid.high, mid.low
        )
    if is_bottom and not is_top:
        tmp = Fractal(FractalType.BOTTOM, i, i, mid.high, mid.low)
        return Fractal(
            FractalType.BOTTOM, i, bottom_extreme_bar_index(tmp, merged), mid.high, mid.low
        )
    return None


class IncrementalAnalyzer:
    """逐根喂入 K 线，增量维护 merged + fractals。"""

    def __init__(self) -> None:
        self.bars: List[Bar] = []
        self.merged: List[MergedBar] = []
        self._fractals_by_idx: dict[int, Fractal] = {}
        self._closes: List[float] = []

    @property
    def fractals(self) -> List[Fractal]:
        return [self._fractals_by_idx[i] for i in sorted(self._fractals_by_idx)]

    def _refresh_fractals_tail(self) -> None:
        """仅刷新尾部候选分型（索引 n-2），O(1)。"""
        n = len(self.merged)
        if n < 3:
            return
        center = n - 2
        self._fractals_by_idx.pop(center, None)
        f = _detect_fractal_at(self.merged, center)
        if f:
            self._fractals_by_idx[center] = f

    def feed(self, bar: Bar) -> None:
        self.bars.append(bar)
        self._closes.append(bar.close if bar.close else (bar.high + bar.low) / 2.0)

        if not self.merged:
            self.merged.append(
                MergedBar(
                    high=bar.high,
                    low=bar.low,
                    origin_indices=[bar.index],
                    high_index=bar.index,
                    low_index=bar.index,
                )
            )
            return

        last = self.merged[-1]
        if _has_inclusion(last, bar):
            direction = _current_direction(self.merged)
            if direction is Direction.UP:
                if bar.high >= last.high:
                    last.high = bar.high
                    last.high_index = bar.index
                if bar.low >= last.low:
                    last.low = bar.low
                    last.low_index = bar.index
            else:
                if bar.high <= last.high:
                    last.high = bar.high
                    last.high_index = bar.index
                if bar.low <= last.low:
                    last.low = bar.low
                    last.low_index = bar.index
            last.origin_indices.append(bar.index)
            last.direction = direction
        else:
            direction = Direction.UP if bar.high > last.high else Direction.DOWN
            self.merged.append(
                MergedBar(
                    high=bar.high,
                    low=bar.low,
                    origin_indices=[bar.index],
                    direction=direction,
                    high_index=bar.index,
                    low_index=bar.index,
                )
            )

        self._refresh_fractals_tail()

    def feed_all(self, bars: List[Bar]) -> None:
        for b in bars:
            self.feed(b)

    def finalize(
        self,
        stroke_standard: StrokeStandard = StrokeStandard.NEW,
    ) -> ChanResult:
        strokes = build_strokes(self.fractals, self.merged, stroke_standard)
        pivots = find_pivots(strokes)
        macd_result = macd(self._closes)
        trade_points = generate_trade_points(strokes, pivots, macd_result.hist)
        return ChanResult(
            bars=self.bars,
            merged=self.merged,
            fractals=self.fractals,
            strokes=strokes,
            pivots=pivots,
            macd=macd_result,
            trade_points=trade_points,
        )


def analyze_incremental(
    bars: List[Bar],
    stroke_standard: StrokeStandard = StrokeStandard.NEW,
) -> ChanResult:
    """增量分析入口（大批量数据默认路径）。"""
    engine = IncrementalAnalyzer()
    engine.feed_all(bars)
    return engine.finalize(stroke_standard)


def analyze_auto(
    bars: List[Bar],
    stroke_standard: StrokeStandard = StrokeStandard.NEW,
    incremental_threshold: int = 1000,
) -> ChanResult:
    """小样本走全量路径，大样本走增量路径。"""
    if len(bars) >= incremental_threshold:
        return analyze_incremental(bars, stroke_standard)
    from .analyzer import analyze

    return analyze(bars, stroke_standard=stroke_standard)


def verify_incremental_matches(bars: List[Bar], standard: StrokeStandard = StrokeStandard.NEW) -> bool:
    """调试：对比增量与全量分型/笔数是否一致。"""
    from .analyzer import analyze

    full = analyze(bars, stroke_standard=standard)
    inc = analyze_incremental(bars, stroke_standard=standard)
    return (
        len(full.merged) == len(inc.merged)
        and len(full.fractals) == len(inc.fractals)
        and len(full.strokes) == len(inc.strokes)
    )
