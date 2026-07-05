"""缠论结构导出 — 将 ChanResult 序列化为 artifact 可用的结构语义。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .analyzer import ChanResult
from .signals import find_divergences


def export_chanlun_structure(
    result: ChanResult,
    *,
    recent_strokes: int = 10,
    active_pivots: int = 5,
) -> Dict[str, Any]:
    """导出笔/中枢/背驰/买卖点结构，供盘古推理与审计报告消费。"""
    strokes = result.strokes
    pivots = result.pivots
    divergences = find_divergences(strokes, result.macd.hist)

    tail_n = min(recent_strokes, len(strokes))
    tail_start = len(strokes) - tail_n
    recent = []
    for i in range(tail_start, len(strokes)):
        item = strokes[i].to_dict()
        item["index"] = i
        recent.append(item)

    last_divergence: Optional[Dict[str, Any]] = None
    if divergences:
        idx, kind = divergences[-1]
        stroke = strokes[idx]
        last_divergence = {
            "stroke_index": idx,
            "kind": kind,
            "bar_index": stroke.end.bar_index,
            "price": stroke.end_price,
            "reason": "顶背驰" if kind == "top" else "底背驰",
        }

    pivot_tail = pivots[-active_pivots:] if pivots else []
    active = [p.to_dict() for p in pivot_tail]

    last_stroke: Optional[Dict[str, Any]] = None
    if strokes:
        last = strokes[-1]
        last_stroke = last.to_dict()
        last_stroke["index"] = len(strokes) - 1

    return {
        "recent_strokes": recent,
        "active_pivots": active,
        "last_divergence": last_divergence,
        "divergences_count": len(divergences),
        "trade_points": [tp.to_dict() for tp in result.trade_points],
        "current_stroke_index": len(strokes) - 1 if strokes else -1,
        "total_strokes": len(strokes),
        "total_pivots": len(pivots),
        "last_stroke": last_stroke,
    }
