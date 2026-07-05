"""阿娇缠论成笔规则单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.analyzer import analyze
from chanlun.fractal import find_fractals
from chanlun.kline import process_inclusion
from chanlun.models import Bar, FractalType, MergedBar, StrokeStandard
from chanlun.stroke import build_strokes
from chanlun.stroke_rules import (
    no_shared_klines,
    raw_klines_between_extremes,
    valid_stroke_pair,
)
from chanlun.test_chanlun import mk_fractal


def linear_merged(n: int) -> list[MergedBar]:
    """构造 n 根无包含、无重叠的合并 K 线（origin 与 merged 一一对应）。"""
    out: list[MergedBar] = []
    for i in range(n):
        h = 10.0 + i
        out.append(MergedBar(h, h - 2, [i], high_index=i, low_index=i))
    return out


class TestAjiaoNewStroke(unittest.TestCase):
    """阿娇缠论 / 缠师新笔（默认）。"""

    def test_new_stroke_requires_three_raw_klines(self):
        merged = linear_merged(12)
        bottom = mk_fractal(FractalType.BOTTOM, 4, 5, 4)
        top = mk_fractal(FractalType.TOP, 7, 12, 7)
        # 底极值 bar3，顶极值 bar8，中间 4 根；分型窗口不共用 K 线
        self.assertEqual(raw_klines_between_extremes(bottom, top, merged), 4)
        self.assertTrue(valid_stroke_pair(bottom, top, merged, StrokeStandard.NEW))

        top_too_close = mk_fractal(FractalType.TOP, 5, 11, 5)
        self.assertLess(raw_klines_between_extremes(bottom, top_too_close, merged), 3)
        self.assertFalse(valid_stroke_pair(bottom, top_too_close, merged, StrokeStandard.NEW))

    def test_no_shared_klines(self):
        merged = linear_merged(10)
        # 底分型占用 merged 0,1,2；顶分型若从 2 开始则共用 index 2
        bottom = mk_fractal(FractalType.BOTTOM, 1, 3, 1)
        top_share = mk_fractal(FractalType.TOP, 2, 10, 2)
        self.assertFalse(no_shared_klines(bottom, top_share, merged))

        top_ok = mk_fractal(FractalType.TOP, 6, 12, 6)
        self.assertTrue(no_shared_klines(bottom, top_ok, merged))
        self.assertTrue(valid_stroke_pair(bottom, top_ok, merged, StrokeStandard.NEW))

    def test_old_stricter_than_new(self):
        bars = [Bar(i, h, l) for i, (h, l) in enumerate([
            (10, 8), (11, 9), (13, 10), (12, 9), (10, 7), (8, 5), (9, 6),
            (11, 8), (14, 11), (13, 10), (11, 8), (9, 6), (12, 9), (15, 12),
        ])]
        new_count = len(analyze(bars, stroke_standard=StrokeStandard.NEW).strokes)
        old_count = len(analyze(bars, stroke_standard=StrokeStandard.OLD).strokes)
        self.assertGreaterEqual(new_count, old_count)

    def test_default_analyzer_uses_new(self):
        bars = [Bar(i, h, l) for i, (h, l) in enumerate([
            (10, 8), (11, 9), (13, 10), (12, 9), (10, 7), (8, 5), (9, 6),
            (11, 8), (14, 11), (13, 10), (11, 8), (9, 6), (12, 9), (15, 12),
        ])]
        self.assertEqual(
            len(analyze(bars).strokes),
            len(analyze(bars, stroke_standard=StrokeStandard.NEW).strokes),
        )


class TestAjiaoFractal(unittest.TestCase):
    """阿娇缠论严格分型（中间 K 线高高 / 低低）。"""

    def test_strict_top_requires_high_and_low(self):
        merged = [
            MergedBar(10, 8, [0], high_index=0, low_index=0),
            MergedBar(15, 12, [1], high_index=1, low_index=1),
            MergedBar(13, 10, [2], high_index=2, low_index=2),
        ]
        tops = [f for f in find_fractals(merged) if f.kind is FractalType.TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].price, 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
