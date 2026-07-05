"""K 线包含处理（合并）。

缠论第一步：对相邻存在包含关系的 K 线按当前走势方向合并，
消除包含关系后再识别分型。
"""

from __future__ import annotations

from typing import List

from .models import Bar, Direction, MergedBar


def _current_direction(merged: List[MergedBar]) -> Direction:
    """依据已合并序列的最后两根判断当前处理方向。

    不足两根时默认向上（与主流缠论实现一致）。
    """
    if len(merged) >= 2:
        return Direction.UP if merged[-1].high > merged[-2].high else Direction.DOWN
    return Direction.UP


def _has_inclusion(a: MergedBar, b: Bar) -> bool:
    """两根 K 线是否存在包含关系（任一方包含另一方）。"""
    a_in_b = b.high >= a.high and b.low <= a.low
    b_in_a = a.high >= b.high and a.low <= b.low
    return a_in_b or b_in_a


def process_inclusion(bars: List[Bar]) -> List[MergedBar]:
    """对原始 K 线执行包含处理，返回合并后的 K 线序列。

    - 向上处理：高点取大、低点取大（高高、低取高）。
    - 向下处理：高点取小、低点取小（低低、高取低）。
    """
    if not bars:
        return []

    first = bars[0]
    merged: List[MergedBar] = [
        MergedBar(
            high=first.high,
            low=first.low,
            origin_indices=[first.index],
            high_index=first.index,
            low_index=first.index,
        )
    ]

    for bar in bars[1:]:
        last = merged[-1]
        if _has_inclusion(last, bar):
            direction = _current_direction(merged)
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
            merged.append(
                MergedBar(
                    high=bar.high,
                    low=bar.low,
                    origin_indices=[bar.index],
                    direction=direction,
                    high_index=bar.index,
                    low_index=bar.index,
                )
            )

    return merged
