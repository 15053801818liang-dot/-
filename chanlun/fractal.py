"""分型识别 — 阿娇缠论 / 缠师108课口径。

包含处理后，用连续三根合并 K 线判定：
- 顶分型：中间 K 线的高、低点均为三根中最高（高高）。
- 底分型：中间 K 线的高、低点均为三根中最低（低低）。
"""

from __future__ import annotations

from typing import List

from .models import Fractal, FractalType, MergedBar
from .stroke_rules import bottom_extreme_bar_index, top_extreme_bar_index


def find_fractals(merged: List[MergedBar]) -> List[Fractal]:
    """在合并 K 线序列中识别所有分型。"""
    fractals: List[Fractal] = []
    for i in range(1, len(merged) - 1):
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
            tmp = Fractal(
                kind=FractalType.TOP,
                merged_index=i,
                bar_index=i,
                high=mid.high,
                low=mid.low,
            )
            fractals.append(
                Fractal(
                    kind=FractalType.TOP,
                    merged_index=i,
                    bar_index=top_extreme_bar_index(tmp, merged),
                    high=mid.high,
                    low=mid.low,
                )
            )
        elif is_bottom and not is_top:
            tmp = Fractal(
                kind=FractalType.BOTTOM,
                merged_index=i,
                bar_index=i,
                high=mid.high,
                low=mid.low,
            )
            fractals.append(
                Fractal(
                    kind=FractalType.BOTTOM,
                    merged_index=i,
                    bar_index=bottom_extreme_bar_index(tmp, merged),
                    high=mid.high,
                    low=mid.low,
                )
            )

    return fractals
