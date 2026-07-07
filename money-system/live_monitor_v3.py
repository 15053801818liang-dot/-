"""
赚钱系统V3 实盘监控 — 24/7
==========================
TP=3.5% SL=1.0% 纯阿娇信号，无闸门
每5分钟拉Binance数据，跑阿娇管线，出信号
主战场: BTC ETH SOL
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

# ═══ V3 配置 ═══
SYMS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
W = 2000
TP = 3.5
SL = 1.0
MIN_BARS = 5
WIN = 240  # 前向窗口(20h)

CACHE_DIR = BASE / "data" / "cache"
LOG_FILE = BASE / "reports" / "live_signals_v3.txt"
STATE_FILE = BASE / "reports" / "monitor_state.json"

os.makedirs(BASE / "reports", exist_ok=True)


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
    """增量更新本地缓存"""
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
    """V3阿娇管线 — 纯信号，无闸门"""
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

        entry = pt.reference_price if pt.reference_price > 0 else pt.confirm_price
        if entry <= 0:
            continue

        d = 'buy' if 'buy' in pk else 'sell'
        last_close = bars[-1]['close']
        dist = abs(last_close - entry) / entry * 100

        # V3: 固定 TP/SL
        tp_price = entry * (1 + TP/100) if d == 'buy' else entry * (1 - TP/100)
        sl_price = entry * (1 - SL/100) if d == 'buy' else entry * (1 + SL/100)

        signals.append({
            'sym': sym, 'dir': d, 'type': pk,
            'entry': round(entry, 4),
            'tp': TP, 'sl': SL,
            'tp_price': round(tp_price, 4),
            'sl_price': round(sl_price, 4),
            'last_price': round(last_close, 4),
            'dist_pct': round(dist, 2),
            'zs_count': len(zs),
            'zoushi': zt.get('type', '?'),
            'div_direction': div.direction,
            'bi_count': len(bi),
            'duan_count': len(du),
            'time': bars[-1]['date'],
        })
    return signals


def log_signal(sig):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        d = '🟢多' if sig['dir'] == 'buy' else '🔴空'
        f.write(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] "
                f"{d} {sig['sym']} | entry={sig['entry']} "
                f"TP={sig['tp']}% SL={sig['sl']}% | "
                f"TP价={sig['tp_price']} SL价={sig['sl_price']} | "
                f"距入场={sig['dist_pct']}% | "
                f"ZS={sig['zs_count']} {sig['zoushi']} div={sig['div_direction']} | "
                f"笔={sig['bi_count']} 段={sig['duan_count']} | "
                f"K线:{sig['time']}\n")


def save_state(scan_count, total_signals, last_scan):
    import json
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'scan_count': scan_count,
            'total_signals': total_signals,
            'last_scan': last_scan,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 65)
    print("  赚钱系统 V3 实盘监控  24/7")
    print(f"  币种: {', '.join(SYMS)}")
    print(f"  参数: TP={TP}% SL={SL}% W={W} WIN={WIN}")
    print(f"  逻辑: 纯阿娇信号 无闸门 固定仓位")
    print(f"  日志: {LOG_FILE}")
    print(f"  启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    scan_count = 0
    total_signals = 0

    while True:
        scan_count += 1
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{'─'*65}")
        print(f"  [{now}] 扫描 #{scan_count}")
        print(f"{'─'*65}")

        all_signals = []
        for sym in SYMS:
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
                print(f"  {sym:<12s} {len(bars)}根{new_str} {sig_str} | "
                      f"最新:{bars[-1]['date']} close={bars[-1]['close']}")
            except Exception as e:
                print(f"  {sym:<12s} ⚠ {e}")

        total_signals += len(all_signals)

        print(f"\n  ── V3 信号 ──")
        if all_signals:
            buys = [s for s in all_signals if s['dir'] == 'buy']
            sells = [s for s in all_signals if s['dir'] == 'sell']
            print(f"  🟢多{len(buys)} 🔴空{len(sells)}  累计信号:{total_signals}")
            for s in all_signals:
                d = "🟢多" if s['dir'] == 'buy' else "🔴空"
                print(f"    {d} {s['sym']} @{s['entry']} "
                      f"TP={s['tp_price']} SL={s['sl_price']} "
                      f"距={s['dist_pct']}% | ZS={s['zs_count']} {s['zoushi']} "
                      f"div={s['div_direction']}")
        else:
            print(f"  无信号  累计信号:{total_signals}")

        save_state(scan_count, total_signals, now)

        print(f"\n  ⏰ 5分钟后... (Ctrl+C 停止 | 累计{scan_count}次扫描)")
        sys.stdout.flush()
        try:
            time.sleep(300)
        except KeyboardInterrupt:
            print(f"\n  ⏹ 停止。共{scan_count}次扫描 {total_signals}个信号")
            print(f"  日志: {LOG_FILE}")
            break


if __name__ == "__main__":
    print("V3 实盘监控初始化...")
    print(f"检查本地缓存...")
    for sym in SYMS:
        cached = load_cached(sym)
        if len(cached) < 500:
            print(f"  {sym}: 本地数据不足({len(cached)}根)，拉取Binance...")
            new_bars = fetch_recent(sym, 1000)
            if new_bars:
                path = CACHE_DIR / f"{sym}_5min.csv"
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
                    w.writeheader()
                    w.writerows(new_bars)
                print(f"    → {len(new_bars)}根 ✅")
        else:
            print(f"  {sym}: {len(cached)}根 ✅")
    print()
    main()
