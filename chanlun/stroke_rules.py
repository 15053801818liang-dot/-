"""阿娇缠论 / 缠师108课 — 成笔规则校验。

新笔（宽笔，A 股默认）两条件：
  1. 顶底分型经包含处理后不共用任何原始 K 线；
  2. 顶分型最高 K 与底分型最低 K 之间（不含这两根），原始 K 线 ≥ 3 根。

老笔（严笔）：
  包含处理后顶底分型之间至少 5 根合并 K 线，且不共用 K 线。
"""

from __future__ import annotations

from typing import List, Set

from .models import Fractal, FractalType, MergedBar, StrokeStandard


def fractal_origin_indices(f: Fractal, merged: List[MergedBar]) -> Set[int]:
    """分型三根合并 K 线涉及的全部原始 K 线下标。"""
    origins: Set[int] = set()
    i = f.merged_index
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(merged):
            origins.update(merged[j].origin_indices)
    return origins


def top_extreme_bar_index(f: Fractal, merged: List[MergedBar]) -> int:
    """顶分型三根 K 线中最高点的原始下标。"""
    i = f.merged_index
    window = [merged[i - 1], merged[i], merged[i + 1]]
    return max(window, key=lambda b: (b.high, -b.low)).high_index


def bottom_extreme_bar_index(f: Fractal, merged: List[MergedBar]) -> int:
    """底分型三根 K 线中最低点的原始下标。"""
    i = f.merged_index
    window = [merged[i - 1], merged[i], merged[i + 1]]
    return min(window, key=lambda b: (b.low, b.high)).low_index


def _ordered_pair(a: Fractal, b: Fractal) -> tuple[Fractal, Fractal]:
    """返回 (bottom, top)。"""
    if a.kind is FractalType.BOTTOM and b.kind is FractalType.TOP:
        return a, b
    if a.kind is FractalType.TOP and b.kind is FractalType.BOTTOM:
        return b, a
    raise ValueError("pair must be one top and one bottom")


def no_shared_klines(a: Fractal, b: Fractal, merged: List[MergedBar]) -> bool:
    """条件一：顶底分型不共用原始 K 线。"""
    return fractal_origin_indices(a, merged).isdisjoint(fractal_origin_indices(b, merged))


def raw_klines_between_extremes(a: Fractal, b: Fractal, merged: List[MergedBar]) -> int:
    """极值两根原始 K 线之间（不含端点）的 K 线根数。"""
    bottom, top = _ordered_pair(a, b)
    lo_idx = bottom_extreme_bar_index(bottom, merged)
    hi_idx = top_extreme_bar_index(top, merged)
    left, right = min(lo_idx, hi_idx), max(lo_idx, hi_idx)
    return max(0, right - left - 1)


def merged_span(a: Fractal, b: Fractal) -> int:
    """两分型中心在合并序列上的跨度（含端点）。"""
    return abs(a.merged_index - b.merged_index) + 1


def price_valid(a: Fractal, b: Fractal) -> bool:
    """顶分型顶必须高于底分型底。"""
    bottom, top = _ordered_pair(a, b)
    return top.high > bottom.low


def valid_stroke_pair(
    a: Fractal,
    b: Fractal,
    merged: List[MergedBar],
    standard: StrokeStandard = StrokeStandard.NEW,
) -> bool:
    """判断相邻顶底分型能否连成一笔（阿娇缠论口径）。"""
    if a.kind is b.kind:
        return False
    if not price_valid(a, b):
        return False
    if not no_shared_klines(a, b, merged):
        return False

    if standard is StrokeStandard.OLD:
        # 老笔：合并 K 线至少 5 根（中心跨度 ≥ 5）
        return merged_span(a, b) >= 5

    # 新笔条件二：极值之间原始 K 线 ≥ 3
    if raw_klines_between_extremes(a, b, merged) < 3:
        return False
    # 新笔条件一推论：合并后至少 4 根 K 线
    return merged_span(a, b) >= 4
