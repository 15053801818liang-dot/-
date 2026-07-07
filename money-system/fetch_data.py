"""
稳健数据拉取 — 断点续传 + 限速
每币逐个拉，已拉的不重复
"""
import requests, time, csv, os
from datetime import datetime

SYMS = ['BTCUSDT','ETHUSDT','SOLUSDT','DOGEUSDT','ADAUSDT','XRPUSDT','AVAXUSDT','BNBUSDT']
OUT = 'data/cache'
os.makedirs(OUT, exist_ok=True)
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

def fetch(sym):
    outfile = os.path.join(OUT, f'{sym}_5min.csv')
    existing = {}
    if os.path.exists(outfile):
        with open(outfile) as f:
            for row in csv.DictReader(f):
                existing[row['date']] = row

    start_ts = int(datetime(2022,1,1).timestamp() * 1000)
    end_ts = int(datetime.now().timestamp() * 1000)
    new_rows = []
    current = start_ts
    errors = 0

    print(f'{sym}: 已有{len(existing):,}根, 从{datetime.fromtimestamp(current/1000).strftime("%Y-%m-%d")}开始')
    last_new = 0
    if existing:
        dates = sorted(existing.keys())
        last_dt = dates[-1]
        last_ts = int(datetime.strptime(last_dt, '%Y-%m-%d %H:%M:%S').timestamp()*1000) + 60000
        if last_ts > current:
            current = last_ts

    while current < end_ts and errors < 10:
        try:
            resp = s.get('https://api.binance.com/api/v3/klines',
                        params={'symbol': sym, 'interval': '5m', 'limit': 1000,
                                'startTime': current, 'endTime': end_ts},
                        timeout=30)
            if resp.status_code == 429:
                print(f'  限速, 等30s...'); time.sleep(30); continue
            if resp.status_code != 200:
                errors += 1; time.sleep(5); continue

            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                break

            errors = 0
            for k in data:
                dt = datetime.fromtimestamp(k[0]/1000).strftime('%Y-%m-%d %H:%M:%S')
                if dt in existing:
                    continue
                new_rows.append({
                    'date': dt, 'open': float(k[1]), 'high': float(k[2]),
                    'low': float(k[3]), 'close': float(k[4]), 'volume': float(k[5]),
                })

            current = data[-1][0] + 60000
            if len(new_rows) - last_new > 50000:
                last_new = len(new_rows)
                pct = (current-start_ts)/(end_ts-start_ts)*100
                print(f'  +{len(new_rows):,}根 ({pct:.0f}%)')

            time.sleep(0.3)

        except Exception as e:
            errors += 1
            print(f'  ⚠️ {e}'); time.sleep(10)

    if new_rows:
        rows = list(existing.values()) + new_rows
        rows.sort(key=lambda r: r['date'])
        with open(outfile, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['date','open','high','low','close','volume'])
            w.writeheader(); w.writerows(rows)

    print(f'  ✅ {sym}: +{len(new_rows):,}根 总计{len(existing)+len(new_rows):,}根')
    return len(new_rows)

total = 0
for sym in SYMS:
    n = fetch(sym)
    total += n
    time.sleep(1)

print(f'\n总计: +{total:,}根')
