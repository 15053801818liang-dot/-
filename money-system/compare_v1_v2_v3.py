"""
赚钱系统 V1 vs V2 vs V3 — 三年对比测试
======================================
同数据、同阿娇信号管线，三套TP/SL/过滤规则横向对比
时间: 2023-01-01 → 2026-06-22
币种: BTC, ETH, SOL (仅此三个有全量3年+数据)
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

# ═══ 共享参数 ═══
W = 2000       # 分析窗口
S = 400        # 步长
WIN = 240      # 前向跟踪 (240×5min = 20h)
MIN_BARS = 5   # 笔最小K线
CACHE = 'data/cache'
SYMS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# ═══ 三套规则 ═══
RULES = {
    'V1': {'tp': 1.5, 'sl': 5.0, 'gate': 'none',     'desc': 'TP=1.5% SL=5.0% 纯阿娇'},
    'V2': {'tp': 1.0, 'sl': 4.0, 'gate': 'structural', 'desc': 'TP=1.0% SL=结构/4% bonus≥1'},
    'V3': {'tp': 3.5, 'sl': 1.0, 'gate': 'none',     'desc': 'TP=3.5% SL=1.0% 纯阿娇'},
}

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


def run_all_systems(sym):
    """跑一次阿娇管线，三套规则分别结算"""
    bars = load(sym)
    if not bars or len(bars) < W + WIN:
        return None

    # 各系统独立交易列表
    trades = {k: [] for k in RULES}
    seen = {k: set() for k in RULES}

    for seg in range(0, len(bars) - W - WIN, S):
        seg_end = seg + W
        window = bars[seg:seg_end]

        # ── 阿娇管线（所有系统共用） ──
        bh = kxian_baohan([dict(b) for b in window])
        for b in bh:
            b['_orig_date'] = b.get('date', '')
        fx = find_fenxing(bh)
        bi = find_bi(bh, fx, MIN_BARS)
        if len(bi) < 3:
            continue
        du = find_duan(bi)
        if len(du) < 3:
            continue
        zs = find_zhongshu_from_duan(du)
        if not zs:
            continue
        c = [b['close'] for b in window]
        h = [b['high'] for b in window]
        l = [b['low'] for b in window]
        div = find_divergence(du, zs, c, h, l, level='5min',
                              zoushi_type=classify_zoushi(zs).get('type', ''))
        pts = detect_buy_sell_points(div, None, bi, du, level='5min')

        # ── V2专用：30min共振 + 趋势方向 ──
        align_bonus = False
        seg30_start = max(0, seg - 800)
        bars30 = bars[seg30_start:seg_end]
        for b30 in bars30:
            b30['_orig_date'] = b30.get('date', '')
        bh30 = kxian_baohan(bars30)
        fx30 = find_fenxing(bh30)
        bi30 = find_bi(bh30, fx30, 5)
        du30 = find_duan(bi30)
        zs30 = find_zhongshu_from_duan(du30)
        if zs30:
            c30 = [b['close'] for b in bars30]
            h30 = [b['high'] for b in bars30]
            l30 = [b['low'] for b in bars30]
            div30 = find_divergence(du30, zs30, c30, h30, l30, level='30min',
                                     zoushi_type=classify_zoushi(zs30).get('type', ''))
            if div30.direction == div.direction and div30.direction != 'none':
                align_bonus = True

        # V2趋势方向bonus
        trend_bonus = False
        wider = bars[max(0, seg - 2000):seg_end]
        if len(wider) > 500:
            wp = [b['close'] for b in wider]
            early = sum(wp[:100]) / 100
            late = sum(wp[-100:]) / 100
            trend_up = late > early * 1.05
            trend_down = late < early * 0.95

        # ── 遍历买卖点 ──
        for pk in ['first_buy', 'first_sell']:
            pt = pts.get(pk)
            if not pt or pt.status not in ('confirmed', 'candidate') or not pt.point_type:
                continue

            entry = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
            if entry <= 0:
                continue
            d = 'buy' if 'buy' in pk else 'sell'
            bt = window[-1].get('date', '')
            year = bt[:4]

            # ── V2专用:  revival check ──
            revival_ok = False
            rev_bonus = False
            div_end = div.segment_b.end_idx if div.segment_b else -1
            target_dir = '向上' if 'buy' in pk else '向下'
            if div_end >= 0:
                for bi2 in bi:
                    if bi2.get('from', {}).get('idx', 0) <= div_end:
                        continue
                    if target_dir in bi2.get('direction', ''):
                        revival_ok = True
                        if abs(bi2.get('from', {}).get('idx', 0) - bi2.get('to', {}).get('idx', 0)) < 8:
                            rev_bonus = True
                        break

            # V2 bonus
            bonus = (1 if align_bonus else 0) + (1 if rev_bonus else 0)
            if d == 'buy' and trend_up:
                trend_bonus = True
            elif d == 'sell' and trend_down:
                trend_bonus = True
            else:
                trend_bonus = False
            bonus_val = bonus + (1 if trend_bonus else 0)

            # V2 structural SL
            structural_sl = RULES['V2']['sl']
            if d == 'buy':
                lows = []
                for d2 in du:
                    lo = d2.get('to', {}).get('low', d2.get('from', {}).get('low', 0)) if isinstance(d2, dict) else 0
                    if lo > 0 and lo < entry:
                        lows.append(lo)
                if lows:
                    swing = max(lows)
                    risk = (entry - swing) / entry * 100
                    if 2.0 <= risk <= 8.0:
                        structural_sl = risk
                    else:
                        structural_sl = min(max(risk, 4.0), 8.0)
            else:
                highs = []
                for d2 in du:
                    hi = d2.get('to', {}).get('high', d2.get('from', {}).get('high', 0)) if isinstance(d2, dict) else 0
                    if hi > entry:
                        highs.append(hi)
                if highs:
                    swing = min(highs)
                    risk = (swing - entry) / entry * 100
                    if 2.0 <= risk <= 8.0:
                        structural_sl = risk
                    else:
                        structural_sl = min(max(risk, 4.0), 8.0)

            # ═══ 三套规则分别结算 ═══
            fwd = bars[seg_end:seg_end + WIN]
            if len(fwd) < 5:
                continue

            for version, rule in RULES.items():
                # V2 gate check
                if version == 'V2':
                    if bonus_val < 1:  # bonus≥1
                        continue
                    if not revival_ok:
                        continue
                    use_tp = rule['tp']
                    use_sl = structural_sl
                else:
                    # V1 / V3: fixed TP/SL
                    use_tp = rule['tp']
                    use_sl = rule['sl']

                key = f"{sym}|{version}|{d}|{bt}|{entry:.2f}"
                if key in seen[version]:
                    continue
                seen[version].add(key)

                tp_price = entry * (1 + use_tp / 100) if d == 'buy' else entry * (1 - use_tp / 100)
                sl_price = entry * (1 - use_sl / 100) if d == 'buy' else entry * (1 + use_sl / 100)

                hit = 'timeout'
                exit_p = fwd[-1]['close']
                for i, b in enumerate(fwd):
                    if d == 'buy':
                        tp_hit = b['high'] >= tp_price
                        sl_hit = b['low'] <= sl_price
                    else:
                        tp_hit = b['low'] <= tp_price
                        sl_hit = b['high'] >= sl_price
                    if tp_hit and not sl_hit:
                        hit = 'tp'; exit_p = tp_price; break
                    if sl_hit and not tp_hit:
                        hit = 'sl'; exit_p = sl_price; break
                    if tp_hit and sl_hit:
                        hit = 'tp'; exit_p = tp_price; break

                pnl = (exit_p - entry) / entry * 100 if d == 'buy' else (entry - exit_p) / entry * 100
                trades[version].append({
                    'sym': sym, 'year': year, 'dir': d,
                    'pnl': round(pnl, 3), 'hit': hit,
                    'entry': round(entry, 2), 'exit': round(exit_p, 2),
                    'tp': use_tp, 'sl': use_sl,
                })

    # 按年过滤: 只用2023-2026
    for v in trades:
        trades[v] = [t for t in trades[v] if t['year'] >= '2023']

    return {'trades': trades, 'bars': len(bars), 'sym': sym}


# ═══ 主程序 ═══
print("=" * 80)
print("  赚钱系统 V1 vs V2 vs V3 — BTC/ETH/SOL 三年对比 (2023-2026)")
print("=" * 80)

all_trades = {k: [] for k in RULES}

for sym in SYMS:
    r = run_all_systems(sym)
    if r is None:
        print(f"\n{sym}: ❌ 数据不足")
        continue

    print(f"\n{'─' * 80}")
    print(f"  {sym}  ({r['bars']//1000}k根K线)")
    print(f"{'─' * 80}")

    for version in ['V1', 'V2', 'V3']:
        trades = r['trades'][version]
        all_trades[version].extend(trades)

        if not trades:
            print(f"  {version}: 0笔信号")
            continue

        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] < 0]
        wr = len(wins) / len(trades) * 100
        spnl = sum(t['pnl'] for t in trades)
        years = sorted(set(t['year'] for t in trades))
        neg_years = sum(1 for y in years if sum(t['pnl'] for t in trades if t['year'] == y) < 0)

        tp_count = sum(1 for t in trades if t['hit'] == 'tp')
        sl_count = sum(1 for t in trades if t['hit'] == 'sl')
        ratio = tp_count / max(sl_count, 1)

        print(f"  {version} ({RULES[version]['desc']}): "
              f"{len(trades):>4d}笔 | WR={wr:>5.1f}% | PnL={spnl:>+7.1f}% | "
              f"盈亏比={ratio:.1f}:1 | {neg_years}/{len(years)}负年 | "
              f"赢均={np.mean([t['pnl'] for t in wins]) if wins else 0:.2f}% "
              f"亏均={np.mean([t['pnl'] for t in losses]) if losses else 0:.2f}%")

        # 逐年
        for y in years:
            yt = [t for t in trades if t['year'] == y]
            yp = sum(t['pnl'] for t in yt)
            ywr = sum(1 for t in yt if t['pnl'] > 0) / len(yt) * 100
            icon = '✅' if yp > 0 else '❌'
            print(f"      {icon} {y}: {len(yt):>3d}笔 WR={ywr:>5.0f}% PnL={yp:>+7.1f}%")


# ═══ 总汇总 ═══
print(f"\n{'=' * 80}")
print(f"  📊 三年总汇总 (2023-2026, BTC+ETH+SOL)")
print(f"{'=' * 80}")

header = f"{'':>6s} | {'笔数':>5s} | {'胜率':>6s} | {'总PnL':>8s} | {'盈亏比':>7s} | {'赢均':>6s} | {'亏均':>6s} | {'负年':>4s}"
print(header)
print("-" * 80)

for version in ['V1', 'V2', 'V3']:
    trades = all_trades[version]
    if not trades:
        print(f"{version:>6s} | 无数据")
        continue
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    wr = len(wins) / len(trades) * 100
    spnl = sum(t['pnl'] for t in trades)
    tp_n = sum(1 for t in trades if t['hit'] == 'tp')
    sl_n = sum(1 for t in trades if t['hit'] == 'sl')
    ratio = tp_n / max(sl_n, 1)
    win_avg = np.mean([t['pnl'] for t in wins]) if wins else 0
    loss_avg = np.mean([t['pnl'] for t in losses]) if losses else 0
    years_set = sorted(set(t['year'] for t in trades))
    neg_y = sum(1 for y in years_set if sum(t['pnl'] for t in trades if t['year'] == y) < 0)

    print(f"{version:>6s} | {len(trades):>5d} | {wr:>5.1f}% | {spnl:>+8.1f}% | "
          f"{ratio:>6.1f}:1 | {win_avg:>5.2f}% | {loss_avg:>5.2f}% | {neg_y:>4d}")

# ═══ 逐年逐币逐系统 ═══
print(f"\n{'=' * 80}")
print(f"  📅 逐年逐币明细")
print(f"{'=' * 80}")

for year in ['2023', '2024', '2025', '2026']:
    print(f"\n  ── {year} ──")
    row = f"{'币种':>8s}"
    for v in ['V1', 'V2', 'V3']:
        row += f" | {v:>18s}"
    print(row)
    print("-" * 80)

    for sym in SYMS:
        row = f"{sym:>8s}"
        best_pnl = -999
        best_v = ''
        for version in ['V1', 'V2', 'V3']:
            yt = [t for t in all_trades[version] if t['year'] == year and t['sym'] == sym]
            if yt:
                yp = sum(t['pnl'] for t in yt)
                ywr = sum(1 for t in yt if t['pnl'] > 0) / len(yt) * 100
                row += f" | {len(yt):>3d}笔 {yp:>+6.1f}% {ywr:>4.0f}%"
                if yp > best_pnl:
                    best_pnl = yp
                    best_v = version
            else:
                row += f" | {'—':>18s}"
        # mark best
        row += f"  ← {best_v}" if best_v else ""
        print(row)

# ═══ 结论 ═══
print(f"\n{'=' * 80}")
print(f"  🏆 结论")
print(f"{'=' * 80}")

for version in ['V1', 'V2', 'V3']:
    trades = all_trades[version]
    if not trades:
        continue
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]
    wr = len(wins) / len(trades) * 100
    spnl = sum(t['pnl'] for t in trades)
    tp_n = sum(1 for t in trades if t['hit'] == 'tp')
    sl_n = sum(1 for t in trades if t['hit'] == 'sl')
    be = RULES[version]['sl'] / (RULES[version]['tp'] + RULES[version]['sl']) * 100
    is_profitable = wr > be

    # 逐年逐币全正检查
    years_set = sorted(set(t['year'] for t in trades))
    all_pos = True
    neg_list = []
    for y in years_set:
        for sym in SYMS:
            yt = [t for t in trades if t['year'] == y and t['sym'] == sym]
            if yt and sum(t['pnl'] for t in yt) < 0:
                all_pos = False
                neg_list.append(f"{sym} {y}")

    print(f"  {version} ({RULES[version]['desc']}):")
    print(f"    总PnL: {spnl:+.1f}% | 胜率: {wr:.0f}% (保本线: {be:.1f}%) | "
          f"{'✅ 赚钱' if is_profitable else '❌ 不赚钱'}")
    print(f"    逐年逐币全正: {'✅' if all_pos else f'❌ 有{len(neg_list)}个负组合: {neg_list[:5]}'}")

print(f"\n✅ 对比完成")
