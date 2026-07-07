"""
赚钱系统V3 — 改进回测
================================
改进点:
  1. 复利计算 PnL (compound, 非简单求和)
  2. 顺序交易 — 去掉滑动窗口重叠 (持仓期间不重复开仓)
  3. 2022年独立回测 + drawdown曲线
"""
import sys, os, csv
from collections import defaultdict
import numpy as np

csv.field_size_limit(10**7)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
sys.stdout.reconfigure(encoding='utf-8')

from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
from bi_v0_1 import find_fenxing, find_bi
from duan_v0_1 import find_duan
from zoushi_type import classify_zoushi
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points

# ═══ V3 参数 ═══
TP = 3.5
SL = 1.0
W = 2000
S = 400
WIN = 240       # 5min bars = 20h 持仓上限
MIN_BARS = 5
CACHE = 'data/cache'
SYMS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']


def load(sym):
    p = os.path.join(CACHE, f'{sym}_5min.csv')
    if not os.path.exists(p):
        return []
    bars = []
    with open(p, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            bar = {}
            for k, v in row.items():
                if k == 'date':
                    bar[k] = v
                elif v is None or v == '':
                    bar[k] = 0.0
                else:
                    try:
                        bar[k] = float(v)
                    except:
                        bar[k] = 0.0
            bars.append(bar)
    return bars


def generate_signals(bars, year_filter=None):
    """从滑动窗口生成所有候选信号（阿娇管线）"""
    signals = []
    seen_exact = set()

    for seg in range(0, len(bars) - W - WIN, S):
        seg_end = seg + W
        window = bars[seg:seg_end]

        # 年过滤
        if year_filter:
            wy = window[-1].get('date', '')[:4]
            if wy != year_filter:
                continue

        # 阿娇管线
        bh = kxian_baohan([dict(b) for b in window])
        for b in bh:
            b['_orig_date'] = b.get('date', '')
        fx = find_fenxing(bh)
        bi = find_bi(bh, fx, MIN_BARS)
        if len(bi) < 3: continue
        du = find_duan(bi)
        if len(du) < 3: continue
        zs = find_zhongshu_from_duan(du)
        if not zs: continue
        c = [b['close'] for b in window]; h = [b['high'] for b in window]; l = [b['low'] for b in window]
        div = find_divergence(du, zs, c, h, l, level='5min',
                              zoushi_type=classify_zoushi(zs).get('type', ''))
        pts = detect_buy_sell_points(div, None, bi, du, level='5min')

        for pk in ['first_buy', 'first_sell']:
            pt = pts.get(pk)
            if not pt or pt.status not in ('confirmed', 'candidate') or not pt.point_type:
                continue
            entry = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
            if entry <= 0: continue
            d = 'buy' if 'buy' in pk else 'sell'
            bt = window[-1].get('date', '')

            # 找信号在 bars 中的确切位置
            entry_idx = seg_end - 1  # 默认窗口末
            for i in range(seg_end - 1, seg, -1):
                if abs(bars[i]['close'] - entry) / entry < 0.005:
                    entry_idx = i
                    break

            key = f"{d}|{seg}|{entry:.4f}"
            if key in seen_exact:
                continue
            seen_exact.add(key)

            # 前向模拟: 找TP/SL击穿点
            fwd = bars[seg_end:seg_end + WIN]
            if len(fwd) < 5: continue

            tp_price = entry * (1 + TP/100) if d == 'buy' else entry * (1 - TP/100)
            sl_price = entry * (1 - SL/100) if d == 'buy' else entry * (1 + SL/100)

            hit = 'timeout'
            exit_p = fwd[-1]['close']
            exit_idx = seg_end + len(fwd) - 1

            for i, b in enumerate(fwd):
                if d == 'buy':
                    tp_hit = b['high'] >= tp_price; sl_hit = b['low'] <= sl_price
                else:
                    tp_hit = b['low'] <= tp_price; sl_hit = b['high'] >= sl_price
                if tp_hit and not sl_hit:
                    hit = 'tp'; exit_p = tp_price; exit_idx = seg_end + i; break
                if sl_hit and not tp_hit:
                    hit = 'sl'; exit_p = sl_price; exit_idx = seg_end + i; break
                if tp_hit and sl_hit:
                    hit = 'tp'; exit_p = tp_price; exit_idx = seg_end + i; break

            pnl = (exit_p - entry) / entry * 100 if d == 'buy' else (entry - exit_p) / entry * 100

            signals.append({
                'dir': d,
                'entry': entry,
                'entry_idx': entry_idx,
                'exit': exit_p,
                'exit_idx': exit_idx,
                'pnl': round(pnl, 3),
                'hit': hit,
                'date': bt,
                'year': bt[:4],
            })

    # 按 entry_idx 排序
    signals.sort(key=lambda s: s['entry_idx'])
    return signals


def sequential_backtest(bars, signals):
    """顺序回测：不重叠持仓，复利计算"""
    trades = []
    equity = 1.0
    equity_curve = []  # [(bar_idx, equity, drawdown_pct)]
    peak = 1.0

    next_signal_idx = 0
    in_trade_until = -1  # bar index where current trade exits

    for bar_idx in range(len(bars)):
        # 记录权益曲线（每日采样，减少数据量）
        if bar_idx % 288 == 0:  # ~daily (288 × 5min = 24h)
            dd = (equity - peak) / peak * 100
            equity_curve.append({
                'idx': bar_idx,
                'date': bars[bar_idx]['date'][:10],
                'equity': round(equity, 6),
                'dd': round(dd, 2),
            })

        # 如果还在持仓中，检查是否已到退出点
        if bar_idx < in_trade_until:
            continue

        # 找下一个未过期信号
        while next_signal_idx < len(signals) and signals[next_signal_idx]['entry_idx'] < bar_idx:
            next_signal_idx += 1

        if next_signal_idx >= len(signals):
            break

        sig = signals[next_signal_idx]
        if sig['entry_idx'] < bar_idx:
            next_signal_idx += 1
            continue

        # 接受这个信号，开仓
        pnl = sig['pnl']
        equity *= (1 + pnl / 100)
        if equity > peak:
            peak = equity

        trades.append({**sig, 'equity_after': round(equity, 6)})
        in_trade_until = sig['exit_idx']
        next_signal_idx += 1

    # 尾部补充权益曲线
    final_dd = (equity - peak) / peak * 100
    equity_curve.append({
        'idx': len(bars) - 1,
        'date': bars[-1]['date'][:10] if bars else '',
        'equity': round(equity, 6),
        'dd': round(final_dd, 2),
    })

    compound_pnl = (equity - 1) * 100
    max_dd = min(ec['dd'] for ec in equity_curve) if equity_curve else 0

    return trades, compound_pnl, max_dd, equity_curve


def print_trades_summary(sym, trades, compound_pnl, max_dd, year_label=None):
    """打印单个币种的交易总结"""
    label = f" ({year_label})" if year_label else ""
    if not trades:
        print(f"  {sym}{label}: 0笔")
        return

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    wr = len(wins) / len(trades) * 100
    tp_n = sum(1 for t in trades if t['hit'] == 'tp')
    sl_n = sum(1 for t in trades if t['hit'] == 'sl')
    ratio = tp_n / max(sl_n, 1)
    win_avg = np.mean([t['pnl'] for t in wins]) if wins else 0
    loss_avg = np.mean([t['pnl'] for t in losses]) if losses else 0

    # 逐年
    years = sorted(set(t['year'] for t in trades))

    print(f"  {sym}{label}: {len(trades)}笔 | WR={wr:.0f}% | "
          f"复利PnL={compound_pnl:+.1f}% | 盈亏比={ratio:.1f}:1 | "
          f"最大回撤={max_dd:.1f}%")
    print(f"    赢均={win_avg:.2f}% 亏均={loss_avg:.2f}%")

    for y in years:
        yt = [t for t in trades if t['year'] == y]
        ypnl_simple = sum(t['pnl'] for t in yt)
        ywr = sum(1 for t in yt if t['pnl'] > 0) / len(yt) * 100
        icon = '✅' if ypnl_simple > 0 else '❌'
        print(f"    {icon} {y}: {len(yt)}笔 WR={ywr:.0f}% 简单PnL={ypnl_simple:+.1f}%")

    return trades


def print_drawdown_curve(equity_curve, title="Drawdown曲线"):
    """打印权益曲线和回撤摘要"""
    if not equity_curve:
        print("  无数据")
        return

    dds = [ec['dd'] for ec in equity_curve]
    equities = [ec['equity'] for ec in equity_curve]

    print(f"\n  {title}:")
    print(f"  起始权益: {equities[0]:.4f} → 最终权益: {equities[-1]:.4f}")
    print(f"  最大回撤: {min(dds):.1f}%")
    print(f"  回撤>5%月份数: {sum(1 for d in dds if d < -5)}")
    print(f"  回撤>10%月份数: {sum(1 for d in dds if d < -10)}")

    # 找最大回撤区间
    peak_idx = 0; peak_val = equities[0]
    worst_dd = 0; worst_start = 0; worst_end = 0
    for i, ec in enumerate(equity_curve):
        if ec['equity'] > peak_val:
            peak_val = ec['equity']
            peak_idx = i
        dd = (ec['equity'] - peak_val) / peak_val * 100
        if dd < worst_dd:
            worst_dd = dd
            worst_start = equity_curve[peak_idx]['date']
            worst_end = ec['date']

    print(f"  最深回撤区间: {worst_start} → {worst_end} ({worst_dd:.1f}%)")

    # ASCII 曲线
    print(f"\n  权益曲线 (每日采样):")
    width = 60
    min_e = min(equities); max_e = max(equities)
    if max_e > min_e:
        normalized = [int((e - min_e) / (max_e - min_e) * (width - 1)) for e in equities]
    else:
        normalized = [0] * len(equities)

    # 每10个采样点打印一行
    step = max(1, len(normalized) // 30)
    for i in range(0, len(normalized), step):
        bar = '█' * normalized[i] + '░' * (width - normalized[i])
        dd_str = f"DD={dds[i]:.0f}%" if dds[i] < -3 else ""
        date_str = equity_curve[i]['date']
        print(f"  {date_str} │{bar}│ {equities[i]:.3f} {dd_str}")


# ═══ 主程序 ═══
print("=" * 75)
print("  赚钱系统 V3 — 改进回测 (复利 + 顺序交易 + Drawdown)")
print(f"  TP={TP}% SL={SL}%  纯阿娇信号  固定仓位100%")
print("=" * 75)

all_trades = []

for sym in SYMS:
    print(f"\n{'─' * 75}")
    print(f"  {sym}")
    print(f"{'─' * 75}")

    bars = load(sym)
    if not bars:
        print(f"  ❌ 无数据")
        continue

    print(f"  总数据: {len(bars)}根K线 ({bars[0]['date'][:10]} → {bars[-1]['date'][:10]})")

    # ── 2023-2026 主回测 ──
    print(f"\n  【2023-2026 主回测】")
    signals = generate_signals(bars)  # 不传year_filter，生成全部信号
    signals = [s for s in signals if s['year'] >= '2023']  # 只要2023+

    # 去重叠: 顺序交易
    trades, compound_pnl, max_dd, equity_curve = sequential_backtest(bars, signals)
    all_trades.extend(trades)
    print_trades_summary(sym, trades, compound_pnl, max_dd)

    # ── 2022 独立回测 + drawdown ──
    print(f"\n  【2022 独立回测 + Drawdown曲线】")
    signals_2022 = generate_signals(bars, year_filter='2022')
    trades_2022, compound_pnl_2022, max_dd_2022, equity_curve_2022 = sequential_backtest(bars, signals_2022)
    print_trades_summary(sym, trades_2022, compound_pnl_2022, max_dd_2022, year_label='2022')
    print_drawdown_curve(equity_curve_2022, title=f"{sym} 2022 Drawdown")


# ═══ 总汇总 ═══
print(f"\n{'=' * 75}")
print(f"  📊 三年总汇总 (2023-2026, 复利+顺序交易)")
print(f"{'=' * 75}")

if all_trades:
    wins = [t for t in all_trades if t['pnl'] > 0]
    losses = [t for t in all_trades if t['pnl'] < 0]
    wr = len(wins) / len(all_trades) * 100
    tp_n = sum(1 for t in all_trades if t['hit'] == 'tp')
    sl_n = sum(1 for t in all_trades if t['hit'] == 'sl')

    # 按币种复利汇总
    print(f"\n  总信号: {len(all_trades)}笔 (去重叠后)")
    print(f"  胜率: {wr:.0f}%")
    print(f"  TP/SL比: {tp_n}:{sl_n} = {tp_n/max(sl_n,1):.1f}:1")
    print(f"  赢均: {np.mean([t['pnl'] for t in wins]):.2f}%")
    print(f"  亏均: {np.mean([t['pnl'] for t in losses]):.2f}%")

    # 逐年
    years = sorted(set(t['year'] for t in all_trades))
    print(f"\n  逐年简单求和PnL:")
    for y in years:
        yt = [t for t in all_trades if t['year'] == y]
        yp = sum(t['pnl'] for t in yt)
        ywr = sum(1 for t in yt if t['pnl'] > 0) / len(yt) * 100
        print(f"    {y}: {len(yt)}笔 WR={ywr:.0f}% 简单PnL={yp:+.1f}%")

print(f"\n✅ 完成")
