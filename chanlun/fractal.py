"""分型识别。

在包含处理后的合并 K 线序列上，用连续三根判定顶/底分型：
- 顶分型：中间一根的高点同时高于左右两根。
- 底分型：中间一根的低点同时低于左右两根。
"""

from __future__ import annotations

from typing import List

from .models import Fractal, FractalType, MergedBar


def find_fractals(merged: List[MergedBar]) -> List[Fractal]:
    """在合并 K 线序列中识别所有分型。"""
    fractals: List[Fractal] = []
    for i in range(1, len(merged) - 1):
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]

        is_top = mid.high > left.high and mid.high > right.high
        is_bottom = mid.low < left.low and mid.low < right.low

        # 合并后不应同时成立；若同时成立（异常数据）则跳过。
        if is_top and not is_bottom:
            fractals.append(
                Fractal(
                    kind=FractalType.TOP,
                    merged_index=i,
                    bar_index=mid.index,
                    high=mid.high,
                    low=mid.low,
                )
            )
        elif is_bottom and not is_top:
            fractals.append(
                Fractal(
                    kind=FractalType.BOTTOM,
                    merged_index=i,
                    bar_index=mid.index,
                    high=mid.high,
                    low=mid.low,
                )
            )

    return fractals
