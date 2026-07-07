"""
赚钱系统v3 — 一键全流程
=====================
1. 检查数据
2. 全币种回测
3. 输出结果 + 启动建议
"""
import sys, os, csv, json
from collections import defaultdict
import numpy as np
from datetime import datetime

csv.field_size_limit(10**7)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
sys.stdout.reconfigure(encoding='utf-8')

from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
from bi_v0_1 import find_fenxing, find_bi
from duan_v0_1 import find_duan
from zoushi_type import classify_zoushi
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points

# ═══ v3 参数 ═══
TP = 3.5
SL = 1.0
W = 2000; S = 400; WIN = 240; MIN_BARS = 5
CACHE = 'data/cache'
OUT = 'reports'

os.makedirs(OUT, exist_ok=True)

def load(sym):
    p = os.path.join(CACHE, f'{sym}_5min.csv')
    if not os.path.exists(p): return []
    bars = []
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
    return bars

def backtest(sym):
    bars = load(sym)
    if not bars or len(bars) < W + WIN: return []
    trades = []; seen = set()
    for seg in range(0, len(bars) - W - WIN, S):
        seg_end = seg + W; window = bars[seg:seg_end]
        bh = kxian_baohan([dict(b) for b in window])
        for b in bh: b['_orig_date'] = b.get('date', '')
        fx = find_fenxing(bh); bi = find_bi(bh, fx, MIN_BARS)
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
            if not pt or pt.status not in ('confirmed','candidate') or not pt.point_type: continue
            entry = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
            if entry <= 0: continue
            d = 'buy' if 'buy' in pk else 'sell'; bt = window[-1].get('date', '')
            key = f'{sym}|{d}|{bt}|{entry:.2f}'
            if key in seen: continue
            seen.add(key)
            fwd = bars[seg_end:seg_end+WIN]
            if len(fwd) < 5: continue
            tp_p = entry*(1+TP/100) if d=='buy' else entry*(1-TP/100)
            sl_p = entry*(1-SL/100) if d=='buy' else entry*(1+SL/100)
            hit = 'timeout'; exit_p = fwd[-1]['close']
            for i, b in enumerate(fwd):
                if d == 'buy':
                    th = b['high'] >= tp_p; sh = b['low'] <= sl_p
                else:
                    th = b['low'] <= tp_p; sh = b['high'] >= sl_p
                if th and not sh: hit = 'tp'; exit_p = tp_p; break
                if sh and not th: hit = 'sl'; exit_p = sl_p; break
                if th and sh: hit = 'tp'; exit_p = tp_p; break
            pnl = (exit_p-entry)/entry*100 if d=='buy' else (entry-exit_p)/entry*100
            trades.append({
                'sym': sym, 'year': bt[:4], 'dir': d, 'hit': hit,
                'pnl': round(pnl, 3), 'entry': round(entry, 2), 'exit': round(exit_p, 2),
            })
    return trades

# ═══ 检查数据 ═══
SYMS = ['BTCUSDT','ETHUSDT','SOLUSDT','DOGEUSDT','ADAUSDT','XRPUSDT','AVAXUSDT','BNBUSDT']

print("=" * 65)
print(f"  赚钱系统 v3 — 全币种回测")
print(f"  TP={TP}% SL={SL}%  纯阿娇信号 无闸门")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 65)

# 数据状态
print(f"\n📊 数据状态:")
ready = []; partial = []
for sym in SYMS:
    p = os.path.join(CACHE, f'{sym}_5min.csv')
    if not os.path.exists(p):
        print(f"  ❌ {sym}: 无数据")
        continue
    with open(p) as f:
        lines = sum(1 for _ in f) - 1
    f = open(p); f.readline()
    first = f.readline()[:10] if lines > 0 else '?'
    for line in f: last = line[:10]
    f.close()
    # >50000 bars = ~6 months of 5min data, good enough
    if lines > 50000:
        print(f"  ✅ {sym}: {lines:,}根 {first}→{last}")
        ready.append(sym)
    elif lines > 5000:
        print(f"  ⚠️ {sym}: {lines:,}根 {first}→{last} (数据偏少)")
        partial.append(sym)
    else:
        print(f"  ❌ {sym}: {lines:,}根 (不足)")

# ═══ 回测 ═══
print(f"\n📈 回测结果 (TP={TP}% SL={SL}%):")

all_trades = []
for sym in ready + partial:
    trades = backtest(sym)
    if not trades:
        print(f"  {sym}: 0笔")
        continue
    all_trades.extend(trades)
    spnl = sum(t['pnl'] for t in trades)
    swr = sum(1 for t in trades if t['pnl']>0)/len(trades)*100
    years = sorted(set(t['year'] for t in trades))
    neg = sum(1 for y in years if sum(t['pnl'] for t in trades if t['year']==y) < 0)
    print(f"  {sym:>12s}: {len(trades):>4d}笔 WR={swr:>5.0f}% PnL={spnl:>+7.1f}% {neg}/{len(years)}负年")
    for y in years:
        yt = [t for t in trades if t['year']==y]
        if len(yt) < 3: continue
        yp = sum(t['pnl'] for t in yt)
        ywr = sum(1 for t in yt if t['pnl']>0)/len(yt)*100
        icon = '✅' if yp > 0 else '❌'
        print(f"       {icon} {y}: {len(yt):>3d}笔 WR={ywr:>5.0f}% PnL={yp:>+7.1f}%")

# ═══ 汇总 ═══
if all_trades:
    wins = [t['pnl'] for t in all_trades if t['pnl'] > 0]
    losses = [t['pnl'] for t in all_trades if t['pnl'] < 0]
    wr = len(wins)/len(all_trades)*100
    be = SL/(TP+SL)*100

    print(f"\n{'='*65}")
    print(f"📋 汇总")
    print(f"  总交易: {len(all_trades)}笔")
    print(f"  总PnL: {sum(t['pnl'] for t in all_trades):.1f}%")
    print(f"  胜率: {wr:.0f}% (保本线: {be:.1f}%)")
    print(f"  赢均: {np.mean(wins):.2f}%  亏均: {np.mean(losses):.2f}%")
    print(f"  赢:亏 = {len(wins)}:{len(losses)} = {len(wins)/max(len(losses),1):.1f}:1")

    # 年度逐币表
    years_all = sorted(set(t['year'] for t in all_trades))
    syms_done = sorted(set(t['sym'] for t in all_trades), key=lambda s: -sum(t['pnl'] for t in all_trades if t['sym']==s))
    print(f"\n{'年':>6s}", end='')
    for sym in syms_done:
        print(f" | {sym:>8s}", end='')
    print(f" | {'合计':>8s}")
    print("-" * (20 + 11 * len(syms_done)))

    for year in years_all:
        yt = [t for t in all_trades if t['year']==year]
        yp = sum(t['pnl'] for t in yt)
        print(f"{year:>6s}", end='')
        for sym in syms_done:
            sp = sum(t['pnl'] for t in yt if t['sym']==sym)
            st = [t for t in yt if t['sym']==sym]
            if st:
                sicon = '✅' if sp >= 0 else '❌'
                print(f" | {sicon}{sp:>6.1f}%", end='')
            else:
                print(f" | {'—':>8s}", end='')
        icon = '✅' if yp >= 0 else '❌'
        print(f" | {icon}{yp:>6.1f}%")

print(f"\n{'='*65}")
print(f"✅ 完成")

# ═══ 保存 ═══
report = {
    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'tp': TP, 'sl': SL,
    'total_trades': len(all_trades),
    'total_pnl': sum(t['pnl'] for t in all_trades),
    'win_rate': wr,
}
with open(os.path.join(OUT, 'v3_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
