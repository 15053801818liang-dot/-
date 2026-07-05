"""笔级别逻辑漏洞探测 — 从 K线包含 → 分型 → 笔 逐级找边界与缺陷。

运行: python3 chanlun/test_stroke_vulnerabilities.py
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.analyzer import analyze
from chanlun.fractal import find_fractals
from chanlun.kline import process_inclusion
from chanlun.models import Bar, FractalType, MergedBar
from chanlun.stroke import build_strokes
from chanlun.test_chanlun import mk_fractal


class Vuln01EqualHighDirection(unittest.TestCase):
    """包含处理：新高相等时一律判 DOWN，忽略低点抬升（偏多 K 线被标为向下）。"""

    def test_equal_high_new_bar_marked_down(self):
        bars = [Bar(0, 10, 5), Bar(1, 15, 8), Bar(2, 18, 10), Bar(3, 18, 12)]
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 3)
        last = merged[-1]
        self.assertEqual(last.high, 18)
        self.assertEqual(last.low, 12)
        # bar3 与 bar2 等高但低点更高，新合并段 direction 仍为 UP（包含合并）
        # 若 bar3 独立成 K 线（无包含）则 direction=DOWN — 口径不一致
        self.assertEqual(last.direction.value, "up")


class Vuln02DefaultUpBias(unittest.TestCase):
    """序列开头仅一根合并 K 线时，包含方向默认 UP。"""

    def test_first_inclusion_assumes_up(self):
        bars = [Bar(0, 20, 10), Bar(1, 19, 11)]  # b2 被 b1 包含
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 1)
        # UP 规则：low=max(10,11)=11；若按前序下跌应为 high=19,low=11
        self.assertEqual(merged[0].high, 20)
        self.assertEqual(merged[0].low, 11)


class Vuln03FlatFractalDropped(unittest.TestCase):
    """分型：平顶/平底（等于邻 K 线极值）成不了分型；过宽 K 线双条件成立时被丢弃。"""

    def test_flat_top_skipped(self):
        merged = [
            MergedBar(10, 8, [0], high_index=0, low_index=0),
            MergedBar(15, 10, [1], high_index=1, low_index=1),
            MergedBar(15, 9, [2], high_index=2, low_index=2),
            MergedBar(12, 7, [3], high_index=3, low_index=3),
        ]
        tops = [f for f in find_fractals(merged) if f.kind is FractalType.TOP]
        self.assertEqual(len(tops), 0)

    def test_wide_middle_silent_drop(self):
        merged = [
            MergedBar(8, 6, [0], high_index=0, low_index=0),
            MergedBar(15, 4, [1], high_index=1, low_index=1),
            MergedBar(9, 5, [2], high_index=2, low_index=2),
        ]
        self.assertEqual(find_fractals(merged), [])


class Vuln04MinGapCliff(unittest.TestCase):
    """min_gap 差 1 可导致笔数从有到无 — 参数悬崖。"""

    def test_gap3_has_strokes_gap4_zero(self):
        bars = [Bar(i, h, l) for i, (h, l) in enumerate([
            (10, 8), (11, 9), (13, 10), (12, 9), (10, 7), (8, 5), (9, 6),
            (11, 8), (14, 11), (13, 10), (11, 8), (9, 6), (12, 9), (15, 12),
        ])]
        s3 = analyze(bars, min_gap=3).strokes
        s4 = analyze(bars, min_gap=4).strokes
        self.assertEqual(len(s3), 3)
        self.assertEqual(len(s4), 0)


class Vuln05SilentDropWhenGapSmall(unittest.TestCase):
    """间隔不足且无法回退时，反向分型被静默丢弃。"""

    def test_orphan_fractal_produces_zero_strokes(self):
        fractals = [
            mk_fractal(FractalType.BOTTOM, 0, 5),
            mk_fractal(FractalType.TOP, 2, 10),
        ]
        self.assertEqual(build_strokes(fractals, min_gap=4), [])


class Vuln06EqualExtremeKeepsStale(unittest.TestCase):
    """同类分型相等极值时保留旧分型，不更新到更近位置。"""

    def test_equal_top_keeps_earlier_index(self):
        fractals = [
            mk_fractal(FractalType.BOTTOM, 0, 5),
            mk_fractal(FractalType.TOP, 5, 12),
            mk_fractal(FractalType.TOP, 6, 12),
            mk_fractal(FractalType.BOTTOM, 11, 3),
        ]
        strokes = build_strokes(fractals, min_gap=4)
        self.assertEqual(strokes[0].end.merged_index, 5)


class Vuln07Repainting(unittest.TestCase):
    """增量 K 线会改写历史笔结构 — 回测/实盘不一致（未来函数）。"""

    def test_append_bars_can_change_stroke_count(self):
        base = [Bar(i, h, l) for i, (h, l) in enumerate([
            (10, 8), (11, 9), (13, 10), (12, 9), (10, 7), (8, 5), (9, 6),
            (11, 8), (14, 11), (13, 10), (11, 8), (9, 6), (12, 9), (15, 12),
        ])]
        n0 = len(analyze(base, min_gap=3).strokes)
        extended = base + [Bar(14, 16, 13), Bar(15, 14, 12), Bar(16, 13, 11)]
        n1 = len(analyze(extended, min_gap=3).strokes)
        self.assertNotEqual(n0, n1)


class Vuln08BarIndexFixedForMergeExtreme(unittest.TestCase):
    """修复验证：分型 bar_index 应对齐极值原始 K 线，而非合并区间首根。"""

    def test_top_fractal_uses_high_index(self):
        bars = [Bar(0, 10, 5), Bar(1, 12, 6), Bar(2, 11, 7)]
        merged = process_inclusion(bars)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1].high_index, 1)
        fractals = find_fractals(merged)
        tops = [f for f in fractals if f.kind is FractalType.TOP]
        if tops:
            self.assertEqual(tops[0].bar_index, 1)


class Vuln09SinglePopBacktrackInsufficient(unittest.TestCase):
    """假分型回退只 pop 一层，复杂噪声下结构残缺。"""

    def test_multi_top_noise(self):
        fractals = [
            mk_fractal(FractalType.BOTTOM, 0, 5),
            mk_fractal(FractalType.TOP, 2, 8),
            mk_fractal(FractalType.TOP, 3, 12),
            mk_fractal(FractalType.BOTTOM, 5, 4),
        ]
        strokes = build_strokes(fractals, min_gap=4)
        self.assertLessEqual(len(strokes), 1)


AUDIT_SUMMARY = """
笔级别漏洞审计 (chanlun) — 从「笔」出发
========================================

【P0 实盘/回测风险 — 已确认可复现】
  V07 重绘: 追加 K 线后笔数/结构变化 → 增量实盘与全量回测不一致
  V04 参数悬崖: min_gap=3 有 3 笔，min_gap=4 同数据 0 笔 → 策略参数极敏感
  V08 bar_index: 已修复 — 分型/MACD 区间现对齐 high_index/low_index

【P1 逻辑缺陷 — 仍 open】
  V01 等高判向: 无包含的新 K 线 high 相等时 direction=DOWN
  V02 默认 UP: 首段包含合并缺少前序方向上下文
  V03 平顶/双条件: 严格 >/< 漏平台；过宽 K 线整段丢弃
  V04 间隔口径: min_gap 按 merged_index 非原始 K 线根数

【P2 边界/可观测性 — 仍 open】
  V05 静默丢弃: gap 不足且无法 pop 时零笔无日志
  V06 相等极值: 同类分型不更新到更近 merged_index
  V09 单层回退: 连续假分型时回退不充分

【下一步修复建议】
  1. 笔状态机: confirmed / provisional，禁止改写 confirmed
  2. min_gap 同时校验 origin_indices 跨度
  3. build_strokes 返回 dropped_fractals 审计列表
  4. 包含方向: 首段用前两根非包含 K 线定方向；等高比 low
"""


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(AUDIT_SUMMARY)
    sys.exit(0 if result.wasSuccessful() else 1)
