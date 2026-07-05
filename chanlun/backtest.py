"""缠论信号回测 — 含手续费/滑点摩擦成本的生产级模拟。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .analyzer import analyze
from .models import Bar, StrokeStandard, TradePointType


def _exec_buy(cash: float, mid: float, commission: float, slippage: float) -> tuple[float, float, float, float]:
    """买入：滑点抬高成交价，手续费按成交额扣除。"""
    exec_price = mid * (1.0 + slippage)
    fee = cash * commission
    investable = max(0.0, cash - fee)
    qty = investable / exec_price if exec_price > 0 else 0.0
    return qty, exec_price, fee, slippage * mid * qty


def _exec_sell(qty: float, mid: float, commission: float, slippage: float) -> tuple[float, float, float, float]:
    """卖出：滑点压低成交价，手续费按成交额扣除。"""
    exec_price = mid * (1.0 - slippage)
    gross = qty * exec_price
    fee = gross * commission
    cash = gross - fee
    return cash, exec_price, fee, slippage * mid * qty


def _simulate(bars: List[Bar], result, config: Dict[str, Any]) -> Dict[str, Any]:
    """按买卖点模拟持仓，分别计算毛收益与扣摩擦后的净收益。"""
    initial = float(config.get("initial_capital", 1.0))
    commission = float(config.get("commission", 0.0))
    slippage = float(config.get("slippage", 0.0))

    cash = initial
    gross_cash = initial
    position = 0.0
    gross_position = 0.0
    entry_price = 0.0
    gross_entry = 0.0

    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = [initial]
    gross_equity_curve: List[float] = [initial]

    total_commission = 0.0
    total_slippage = 0.0

    buy_kinds = {TradePointType.BUY1, TradePointType.BUY2, TradePointType.BUY3}
    sell_kinds = {TradePointType.SELL1, TradePointType.SELL2, TradePointType.SELL3}

    points = sorted(result.trade_points, key=lambda p: p.bar_index)
    point_by_bar = {p.bar_index: p for p in points}

    for bar in bars:
        tp = point_by_bar.get(bar.index)
        if tp and tp.kind in buy_kinds and position == 0 and cash > 0:
            qty, exec_p, fee, slip_cost = _exec_buy(cash, bar.close, commission, slippage)
            position = qty
            entry_price = exec_p
            cash = 0.0
            total_commission += fee
            total_slippage += slip_cost

            gross_position = gross_cash / bar.close if bar.close > 0 else 0.0
            gross_entry = bar.close
            gross_cash = 0.0

            trades.append(
                {
                    "side": "buy",
                    "bar_index": bar.index,
                    "price": bar.close,
                    "exec_price": round(exec_p, 4),
                    "commission": round(fee, 6),
                    "slippage_cost": round(slip_cost, 6),
                    "kind": tp.kind.value,
                    "reason": tp.reason,
                }
            )
        elif tp and tp.kind in sell_kinds and position > 0:
            cash, exec_p, fee, slip_cost = _exec_sell(position, bar.close, commission, slippage)
            pnl_gross = (bar.close - gross_entry) / gross_entry if gross_entry > 0 else 0.0
            pnl_net = (exec_p - entry_price) / entry_price if entry_price > 0 else 0.0
            total_commission += fee
            total_slippage += slip_cost

            gross_cash = gross_position * bar.close
            gross_position = 0.0

            trades.append(
                {
                    "side": "sell",
                    "bar_index": bar.index,
                    "price": bar.close,
                    "exec_price": round(exec_p, 4),
                    "commission": round(fee, 6),
                    "slippage_cost": round(slip_cost, 6),
                    "pnl_gross": round(pnl_gross, 6),
                    "pnl": round(pnl_net, 6),
                    "kind": tp.kind.value,
                    "reason": tp.reason,
                }
            )
            position = 0.0
            entry_price = 0.0
            gross_entry = 0.0

        mark = position * bar.close if position > 0 else cash
        gross_mark = gross_position * bar.close if gross_position > 0 else gross_cash
        equity_curve.append(mark)
        gross_equity_curve.append(gross_mark)

    if position > 0 and bars:
        last = bars[-1].close
        cash, _, fee, slip_cost = _exec_sell(position, last, commission, slippage)
        total_commission += fee
        total_slippage += slip_cost
        gross_cash = gross_position * last
        position = 0.0
        gross_position = 0.0

    def _stats(curve: List[float]) -> tuple[float, float, float]:
        total_ret = (curve[-1] - initial) / initial if initial > 0 else 0.0
        rets = [(curve[i] - curve[i - 1]) / curve[i - 1] for i in range(1, len(curve)) if curve[i - 1] > 0]
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            if peak > 0:
                max_dd = min(max_dd, (v - peak) / peak)
        if len(rets) > 1:
            mean_r = sum(rets) / len(rets)
            var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
            sharpe = (mean_r / math.sqrt(var)) * math.sqrt(252 * 288) if var > 0 else 0.0
        else:
            sharpe = 0.0
        return total_ret, max_dd, sharpe

    net_ret, max_dd, sharpe = _stats(equity_curve)
    gross_ret, gross_dd, gross_sharpe = _stats(gross_equity_curve)

    sell_trades = [t for t in trades if t["side"] == "sell"]
    wins_gross = [t for t in sell_trades if t.get("pnl_gross", 0) > 0]
    wins_net = [t for t in sell_trades if t.get("pnl", 0) > 0]

    friction_drag = gross_ret - net_ret

    return {
        "trades": trades,
        "metrics": {
            "sharpe": round(sharpe, 4),
            "sharpe_gross": round(gross_sharpe, 4),
            "total_return": round(net_ret, 6),
            "total_return_gross": round(gross_ret, 6),
            "friction_drag": round(friction_drag, 6),
            "total_commission": round(total_commission, 6),
            "total_slippage_cost": round(total_slippage, 6),
            "max_drawdown": round(max_dd, 6),
            "max_drawdown_gross": round(gross_dd, 6),
            "win_rate": round(len(wins_net) / len(sell_trades), 4) if sell_trades else 0.0,
            "win_rate_gross": round(len(wins_gross) / len(sell_trades), 4) if sell_trades else 0.0,
            "total_trades": len(sell_trades),
            "signals_count": len(result.trade_points),
            "strokes_count": len(result.strokes),
            "fractals_count": len(result.fractals),
            "pivots_count": len(result.pivots),
            "commission_rate": commission,
            "slippage_rate": slippage,
        },
        "structure": {
            "trade_point_kinds": sorted({tp.kind.value for tp in result.trade_points}),
        },
    }


def run_chanlun_backtest(bars: List[Bar], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """缠论结构分析 + 含摩擦成本的信号回测主入口。"""
    config = config or {}
    standard_name = config.get("stroke_standard", "new")
    standard = StrokeStandard.OLD if standard_name == "old" else StrokeStandard.NEW

    result = analyze(bars, stroke_standard=standard)
    out = _simulate(bars, result, config)
    out["structure"]["stroke_standard"] = standard.value
    out["audit"] = {
        "engine": "chanlun",
        "version": "0.1.0",
        "stroke_standard": standard.value,
        "bars": len(bars),
        "commission": config.get("commission", 0),
        "slippage": config.get("slippage", 0),
        "initial_capital": config.get("initial_capital", 1.0),
    }
    return out
