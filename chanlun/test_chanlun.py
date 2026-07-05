"""缠论内核单元测试。

可直接运行：``python3 chanlun/test_chanlun.py``
也可用 pytest：``python3 -m pytest chanlun/test_chanlun.py``
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.analyzer import analyze
from chanlun.fractal import find_fractals
from chanlun.kline import process_inclusion
from chanlun.macd import area, ema, macd
from chanlun.models import (
    Bar,
    Direction,
    Fractal,
    FractalType,
    MergedBar,
    Stroke,
    StrokeStandard,
    TradePointType,
)
from chanlun.pivot import find_pivots
from chanlun.sample import sample_bars, sample_bars_pivot
from chanlun.signals import find_divergences
from chanlun.stroke import build_strokes


def mk_fractal(kind, merged_index, price, bar_index=None):
    """构造分型：顶分型 high=price，底分型 low=price。"""
    bar_index = merged_index if bar_index is None else bar_index
    if kind is FractalType.TOP:
        return Fractal(kind, merged_index, bar_index, high=price, low=price - 1)
    return Fractal(kind, merged_index, bar_index, high=price + 1, low=price)


def mk_stroke(direction, start_price, end_price, start_bar, end_bar):
    if direction is Direction.UP:
        start = mk_fractal(FractalType.BOTTOM, start_bar, start_price, start_bar)
        end = mk_fractal(FractalType.TOP, end_bar, end_price, end_bar)
    else:
        start = mk_fractal(FractalType.TOP, start_bar, start_price, start_bar)
        end = mk_fractal(FractalType.BOTTOM, end_bar, end_price, end_bar)
    return Stroke(direction=direction, start=start, end=end)


class TestInclusion(unittest.TestCase):
    def test_no_inclusion_preserved(self):
        bars = [Bar(0, 10, 5), Bar(1, 12, 7), Bar(2, 14, 9)]
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 3)

    def test_upward_inclusion_merge(self):
        # b2 被 b1 包含，向上处理：高取大、低取大。
        bars = [Bar(0, 10, 5), Bar(1, 12, 6), Bar(2, 11, 7)]
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1].high, 12)
        self.assertEqual(merged[1].low, 7)
        self.assertEqual(merged[1].origin_indices, [1, 2])

    def test_downward_inclusion_merge(self):
        # b2 被 b1 包含，向下处理：高取小、低取小。
        bars = [Bar(0, 20, 15), Bar(1, 18, 10), Bar(2, 17, 12)]
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1].high, 17)
        self.assertEqual(merged[1].low, 10)

    def test_empty(self):
        self.assertEqual(process_inclusion([]), [])


class TestFractal(unittest.TestCase):
    def test_top_fractal(self):
        merged = [MergedBar(10, 5, [0]), MergedBar(15, 8, [1]), MergedBar(12, 7, [2])]
        fractals = find_fractals(merged)
        self.assertEqual(len(fractals), 1)
        self.assertIs(fractals[0].kind, FractalType.TOP)
        self.assertEqual(fractals[0].price, 15)

    def test_bottom_fractal(self):
        merged = [MergedBar(15, 10, [0]), MergedBar(12, 5, [1]), MergedBar(14, 9, [2])]
        fractals = find_fractals(merged)
        self.assertEqual(len(fractals), 1)
        self.assertIs(fractals[0].kind, FractalType.BOTTOM)
        self.assertEqual(fractals[0].price, 5)


def linear_merged(n: int) -> list[MergedBar]:
    return [MergedBar(10.0 + i, 8.0 + i, [i], high_index=i, low_index=i) for i in range(n)]


class TestStroke(unittest.TestCase):
    def test_alternating_strokes(self):
        merged = linear_merged(15)
        fractals = [
            mk_fractal(FractalType.BOTTOM, 1, 5, 1),
            mk_fractal(FractalType.TOP, 6, 12, 6),
            mk_fractal(FractalType.BOTTOM, 12, 3, 12),
        ]
        strokes = build_strokes(fractals, merged, StrokeStandard.NEW)
        self.assertEqual(len(strokes), 2)
        self.assertIs(strokes[0].direction, Direction.UP)
        self.assertIs(strokes[1].direction, Direction.DOWN)

    def test_same_kind_keeps_extreme(self):
        merged = linear_merged(15)
        fractals = [
            mk_fractal(FractalType.BOTTOM, 1, 5, 1),
            mk_fractal(FractalType.BOTTOM, 2, 3, 2),
            mk_fractal(FractalType.TOP, 8, 12, 8),
        ]
        strokes = build_strokes(fractals, merged, StrokeStandard.NEW)
        self.assertEqual(len(strokes), 1)
        self.assertIs(strokes[0].direction, Direction.UP)
        self.assertEqual(strokes[0].start_price, 3)

    def test_gap_too_small_rejected(self):
        merged = linear_merged(15)
        fractals = [
            mk_fractal(FractalType.BOTTOM, 1, 5, 1),
            mk_fractal(FractalType.TOP, 3, 10, 3),
            mk_fractal(FractalType.BOTTOM, 5, 2, 5),
            mk_fractal(FractalType.TOP, 10, 15, 10),
        ]
        strokes = build_strokes(fractals, merged, StrokeStandard.OLD)
        self.assertEqual(len(strokes), 1)
        self.assertEqual(strokes[0].start_price, 2)
        self.assertEqual(strokes[0].end_price, 15)


class TestPivot(unittest.TestCase):
    def test_three_strokes_form_pivot(self):
        strokes = [
            mk_stroke(Direction.DOWN, 10, 6, 0, 4),
            mk_stroke(Direction.UP, 6, 9, 4, 8),
            mk_stroke(Direction.DOWN, 9, 7, 8, 12),
        ]
        pivots = find_pivots(strokes)
        self.assertEqual(len(pivots), 1)
        self.assertEqual(pivots[0].zg, 9)
        self.assertEqual(pivots[0].zd, 7)

    def test_no_overlap_no_pivot(self):
        strokes = [
            mk_stroke(Direction.DOWN, 10, 8, 0, 4),
            mk_stroke(Direction.UP, 8, 7, 4, 8),   # 造成不重叠
            mk_stroke(Direction.DOWN, 7, 5, 8, 12),
        ]
        # zg=min(10,8,7)=7, zd=max(8,7,5)=8 -> 7<8 不成中枢
        pivots = find_pivots(strokes)
        self.assertEqual(len(pivots), 0)

    def test_leaving_stroke_stops_extension(self):
        # 前三笔成中枢 [7,9]，第四笔终点离开区间 -> 不并入。
        strokes = [
            mk_stroke(Direction.DOWN, 10, 6, 0, 4),
            mk_stroke(Direction.UP, 6, 9, 4, 8),
            mk_stroke(Direction.DOWN, 9, 7, 8, 12),
            mk_stroke(Direction.UP, 7, 20, 12, 16),  # 离开
        ]
        pivots = find_pivots(strokes)
        self.assertEqual(len(pivots), 1)
        self.assertEqual(pivots[0].end_index, 2)


class TestMACD(unittest.TestCase):
    def test_ema_constant(self):
        self.assertEqual(ema([5, 5, 5, 5], 3), [5, 5, 5, 5])

    def test_macd_length(self):
        closes = [float(i) for i in range(1, 40)]
        result = macd(closes)
        self.assertEqual(len(result.dif), len(closes))
        self.assertEqual(len(result.hist), len(closes))

    def test_area_positive_negative(self):
        hist = [1.0, -2.0, 3.0, -4.0]
        self.assertEqual(area(hist, 0, 3, positive=True), 4.0)
        self.assertEqual(area(hist, 0, 3, positive=False), 6.0)

    def test_area_bounds_clamped(self):
        hist = [1.0, 2.0]
        self.assertEqual(area(hist, -5, 99, positive=True), 3.0)


class TestDivergence(unittest.TestCase):
    def test_bottom_divergence(self):
        strokes = [
            mk_stroke(Direction.UP, 5, 12, 0, 2),
            mk_stroke(Direction.DOWN, 12, 4, 2, 4),   # 第一段下跌，力度大
            mk_stroke(Direction.UP, 4, 10, 4, 8),
            mk_stroke(Direction.DOWN, 10, 2, 8, 10),  # 创新低但力度小
        ]
        hist = [0.0, 0.0, -5.0, -5.0, -5.0, 0.0, 0.0, 0.0, -1.0, -1.0, -1.0]
        divs = find_divergences(strokes, hist)
        self.assertIn((3, "bottom"), divs)

    def test_no_divergence_when_force_grows(self):
        strokes = [
            mk_stroke(Direction.UP, 5, 12, 0, 2),
            mk_stroke(Direction.DOWN, 12, 4, 2, 4),
            mk_stroke(Direction.UP, 4, 10, 4, 8),
            mk_stroke(Direction.DOWN, 10, 2, 8, 10),
        ]
        # 后一段力度更大 -> 不背驰
        hist = [0.0, 0.0, -1.0, -1.0, -1.0, 0.0, 0.0, 0.0, -5.0, -5.0, -5.0]
        divs = find_divergences(strokes, hist)
        self.assertEqual(divs, [])


class TestEndToEnd(unittest.TestCase):
    def test_sample_produces_buy1(self):
        result = analyze(sample_bars())
        self.assertGreater(len(result.strokes), 0)
        kinds = {tp.kind for tp in result.trade_points}
        self.assertIn(TradePointType.BUY1, kinds)

    def test_sample_pivot_produces_buy3(self):
        result = analyze(sample_bars_pivot())
        self.assertGreater(len(result.pivots), 0)
        kinds = {tp.kind for tp in result.trade_points}
        self.assertIn(TradePointType.BUY3, kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
