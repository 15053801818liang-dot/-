"""背驰判定与一/二/三类买卖点。

- 背驰：相邻同向笔中，后一笔创新高/新低但 MACD 柱面积（力度）更小。
- 第一类买卖点：由底/顶背驰给出。
- 第二类买卖点：第一类之后的同向回抽不创新低/新高。
- 第三类买卖点：离开中枢后的回抽不重回中枢区间。
"""

from __future__ import annotations

from typing import List, Tuple

from .macd import area
from .models import Direction, Pivot, Stroke, TradePoint, TradePointType


def find_divergences(strokes: List[Stroke], hist: List[float]) -> List[Tuple[int, str]]:
    """返回背驰列表：(笔下标, 'top'|'bottom')。

    以相隔一笔的同向笔（i 与 i-2）作力度对比。
    """
    results: List[Tuple[int, str]] = []
    for i in range(2, len(strokes)):
        cur, prev = strokes[i], strokes[i - 2]
        if cur.direction is not prev.direction:
            continue

        if cur.direction is Direction.UP:
            made_extreme = cur.end_price > prev.end_price
            cur_force = area(hist, cur.start.bar_index, cur.end.bar_index, positive=True)
            prev_force = area(hist, prev.start.bar_index, prev.end.bar_index, positive=True)
            if made_extreme and cur_force < prev_force:
                results.append((i, "top"))
        else:
            made_extreme = cur.end_price < prev.end_price
            cur_force = area(hist, cur.start.bar_index, cur.end.bar_index, positive=False)
            prev_force = area(hist, prev.start.bar_index, prev.end.bar_index, positive=False)
            if made_extreme and cur_force < prev_force:
                results.append((i, "bottom"))

    return results


def generate_trade_points(
    strokes: List[Stroke],
    pivots: List[Pivot],
    hist: List[float],
) -> List[TradePoint]:
    """综合背驰与中枢，输出一/二/三类买卖点。"""
    points: List[TradePoint] = []
    divergences = find_divergences(strokes, hist)

    # 一类 & 二类
    for idx, kind in divergences:
        stroke = strokes[idx]
        if kind == "bottom":
            points.append(
                TradePoint(
                    kind=TradePointType.BUY1,
                    bar_index=stroke.end.bar_index,
                    price=stroke.end_price,
                    reason="底背驰",
                )
            )
            # 二类买点：BUY1 之后的向下回调笔不创新低。
            if idx + 2 < len(strokes):
                pull = strokes[idx + 2]
                if pull.direction is Direction.DOWN and pull.end_price > stroke.end_price:
                    points.append(
                        TradePoint(
                            kind=TradePointType.BUY2,
                            bar_index=pull.end.bar_index,
                            price=pull.end_price,
                            reason="一类买点后回调不创新低",
                        )
                    )
        else:  # top
            points.append(
                TradePoint(
                    kind=TradePointType.SELL1,
                    bar_index=stroke.end.bar_index,
                    price=stroke.end_price,
                    reason="顶背驰",
                )
            )
            if idx + 2 < len(strokes):
                pull = strokes[idx + 2]
                if pull.direction is Direction.UP and pull.end_price < stroke.end_price:
                    points.append(
                        TradePoint(
                            kind=TradePointType.SELL2,
                            bar_index=pull.end.bar_index,
                            price=pull.end_price,
                            reason="一类卖点后反弹不创新高",
                        )
                    )

    # 三类：离开中枢后的回抽不回中枢。
    for pivot in pivots:
        leave_idx = pivot.end_index + 1
        pull_idx = pivot.end_index + 2
        if pull_idx >= len(strokes):
            continue
        leave, pull = strokes[leave_idx], strokes[pull_idx]

        # 三买：向上离开（离开笔高点高于中枢上沿）后，回调低点不回中枢。
        if (
            leave.direction is Direction.UP
            and leave.high > pivot.zg
            and pull.direction is Direction.DOWN
            and pull.end_price > pivot.zg
        ):
            points.append(
                TradePoint(
                    kind=TradePointType.BUY3,
                    bar_index=pull.end.bar_index,
                    price=pull.end_price,
                    reason="上涨离开中枢后回调不回中枢",
                )
            )
        # 三卖：向下离开后，反抽高点不回中枢。
        if (
            leave.direction is Direction.DOWN
            and leave.low < pivot.zd
            and pull.direction is Direction.UP
            and pull.end_price < pivot.zd
        ):
            points.append(
                TradePoint(
                    kind=TradePointType.SELL3,
                    bar_index=pull.end.bar_index,
                    price=pull.end_price,
                    reason="下跌离开中枢后反抽不回中枢",
                )
            )

    points.sort(key=lambda p: p.bar_index)
    return points
