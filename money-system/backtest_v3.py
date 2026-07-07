"""
赚钱系统v3 — TP=3.5% SL=1.0% 纯阿娇信号，无闸门
===============================================
每个币、每一年都跑，看是不是全正
"""
import sys, os, csv
csv.field_size_limit(10**7)
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
sys.stdout.reconfigure(encoding='utf-8')

from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
from bi_v0_1 import find_fenxing, find_bi
from duan_v0_1 import find_duan
from zoushi_type import classify_zoushi
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points

# ═══ v3 参数 ═══
TP = 3.5      # 止盈%
SL = 1.0      # 止损%
W = 2000      # 分析窗口
S = 400       # 步长
WIN = 240     # 前向跟踪窗口 (240×5min = 20h)
MIN_BARS = 5  # 笔最小K线

CACHE = 'data/cache'

def load(sym):
    p = os.path.join(CACHE, f'{sym}_5min.csv')
    if not os.path.exists(p): return []
    bars = []
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                bar = {}
                for k, v in row.items():
                    if k == 'date': bar[k] = v
                    elif v is None or v == '': bar[k] = 0.0
                    else:
                        try: bar[k] = float(v)
                        except: bar[k] = 0.0
                bars.append(bar)
    except: return []
    return bars

def run(sym, tp=TP, sl=SL):
    bars = load(sym)
    if not bars or len(bars) < W + WIN: return None

    trades = []; seen = set()

    for seg in range(0, len(bars) - W - WIN, S):
        seg_end = seg + W
        window = bars[seg:seg_end]

        # 阿娇管线
        bh = kxian_baohan([dict(b) for b in window])
        for b in bh: b['_orig_date'] = b.get('date', '')
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
            if not pt or pt.status not in ('confirmed','candidate') or not pt.point_type:
                continue

            entry = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
            if entry <= 0: continue
            d = 'buy' if 'buy' in pk else 'sell'
            bt = window[-1].get('date', '')
            year = bt[:4]

            key = f"{sym}|{d}|{bt}|{entry:.2f}"
            if key in seen: continue
            seen.add(key)

            # TP/SL 前向模拟
            fwd = bars[seg_end:seg_end + WIN]
            if len(fwd) < 5: continue

            tp_price = entry*(1+tp/100) if d == 'buy' else entry*(1-tp/100)
            sl_price = entry*(1-sl/100) if d == 'buy' else entry*(1+sl/100)

            hit = 'timeout'; exit_p = fwd[-1]['close']
            for i, b in enumerate(fwd):
                if d == 'buy':
                    tp_hit = b['high'] >= tp_price; sl_hit = b['low'] <= sl_price
                else:
                    tp_hit = b['low'] <= tp_price; sl_hit = b['high'] >= sl_price
                if tp_hit and not sl_hit: hit = 'tp'; exit_p = tp_price; break
                if sl_hit and not tp_hit: hit = 'sl'; exit_p = sl_price; break
                if tp_hit and sl_hit: hit = 'tp'; exit_p = tp_price; break

            pnl = (exit_p-entry)/entry*100 if d == 'buy' else (entry-exit_p)/entry*100
            trades.append({
                'sym': sym, 'year': year, 'dir': d,
                'pnl': round(pnl, 3), 'hit': hit,
                'entry': round(entry,2), 'exit': round(exit_p,2),
            })

    return {'trades': trades, 'bars': len(bars), 'sym': sym}


# ═══ 主程序 ═══
print(f"赚钱系统v3 — TP={TP}% SL={SL}% 纯阿娇信号 无闸门")
print("=" * 70)

# 获取可用币种
SYMS = []
for f in sorted(os.listdir(CACHE)):
    if f.endswith('_5min.csv'):
        sym = f.replace('_5min.csv', '')
        sz = os.path.getsize(os.path.join(CACHE, f))
        SYMS.append((sym, sz))
SYMS.sort(key=lambda x: -x[1])

all_trades = []
total_signals = 0

for sym, sz in SYMS:
    r = run(sym)
    if r is None:
        print(f"{sym:>12s}: ❌ 无数据")
        continue
    trades = r['trades']
    if not trades:
        print(f"{sym:>12s}: 0笔信号")
        continue
    all_trades.extend(trades)
    total_signals += r['total_signals'] if 'total_signals' in r else len(trades)

    spnl = sum(t['pnl'] for t in trades)
    swr = sum(1 for t in trades if t['pnl']>0) / len(trades)*100
    years = sorted(set(t['year'] for t in trades))
    neg = sum(1 for y in years if sum(t['pnl'] for t in trades if t['year']==y) < 0)
    bars_k = r['bars'] // 1000

    print(f"{sym:>12s} | {len(trades):>4d}笔 | WR:{swr:>5.0f}% | PnL:{spnl:>7.1f}% | {neg}/{len(years)}负年 | {bars_k}k根")

# ═══ 按年汇总 ═══
print(f"\n{'='*70}")
print(f"汇总: {len(all_trades)}笔  PnL:{sum(t['pnl'] for t in all_trades):.1f}%")
print(f"{'='*70}")

yearly = defaultdict(list)
for t in all_trades: yearly[t['year']].append(t)
all_years = sorted(yearly)

# 按币种收集
syms_found = sorted(set(t['sym'] for t in all_trades), key=lambda s: -sum(t['pnl'] for t in all_trades if t['sym']==s))

header = f"{'年':>6s} | {'总笔':>4s} | {'总PnL':>7s}"
for sym in syms_found:
    header += f" | {sym:>7s}"
print(header)
print("-" * (20 + 10 * len(syms_found)))

for year in all_years:
    yt = yearly[year]
    ypnl = sum(t['pnl'] for t in yt)
    row = f"{year:>6s} | {len(yt):>4d} | {ypnl:>6.1f}%"
    for sym in syms_found:
        sp = sum(t['pnl'] for t in yt if t['sym']==sym)
        if any(t['sym']==sym for t in yt):
            row += f" | {sp:>6.1f}%"
        else:
            row += f" | {'—':>7s}"
    print(row)

# ═══ 盈亏统计 ═══
print(f"\n赢:亏 保本线分析:")
wins_raw = [t['pnl'] for t in all_trades if t['pnl'] > 0]
losses_raw = [t['pnl'] for t in all_trades if t['pnl'] < 0]
wr = len(wins_raw)/len(all_trades)*100
break_even = SL/(TP+SL)*100
print(f"  胜率: {wr:.0f}%  保本线: {break_even:.1f}%  {'✅ 赚钱' if wr>break_even else '❌ 亏钱'}")
print(f"  赢均: {np.mean(wins_raw):.2f}% ({len(wins_raw)}笔)")
print(f"  亏均: {np.mean(losses_raw):.2f}% ({len(losses_raw)}笔)")
print(f"  盈亏比(次数): {len(wins_raw)}:{len(losses_raw)} = {len(wins_raw)/max(len(losses_raw),1):.1f}:1")

# 是否每年每币全正
print(f"\n逐年逐币检查:")
all_good = True
for year in all_years:
    for sym in syms_found:
        yt = [t for t in all_trades if t['year']==year and t['sym']==sym]
        if not yt: continue
        yp = sum(t['pnl'] for t in yt)
        if yp < 0:
            print(f"  ❌ {sym} {year}: {yp:.1f}%")
            all_good = False

if all_good:
    print(f"  ✅ 全部正收益!")
else:
    # 还是打印正收益的
    pos_count = 0
    for year in all_years:
        for sym in syms_found:
            yt = [t for t in all_trades if t['year']==year and t['sym']==sym]
            if yt and sum(t['pnl'] for t in yt) >= 0:
                pos_count += 1
    total_combos = sum(1 for y in all_years for s in syms_found if any(t['year']==y and t['sym']==s for t in all_trades))
    print(f"  正收益: {pos_count}/{total_combos}")

print(f"\n✅ 完成 — v3 TP={TP}% SL={SL}%")
