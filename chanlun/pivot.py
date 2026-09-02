"""中枢识别。

中枢定义（笔中枢近似）：连续至少三笔存在价格重叠区间。
- 中枢上沿 ZG = 头三笔高点的最小值
- 中枢下沿 ZD = 头三笔低点的最大值
- 仅当 ZG > ZD 时成立。

中枢形成后，其 ZG/ZD 由头三笔固定；后续笔只要其**终点**仍落在
[ZD, ZG] 区间内（即走势仍在中枢中心震荡）即并入该中枢（延伸），
一旦某笔终点脱离区间（离开中枢）即停止延伸。这样"离开中枢的笔"
不会被并入，从而可用于识别第三类买卖点。
"""

from __future__ import annotations

from typing import List

from .models import Pivot, Stroke


def find_pivots(strokes: List[Stroke]) -> List[Pivot]:
    """在笔序列中识别所有（互不重叠的）中枢。"""
    pivots: List[Pivot] = []
    n = len(strokes)
    i = 0

    while i + 2 < n:
        window = strokes[i : i + 3]
        zg = min(s.high for s in window)
        zd = max(s.low for s in window)

        if zg > zd:
            members = list(window)
            end = i + 2
            j = i + 3
            while j < n:
                s = strokes[j]
                still_inside = zd <= s.end_price <= zg
                if still_inside:
                    members.append(s)
                    end = j
                    j += 1
                else:
                    break
            pivots.append(
                Pivot(
                    zg=zg,
                    zd=zd,
                    start_index=i,
                    end_index=end,
                    strokes=members,
                )
            )
            i = end + 1
        else:
            i += 1

    return pivots
