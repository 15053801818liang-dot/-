"""
资金管理系统 — 仓位计算 + 风险控制 + 回撤熔断
=======================================
基于赚钱系统v3 实盘验证数据：
  胜率 52.7% | 赢均 +3.15% | 亏均 -0.98% | 最大回撤 11.8%
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# 参数配置
# ═══════════════════════════════════════════════════════════════

@dataclass
class StrategyParams:
    """策略参数"""
    win_rate: float = 0.527          # 胜率 52.7%
    avg_win: float = 3.15             # 赢均 3.15%
    avg_loss: float = -0.98           # 亏均 -0.98%
    max_drawdown: float = 11.8        # 最大回撤 11.8%
    tp_pct: float = 3.5               # 止盈%
    sl_pct: float = 1.0               # 止损%
    signals_per_coin_per_year: int = 46  # 每年/币 信号数


@dataclass
class AccountConfig:
    """账户配置"""
    initial_balance: float = 10000.0   # 初始资金（USDT）
    max_concurrent_positions: int = 3   # 最大同时持仓数
    max_daily_loss: float = 5.0         # 单日最大亏损%
    max_total_drawdown: float = 15.0    # 总回撤熔断%
    commission_pct: float = 0.04        # 手续费%（币安现货 0.04%）


# ═══════════════════════════════════════════════════════════════
# 仓位计算
# ═══════════════════════════════════════════════════════════════

class PositionSizer:
    """
    仓位计算器
    支持：固定比例 / 凯利公式 / 保守凯利
    """

    def __init__(self, strategy: StrategyParams, account: AccountConfig):
        self.strategy = strategy
        self.account = account
        self._trade_log: List[Dict] = []
        self._current_balance = account.initial_balance
        self._peak_balance = account.initial_balance

    @property
    def current_balance(self) -> float:
        return self._current_balance

    def reset(self, balance: float = 0):
        """重置到初始状态"""
        self._current_balance = balance or self.account.initial_balance
        self._peak_balance = self._current_balance
        self._trade_log = []

    # ── 核心仓位公式 ──

    def kelly_fraction(self) -> float:
        """
        凯利公式：f* = (p*b - q) / b
        p = 胜率, q = 1-p, b = 盈亏比（赢均/亏均绝对值）
        """
        p = self.strategy.win_rate
        q = 1 - p
        b = abs(self.strategy.avg_win / self.strategy.avg_loss) if self.strategy.avg_loss != 0 else 1
        kelly = (p * b - q) / b
        return max(0.0, min(kelly, 1.0))  # 截断 0-1

    def half_kelly(self) -> float:
        """半凯利 — 更安全"""
        return self.kelly_fraction() * 0.5

    def quarter_kelly(self) -> float:
        """四分之一凯利 — 最保守"""
        return self.kelly_fraction() * 0.25

    def fixed_risk(self, risk_pct: float = 1.0) -> float:
        """
        固定比例风险：每次承担账户余额的 risk_pct
        返回仓位 USDT 金额
        """
        return self._current_balance * risk_pct / 100

    def calculate_position(self, method: str = 'half_kelly') -> Dict:
        """
        计算本次交易仓位
        返回：{position, risk_amount, method, balance, metadata}
        """
        balance = self._current_balance

        if method == 'kelly':
            fraction = self.kelly_fraction()
        elif method == 'half_kelly':
            fraction = self.half_kelly()
        elif method == 'quarter_kelly':
            fraction = self.quarter_kelly()
        elif method == 'fixed_1pct':
            fraction = self.fixed_risk(1.0) / balance
        elif method == 'fixed_2pct':
            fraction = self.fixed_risk(2.0) / balance
        else:
            fraction = self.half_kelly()

        # 计算仓位金额
        position = balance * fraction
        risk_amount = position * self.strategy.sl_pct / 100

        # 并发限制（若有持仓记录）
        active_positions = len([t for t in self._trade_log
                                if t.get('status') == 'open'])
        if active_positions >= self.account.max_concurrent_positions:
            return {
                "position": 0, "reason": "max_concurrent",
                "balance": balance, "method": method,
                "fraction": 0, "risk_amount": 0
            }

        return {
            "position": round(position, 2),
            "risk_amount": round(risk_amount, 2),
            "method": method,
            "fraction": round(fraction * 100, 2),
            "balance": round(balance, 2),
            "active_positions": active_positions,
            "max_concurrent": self.account.max_concurrent_positions,
        }

    # ── 交易记录 ──

    def record_trade(self, pnl_pct: float, method: str = 'half_kelly',
                     direction: str = 'buy', symbol: str = 'BTCUSDT'):
        """
        记录一笔已平仓交易，更新余额
        pnl_pct: 本次交易的盈亏%
        """
        pos_info = self.calculate_position(method)
        if pos_info['position'] <= 0:
            return None

        position_usdt = pos_info['position']
        pnl_usdt = position_usdt * pnl_pct / 100
        new_balance = self._current_balance + pnl_usdt

        # 检查每日亏损限制
        today_trades = [t for t in self._trade_log
                        if t.get('date', '')[:10] == datetime.now().strftime('%Y-%m-%d')]
        today_pnl = sum(t['pnl_usdt'] for t in today_trades)
        daily_loss_limit = -self.account.initial_balance * self.account.max_daily_loss / 100

        # 检查总回撤熔断
        if new_balance > self._peak_balance:
            self._peak_balance = new_balance
        current_dd = (self._peak_balance - new_balance) / self._peak_balance * 100

        trade_record = {
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "symbol": symbol,
            "direction": direction,
            "method": method,
            "balance_before": round(self._current_balance, 2),
            "position_usdt": round(position_usdt, 2),
            "pnl_pct": pnl_pct,
            "pnl_usdt": round(pnl_usdt, 2),
            "balance_after": round(new_balance, 2),
            "drawdown_pct": round(current_dd, 2),
            "status": "closed",
        }

        self._current_balance = new_balance
        self._trade_log.append(trade_record)
        return trade_record

    # ── 熔断检查 ──

    def check_fuses(self) -> Dict:
        """检查是否触发熔断"""
        # 总回撤熔断
        dd = (self._peak_balance - self._current_balance) / self._peak_balance * 100
        dd_triggered = dd >= self.account.max_total_drawdown

        # 当日亏损熔断
        today_trades = [t for t in self._trade_log
                        if t.get('date', '')[:10] == datetime.now().strftime('%Y-%m-%d')]
        today_pnl = sum(t['pnl_usdt'] for t in today_trades) if today_trades else 0
        daily_loss_pct = today_pnl / self.account.initial_balance * 100
        daily_triggered = daily_loss_pct <= -self.account.max_daily_loss

        return {
            "drawdown": round(dd, 2),
            "drawdown_triggered": dd_triggered,
            "today_pnl_pct": round(daily_loss_pct, 2),
            "daily_triggered": daily_triggered,
            "stopped": dd_triggered or daily_triggered,
            "balance": round(self._current_balance, 2),
            "peak": round(self._peak_balance, 2),
        }

    # ── 报告 ──

    def report(self) -> str:
        """生成资金管理报告"""
        kelly = self.kelly_fraction()
        half = self.half_kelly()
        quarter = self.quarter_kelly()
        fixed1 = self.fixed_risk(1.0)
        fixed2 = self.fixed_risk(2.0)
        fuses = self.check_fuses()

        lines = [
            f"\n{'='*60}",
            f"  资金管理报告",
            f"  余额: ${self._current_balance:.2f} | 峰值: ${self._peak_balance:.2f}",
            f"{'='*60}",
            "",
            f"  【策略参数】",
            f"    胜率 {self.strategy.win_rate*100:.1f}%  赢均 +{self.strategy.avg_win:.2f}%  亏均 {self.strategy.avg_loss:.2f}%",
            f"    盈亏比 {abs(self.strategy.avg_win/self.strategy.avg_loss):.2f}:1",
            "",
            f"  【仓位方案对比】",
            f"    {'方法':<20s} {'比例':>8s} {'1万U仓位':>12s} {'风险U':>10s}",
            f"    {'─'*52}",
            f"    {'满凯利 (Kelly)':<20s} {kelly*100:>6.2f}%  {self._current_balance*kelly:>9.2f}  {self._current_balance*kelly*self.strategy.sl_pct/100:>8.2f}",
            f"    {'半凯利 (Half Kelly)':<20s} {half*100:>6.2f}%  {self._current_balance*half:>9.2f}  {self._current_balance*half*self.strategy.sl_pct/100:>8.2f}",
            f"    {'四分之一凯利':<20s} {quarter*100:>6.2f}%  {self._current_balance*quarter:>9.2f}  {self._current_balance*quarter*self.strategy.sl_pct/100:>8.2f}",
            f"    {'固定1%风险':<20s} {'1.00%':>8s} {fixed1:>9.2f}  {fixed1*self.strategy.sl_pct/100:>8.2f}",
            f"    {'固定2%风险':<20s} {'2.00%':>8s} {fixed2:>9.2f}  {fixed2*self.strategy.sl_pct/100:>8.2f}",
            "",
            f"  【风控状态】",
            f"    {'当前回撤':<20s} {fuses['drawdown']:.1f}%  ({'⚠️ 熔断' if fuses['drawdown_triggered'] else '正常'})",
            f"    {'回撤熔断线':<20s} {self.account.max_total_drawdown:.0f}%",
            f"    {'当日盈亏':<20s} {fuses['today_pnl_pct']:.1f}%  ({'⚠️ 熔断' if fuses['daily_triggered'] else '正常'})",
            f"    {'单日亏损上限':<20s} {self.account.max_daily_loss:.0f}%",
            f"    {'最大并发持仓':<20s} {self.account.max_concurrent_positions}",
            "",
            f"  【推荐方案】",
        ]
        if kelly > 0.5:
            lines.append(f"    全凯利 {kelly*100:.0f}% 风险偏高，建议半凯利 {half*100:.1f}%")
        else:
            lines.append(f"    半凯利 {half*100:.1f}% — 平衡风险收益")
        lines.append(f"    每笔风险控制在余额的 {half*self.strategy.sl_pct:.2f}% 以内")
        lines.append(f"    三币同时持仓时总风险约 {half*self.strategy.sl_pct*3:.2f}%")
        lines.append(f"{'='*60}")
        return "\n".join(lines)

    # ── 蒙特卡洛模拟 ──

    def monte_carlo(self, num_trades: int = 1000, simulations: int = 10000,
                    method: str = 'half_kelly') -> Dict:
        """
        蒙特卡洛模拟 — 验证资金曲线稳定性
        """
        import random
        import numpy as np

        final_equities = []
        max_dd_list = []
        bankruptcies = 0

        for _ in range(simulations):
            balance = self.account.initial_balance
            peak = balance
            max_dd = 0
            bankrupt = False

            for _ in range(num_trades):
                pos = balance * (self.half_kelly() if method == 'half_kelly' else self.quarter_kelly())
                if pos <= 0:
                    bankrupt = True
                    break

                # 随机抽取赢/亏
                if random.random() < self.strategy.win_rate:
                    pnl_pct = random.uniform(self.strategy.avg_win * 0.5, self.strategy.avg_win * 1.5)
                else:
                    pnl_pct = random.uniform(self.strategy.avg_loss * 1.5, self.strategy.avg_loss * 0.5)

                pnl_usdt = pos * pnl_pct / 100
                balance += pnl_usdt
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100
                if dd > max_dd:
                    max_dd = dd
                if balance <= 0:
                    bankrupt = True
                    break

            final_equities.append(balance)
            max_dd_list.append(max_dd)
            if bankrupt:
                bankruptcies += 1

        final_equities.sort()
        max_dd_list.sort()

        return {
            "method": method,
            "trades_per_sim": num_trades,
            "simulations": simulations,
            "median_final": round(np.median(final_equities), 2),
            "mean_final": round(np.mean(final_equities), 2),
            "p10_final": round(final_equities[int(simulations * 0.1)], 2),
            "p90_final": round(final_equities[int(simulations * 0.9)], 2),
            "median_dd": round(np.median(max_dd_list), 2),
            "p95_dd": round(max_dd_list[int(simulations * 0.95)], 2),
            "max_dd": round(max(max_dd_list), 2),
            "bankruptcy_rate": round(bankruptcies / simulations * 100, 2),
        }


# ═══ CLI 入口 ═══

def report(initial_balance: float = 10000):
    """输出资金管理方案"""
    strategy = StrategyParams()
    account = AccountConfig(initial_balance=initial_balance)
    sizer = PositionSizer(strategy, account)
    print(sizer.report())
    return sizer


def simulate(initial_balance: float = 10000, method: str = 'half_kelly',
             trades: int = 1000, sims: int = 10000):
    """运行蒙特卡洛模拟"""
    strategy = StrategyParams()
    account = AccountConfig(initial_balance=initial_balance)
    sizer = PositionSizer(strategy, account)
    result = sizer.monte_carlo(trades, sims, method)

    print(f"\n{'='*60}")
    print(f"  蒙特卡洛模拟 — {method}")
    print(f"  {trades}笔 × {sims}次")
    print(f"{'='*60}")
    print(f"  初始资金:      ${initial_balance:>8.2f}")
    print(f"  {'─'*40}")
    print(f"  中位数终值:    ${result['median_final']:>8.2f}")
    print(f"  均值终值:      ${result['mean_final']:>8.2f}")
    print(f"  P10 (最差10%): ${result['p10_final']:>8.2f}")
    print(f"  P90 (最好10%): ${result['p90_final']:>8.2f}")
    print(f"  {'─'*40}")
    print(f"  中位数回撤:    {result['median_dd']:>7.2f}%")
    print(f"  P95 回撤:      {result['p95_dd']:>7.2f}%")
    print(f"  最大回撤:      {result['max_dd']:>7.2f}%")
    print(f"  破产率:        {result['bankruptcy_rate']:>7.2f}%")
    print(f"{'='*60}")
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'simulate':
        balance = float(sys.argv[2]) if len(sys.argv) > 2 else 10000
        method = sys.argv[3] if len(sys.argv) > 3 else 'half_kelly'
        trades = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
        sims = int(sys.argv[5]) if len(sys.argv) > 5 else 10000
        simulate(balance, method, trades, sims)
    else:
        report()
