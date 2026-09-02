"""笔的构建 — 阿娇缠论 / 缠师新笔（默认）与老笔。

成笔规则见 ``stroke_rules.valid_stroke_pair``。
采用带回退的贪心：间隔不足时若新分型更极端则弹出假分型重试。
"""

from __future__ import annotations

from typing import List

from .models import Direction, Fractal, FractalType, MergedBar, Stroke, StrokeStandard
from .stroke_rules import valid_stroke_pair


def build_strokes(
    fractals: List[Fractal],
    merged: List[MergedBar],
    standard: StrokeStandard = StrokeStandard.NEW,
    *,
    min_gap: int | None = None,
) -> List[Stroke]:
    """从分型序列构建笔序列。

    ``min_gap`` 已废弃，保留仅为兼容旧调用；请使用 ``standard``。
    """
    if min_gap is not None and standard is StrokeStandard.NEW:
        standard = StrokeStandard.OLD if min_gap >= 4 else StrokeStandard.NEW

    confirmed: List[Fractal] = []

    for f in fractals:
        while True:
            if not confirmed:
                confirmed.append(f)
                break

            last = confirmed[-1]

            if f.kind is last.kind:
                more_extreme = (
                    f.high > last.high
                    if f.kind is FractalType.TOP
                    else f.low < last.low
                )
                if more_extreme:
                    confirmed[-1] = f
                break

            if valid_stroke_pair(last, f, merged, standard):
                confirmed.append(f)
                break

            if len(confirmed) >= 2:
                prev = confirmed[-2]
                if prev.kind is f.kind:
                    f_more_extreme = (
                        f.high > prev.high
                        if f.kind is FractalType.TOP
                        else f.low < prev.low
                    )
                    if f_more_extreme and not valid_stroke_pair(prev, last, merged, standard):
                        confirmed.pop()
                        continue
            break

    strokes: List[Stroke] = []
    for i in range(len(confirmed) - 1):
        a, b = confirmed[i], confirmed[i + 1]
        direction = Direction.UP if b.kind is FractalType.TOP else Direction.DOWN
        strokes.append(Stroke(direction=direction, start=a, end=b))

    return strokes
