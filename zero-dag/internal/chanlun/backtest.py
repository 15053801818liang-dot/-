"""回测 — 缠论信号 → 模拟交易"""
import numpy as np
import pandas as pd


def run_backtest(bars: list, chanlun_result: dict, initial_capital: float = 100000.0) -> dict:
    signals = chanlun_result.get("signals", [])
    if not signals:
        return {
            "error": "no signals", "initial_capital": initial_capital,
            "final_capital": initial_capital, "total_return_pct": 0.0,
            "sharpe_ratio": 0.0, "win_rate_pct": 0.0, "num_trades": 0,
            "num_signals": 0, "trades": [],
        }

    prices = [float(b.close) for b in bars]
    capital = initial_capital
    position = 0
    trades = []
    equity = [capital]

    for sig in sorted(signals, key=lambda s: s["bi_index"]):
        idx = min(sig["bi_index"], len(prices) - 1)
        price = prices[idx]

        if sig["type"] == "bottom_divergence" and position == 0:
            position = capital / price * 0.95
            capital *= 0.05
            trades.append({"action": "BUY", "price": round(price, 2), "capital": round(capital, 2)})
        elif sig["type"] == "top_divergence" and position > 0:
            capital += position * price
            position = 0
            trades.append({"action": "SELL", "price": round(price, 2), "capital": round(capital, 2)})
            equity.append(capital)

    final = capital + position * prices[-1]
    ret = (final - initial_capital) / initial_capital * 100
    sharpe = 0.0
    if len(equity) > 1:
        r = pd.Series(equity).pct_change().dropna()
        sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0
    sells = [t for t in trades if t["action"] == "SELL"]
    wins = sum(1 for i, t in enumerate(trades) if t["action"] == "SELL" and i > 0 and t["capital"] > trades[i - 1]["capital"])
    win_rate = wins / max(len(sells), 1) * 100

    return {
        "initial_capital": initial_capital,
        "final_capital": round(final, 2),
        "total_return_pct": round(ret, 2),
        "sharpe_ratio": round(sharpe, 2),
        "win_rate_pct": round(win_rate, 1),
        "num_trades": len(trades),
        "num_signals": len(signals),
        "trades": trades,
    }
