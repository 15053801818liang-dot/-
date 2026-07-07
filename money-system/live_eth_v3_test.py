"""
赚钱系统v3 — ETH 24小时实时实测（简化版）
vs 小龙虾赚钱 同一品种(ETH 5min)对照运行
运行方式：python live_eth_v3_test.py / --report
"""
import os, sys, json, csv, requests
from datetime import datetime
from pathlib import Path
sys.path.insert(0, r'D:\序\workspace\墨熵·序\active\赚钱系统')
sys.path.insert(0, r'D:\序\workspace\墨熵·序\active\赚钱系统\core')
from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
from bi_v0_1 import find_fenxing, find_bi
from duan_v0_1 import find_duan
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points
LIVE_DIR = Path(r'D:\序\workspace\墨熵·序\active\赚钱系统\live')
LIVE_DIR.mkdir(exist_ok=True)
CACHE_DIR = LIVE_DIR / 'cache'; CACHE_DIR.mkdir(exist_ok=True)
TRADE_LOG = LIVE_DIR / 'trades_v3.jsonl'
STATE_LOG = LIVE_DIR / 'state_v3.json'
SYM = 'ETHUSDT'; INITIAL = 10000.0
MIN_BARS = 5

def fetch_5min(n=200):
    r = requests.get('https://api.binance.com/api/v3/klines',
        params={'symbol':SYM,'interval':'5m','limit':n}, timeout=10)
    r.raise_for_status()
    return [{'time':int(k[0])//1000,'date':datetime.fromtimestamp(int(k[0])//1000).strftime('%Y-%m-%d %H:%M'),'open':float(k[1]),'high':float(k[2]),
             'low':float(k[3]),'close':float(k[4]),'volume':float(k[5])} for k in r.json()]

def run_pipeline(bars):
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]; lows = [b['low'] for b in bars]
    bh = kxian_baohan([dict(b) for b in bars])
    for b in bh: b['_orig_date'] = b.get('date','')
    fx = find_fenxing(bh)
    bi = find_bi(bh, fx, MIN_BARS)
    du = find_duan(bi)
    zs = find_zhongshu_from_duan(du)
    div = find_divergence(du, zs, closes, highs, lows, level='5min')
    pts = detect_buy_sell_points(div, None, bi, du, level='5min')
    return {'signals':pts,'bi':len(bi),'duan':len(du),'zhongshu':len(zs)}

def run_once():
    bars = fetch_5min(200)
    r = run_pipeline(bars)
    price = bars[-1]['close']
    print(f"[v3] ETH ${price:.2f} | 笔:{r['bi']} 段:{r['duan']} 中枢:{r['zhongshu']} 信号:{len(r['signals'])}")
    for s in r['signals']:
        rec = {'time':datetime.now().isoformat(),'sym':SYM,'price':price,'type':str(s)}
        with open(TRADE_LOG,'a',encoding='utf-8') as f:
            f.write(json.dumps(rec,ensure_ascii=False)+'\n')
    STATE_LOG.write_text(json.dumps({'last':datetime.now().isoformat(),
        'signals':len(r['signals']),'price':price},ensure_ascii=False,indent=2),encoding='utf-8')

def report():
    trades = []
    if TRADE_LOG.exists():
        with open(TRADE_LOG,'r') as f:
            for line in f:
                if line.strip(): trades.append(json.loads(line))
    print(f"\n{'='*40}\n赚钱系统v3 · ETH 5min 实盘\n{'='*40}")
    print(f"  初始资金: ${INITIAL:,.0f} | 信号: {len(trades)} 次")
    if trades: print(f"  最近: {trades[-1]['time'][:16]} @ ${trades[-1]['price']}")

if __name__ == '__main__':
    run_once() if '--report' not in sys.argv else report()
