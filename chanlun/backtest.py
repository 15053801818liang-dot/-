"""缠论信号简易回测 — 基于 trade_points 的 long-only 模拟。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .analyzer import analyze
from .models import Bar, StrokeStandard, TradePointType


def _simulate(bars: List[Bar], result) -> Dict[str, Any]:
    """按买卖点模拟持仓，返回 trades 与 metrics。"""
    initial = 1.0
    cash = initial
    position = 0.0
    entry_price = 0.0
    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = [initial]

    buy_kinds = {TradePointType.BUY1, TradePointType.BUY2, TradePointType.BUY3}
    sell_kinds = {TradePointType.SELL1, TradePointType.SELL2, TradePointType.SELL3}

    points = sorted(result.trade_points, key=lambda p: p.bar_index)
    point_by_bar = {p.bar_index: p for p in points}

    for bar in bars:
        tp = point_by_bar.get(bar.index)
        if tp and tp.kind in buy_kinds and position == 0:
            position = cash / bar.close
            entry_price = bar.close
            cash = 0.0
            trades.append(
                {
                    "side": "buy",
                    "bar_index": bar.index,
                    "price": bar.close,
                    "kind": tp.kind.value,
                    "reason": tp.reason,
                }
            )
        elif tp and tp.kind in sell_kinds and position > 0:
            cash = position * bar.close
            pnl = (bar.close - entry_price) / entry_price
            trades.append(
                {
                    "side": "sell",
                    "bar_index": bar.index,
                    "price": bar.close,
                    "kind": tp.kind.value,
                    "reason": tp.reason,
                    "pnl": round(pnl, 6),
                }
            )
            position = 0.0
            entry_price = 0.0

        mark = position * bar.close if position > 0 else cash
        equity_curve.append(mark)

    if position > 0 and bars:
        cash = position * bars[-1].close
        position = 0.0

    total_return = cash - initial
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            returns.append((equity_curve[i] - prev) / prev)

    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = min(max_dd, (v - peak) / peak)

    sell_trades = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in sell_trades if t.get("pnl", 0) > 0]
    win_rate = len(wins) / len(sell_trades) if sell_trades else 0.0

    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        sharpe = (mean_r / math.sqrt(var)) * math.sqrt(252 * 288) if var > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "trades": trades,
        "metrics": {
            "sharpe": round(sharpe, 4),
            "total_return": round(total_return, 6),
            "max_drawdown": round(max_dd, 6),
            "win_rate": round(win_rate, 4),
            "total_trades": len(sell_trades),
            "signals_count": len(result.trade_points),
            "strokes_count": len(result.strokes),
            "fractals_count": len(result.fractals),
            "pivots_count": len(result.pivots),
        },
        "structure": {
            "trade_point_kinds": sorted({tp.kind.value for tp in result.trade_points}),
        },
    }


def run_chanlun_backtest(bars: List[Bar], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """缠论结构分析 + 信号回测主入口。"""
    config = config or {}
    standard_name = config.get("stroke_standard", "new")
    standard = StrokeStandard.OLD if standard_name == "old" else StrokeStandard.NEW

    result = analyze(bars, stroke_standard=standard)
    out = _simulate(bars, result)
    out["structure"]["stroke_standard"] = standard.value
    out["audit"] = {
        "engine": "chanlun",
        "version": "0.1.0",
        "stroke_standard": standard.value,
        "bars": len(bars),
    }
    return out
