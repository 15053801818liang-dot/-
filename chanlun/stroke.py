"""笔的构建。

由交替的顶/底分型连接成笔，需满足：
1. 顶底分型严格交替（顶-底-顶-底…）。
2. 相邻两分型之间在合并 K 线上的间隔不小于 ``min_gap``
   （默认 4，即含两端至少 5 根合并 K 线，对应经典"老笔"口径）。

实现采用带回退的贪心：当出现间隔不足的反向分型时，
若它比更早的同类分型更极端，则弹出中间的"假分型"并重试，
从而在噪声数据上仍能得到稳定的笔序列。
"""

from __future__ import annotations

from typing import List

from .models import Direction, Fractal, FractalType, Stroke


def build_strokes(fractals: List[Fractal], min_gap: int = 4) -> List[Stroke]:
    """从分型序列构建笔序列。"""
    confirmed: List[Fractal] = []

    for f in fractals:
        while True:
            if not confirmed:
                confirmed.append(f)
                break

            last = confirmed[-1]

            if f.kind is last.kind:
                # 同类型分型：保留更极端者。
                more_extreme = (
                    f.high > last.high
                    if f.kind is FractalType.TOP
                    else f.low < last.low
                )
                if more_extreme:
                    confirmed[-1] = f
                break

            gap = abs(f.merged_index - last.merged_index)
            if gap >= min_gap:
                confirmed.append(f)
                break

            # 间隔不足：last 可能是未成笔的"假分型"。
            if len(confirmed) >= 2:
                prev = confirmed[-2]  # 与 f 同类型
                f_more_extreme = (
                    f.high > prev.high
                    if f.kind is FractalType.TOP
                    else f.low < prev.low
                )
                if f_more_extreme:
                    confirmed.pop()  # 弹出假分型，回退重试
                    continue
            break

    strokes: List[Stroke] = []
    for i in range(len(confirmed) - 1):
        a, b = confirmed[i], confirmed[i + 1]
        direction = Direction.UP if b.kind is FractalType.TOP else Direction.DOWN
        strokes.append(Stroke(direction=direction, start=a, end=b))

    return strokes
