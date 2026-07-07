"""
赚钱系统v2 实盘监控 — 5min 多空信号
====================================
每5分钟拉一次Binance数据，跑v2管线，出信号。
聚焦不稳定品种：DOGE SOL AVAX ADA XRP + 基准BTC ETH BNB
"""
import sys, csv, time, os, requests
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / 'core'))

from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
from bi_v0_1 import find_fenxing, find_bi
from duan_v0_1 import find_duan
from zoushi_type import classify_zoushi
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points

# ═══ 配置 ═══
VOLATILE = ['DOGEUSDT', 'SOLUSDT', 'AVAXUSDT', 'ADAUSDT', 'XRPUSDT']
STABLE   = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
ALL_SYMS = VOLATILE + STABLE

W = 2000
SL_FALLBACK = 1.0
TP = 3.5
MIN_BARS = 5

CACHE_DIR = BASE / "data" / "cache"
LOG_FILE = BASE / "reports" / "live_signals.txt"


def fetch_recent(sym, n=200):
    """Binance API: 最近n根5min K线"""
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0'})
        resp = s.get('https://api.binance.com/api/v3/klines',
                     params={'symbol': sym, 'interval': '5m', 'limit': n},
                     timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        rows = []
        for k in data:
            rows.append({
                'date': time.strftime('%Y-%m-%dT%H:%M', time.localtime(k[0] / 1000)),
                'open': float(k[1]), 'high': float(k[2]),
                'low': float(k[3]), 'close': float(k[4]),
                'volume': float(k[5]),
            })
        return rows
    except Exception as e:
        return []


def load_cached(sym):
    path = CACHE_DIR / f"{sym}_5min.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append({
                'date': row['date'],
                'open': float(row['open']), 'high': float(row['high']),
                'low': float(row['low']), 'close': float(row['close']),
                'volume': float(row.get('volume', 0)),
            })
    return rows


def update_data(sym):
    """增量更新"""
    cached = load_cached(sym)
    recent = fetch_recent(sym, 200)
    if not recent:
        return cached, 0

    existing = {r['date'] for r in cached}
    new_bars = [r for r in recent if r['date'] not in existing]

    if new_bars:
        all_bars = cached + new_bars
        all_bars.sort(key=lambda r: r['date'])
        path = CACHE_DIR / f"{sym}_5min.csv"
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
            w.writeheader()
            w.writerows(all_bars)
        return all_bars, len(new_bars)
    return cached, 0


def run_pipeline(bars, sym):
    """赚钱v2管线"""
    bars = [dict(b) for b in bars[-W:]]
    for b in bars:
        b['_orig_date'] = b['date']

    bh = kxian_baohan(bars)
    fx = find_fenxing(bh)
    bi = find_bi(bh, fx, MIN_BARS)
    if len(bi) < 3:
        return []

    du = find_duan(bi)
    zs = find_zhongshu_from_duan(du)
    if not zs:
        return []

    c = [b['close'] for b in bars]
    h = [b['high'] for b in bars]
    l = [b['low'] for b in bars]

    zt = classify_zoushi(zs)
    div = find_divergence(du, zs, c, h, l, level='5min',
                          zoushi_type=zt.get('type', ''))
    pts = detect_buy_sell_points(div, None, bi, du, level='5min')

    signals = []
    for pk in ['first_buy', 'first_sell']:
        pt = pts.get(pk)
        if not pt or pt.status not in ('confirmed', 'candidate') or not pt.point_type:
            continue

        revival_ok = False
        div_end = div.segment_b.end_idx if div.segment_b else -1
        if div_end < 0:
            continue
        target_dir = '向上笔' if 'buy' in pk else '向下笔'
        for bi2 in bi:
            if bi2.get('from', {}).get('idx', 0) <= div_end:
                continue
            if bi2.get('direction', '') == target_dir:
                revival_ok = True
                break
        if not revival_ok:
            continue

        ref_b = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
        if ref_b <= 0:
            continue

        d = 'buy' if 'buy' in pk else 'sell'

        structural_sl = SL_FALLBACK
        sl_source = 'fallback'
        if d == 'buy':
            lows = []
            for d2 in du:
                lo = d2.get('to', {}).get('low', d2.get('from', {}).get('low', 0)) if isinstance(d2, dict) else 0
                if 0 < lo < ref_b: lows.append(lo)
            if lows:
                swing = max(lows); risk = (ref_b - swing) / ref_b * 100
                structural_sl = min(max(risk, 2.0), 8.0); sl_source = f'swing({structural_sl:.1f}%)'
        else:
            highs = []
            for d2 in du:
                hi = d2.get('to', {}).get('high', d2.get('from', {}).get('high', 0)) if isinstance(d2, dict) else 0
                if hi > ref_b: highs.append(hi)
            if highs:
                swing = min(highs); risk = (swing - ref_b) / ref_b * 100
                structural_sl = min(max(risk, 2.0), 8.0); sl_source = f'swing({structural_sl:.1f}%)'

        last_close = bars[-1]['close']
        dist = abs(last_close - ref_b) / ref_b * 100

        signals.append({
            'sym': sym, 'dir': d, 'type': pk,
            'entry': round(ref_b, 4), 'sl': round(structural_sl, 2),
            'sl_source': sl_source, 'tp': TP,
            'last_price': round(last_close, 4), 'dist_pct': round(dist, 2),
            'zs_count': len(zs), 'zoushi': zt.get('type', '?'),
            'div_direction': div.direction, 'time': bars[-1]['date'],
        })
    return signals


def log_signal(sig):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        d = '多' if sig['dir'] == 'buy' else '空'
        f.write(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] "
                f"{sig['sym']} {d} | entry={sig['entry']} "
                f"SL={sig['sl']}% TP={sig['tp']}% | "
                f"距入场={sig['dist_pct']}% | "
                f"ZS={sig['zs_count']} {sig['zoushi']} div={sig['div_direction']} | "
                f"K线:{sig['time']}\n")


def main():
    print("=" * 60)
    print("  赚钱系统v2 实盘监控")
    print(f"  不稳定: {', '.join(VOLATILE)}")
    print(f"  基准:   {', '.join(STABLE)}")
    print(f"  参数: SL={SL_FALLBACK}% TP={TP}% W={W} min_bars={MIN_BARS}")
    print(f"  日志: {LOG_FILE}")
    print("=" * 60)

    while True:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{'─'*60}")
        print(f"  [{now}] 扫描中...")
        print(f"{'─'*60}")

        all_signals = []
        for sym in ALL_SYMS:
            try:
                bars, new_n = update_data(sym)
                if not bars:
                    print(f"  {sym:<12s} ❌ 无数据")
                    continue
                sigs = run_pipeline(bars, sym)
                for s in sigs:
                    all_signals.append(s)
                    log_signal(s)
                new_str = f" +{new_n}" if new_n else ""
                sig_str = f"⚡{len(sigs)}信号" if sigs else "-"
                tag = "🔴" if sym in VOLATILE else "🟢"
                print(f"  {tag} {sym:<12s} {len(bars)}根{new_str} {sig_str} | {bars[-1]['date']}")
            except Exception as e:
                print(f"  {sym:<12s} ⚠ {e}")

        print(f"\n  ── 信号 ──")
        if all_signals:
            buys = [s for s in all_signals if s['dir'] == 'buy']
            sells = [s for s in all_signals if s['dir'] == 'sell']
            print(f"  🟢多{len(buys)} 🔴空{len(sells)}")
            for s in all_signals:
                d = "🟢多" if s['dir'] == 'buy' else "🔴空"
                print(f"    {d} {s['sym']} @{s['entry']} SL={s['sl']}% "
                      f"距={s['dist_pct']}% | {s['zoushi']}")
        else:
            print(f"  无信号")

        print(f"\n  ⏰ 5分钟后... (Ctrl+C 停止)")
        sys.stdout.flush()
        try:
            time.sleep(300)
        except KeyboardInterrupt:
            print(f"\n  停止。日志: {LOG_FILE}")
            break


if __name__ == "__main__":
    print("初始化，拉取数据...")
    for sym in ALL_SYMS:
        cached = load_cached(sym)
        if len(cached) < 500:
            print(f"  {sym}: 拉取中...")
            new_bars = fetch_recent(sym, 1000)
            if new_bars:
                path = CACHE_DIR / f"{sym}_5min.csv"
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
                    w.writeheader()
                    w.writerows(new_bars)
                print(f"    → {len(new_bars)}根")
        else:
            print(f"  {sym}: {len(cached)}根 ✅")
    print()
    main()
