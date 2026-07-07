"""赚钱系统v2.1 — 结构止损+趋势加分 🔒封存 2026-06-20"""
import sys,csv,os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))
sys.stdout.reconfigure(encoding='utf-8')
from draw_chan_ajiao import kxian_baohan,find_zhongshu_from_duan
from bi_v0_1 import find_fenxing,find_bi
from duan_v0_1 import find_duan
from zoushi_type import classify_zoushi
from divergence import find_divergence
from buy_sell_points import detect_buy_sell_points

# ═══════ v2.1 参数 ═══════
SYMS=['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','ADAUSDT','DOGEUSDT','XRPUSDT','AVAXUSDT']
W=2000; S=400; WIN=120
SL_FALLBACK=4.0        # 结构止损回退固定% (仅在无结构时)
TP_MAIN=1.0
TP_ALT=0.8
BONUS_MIN=1

events=[]

for sym in SYMS:
    try:
        bars_all=[]
        with open(f'data/cache/{sym}_5min.csv') as f:
            for row in csv.DictReader(f):
                bars_all.append({k:float(v) if k!='date' else v for k,v in row.items()})
    except: continue
    if len(bars_all)<W: continue
    seen=set()

    for seg in range(0,len(bars_all)-W-WIN,S):
        seg_end=seg+W
        bars=bars_all[seg:seg_end]
        for b in bars: b['_orig_date']=b['date']
        bh=kxian_baohan(bars);fx=find_fenxing(bh);bi=find_bi(bh,fx,5)
        if len(bi)<3: continue
        du=find_duan(bi);zs=find_zhongshu_from_duan(du)
        if not zs: continue
        c=[b['close'] for b in bars];h=[b['high'] for b in bars];l=[b['low'] for b in bars]
        div=find_divergence(du,zs,c,h,l,level='5min',zoushi_type=classify_zoushi(zs).get('type',''))
        pts=detect_buy_sell_points(div,None,bi,du,level='5min')

        # 30min共振
        seg30_start=max(0,seg-800);bars30=bars_all[seg30_start:seg_end]
        for b in bars30: b['_orig_date']=b['date']
        bh30=kxian_baohan(bars30);fx30=find_fenxing(bh30)
        bi30=find_bi(bh30,fx30,5);du30=find_duan(bi30);zs30=find_zhongshu_from_duan(du30)
        align_bonus=False
        if zs30:
            c30=[b['close'] for b in bars30];h30=[b['high'] for b in bars30];l30=[b['low'] for b in bars30]
            div30=find_divergence(du30,zs30,c30,h30,l30,level='30min',
                                  zoushi_type=classify_zoushi(zs30).get('type',''))
            if div30.direction==div.direction and div30.direction!='none': align_bonus=True

        for pk in ['first_buy','first_sell']:
            pt=pts.get(pk)
            if not pt or pt.status not in ('confirmed','candidate') or not pt.point_type: continue
            target_dir='向上' if 'buy' in pk else '向下';revival_ok=False;rev_bonus=False
            div_end=div.segment_b.end_idx if div.segment_b else -1
            if div_end<0: continue
            for bi2 in bi:
                if bi2.get('from',{}).get('idx',0)<=div_end: continue
                if target_dir in bi2.get('direction',''):
                    revival_ok=True
                    if abs(bi2.get('from',{}).get('idx',0)-bi2.get('to',{}).get('idx',0))<8: rev_bonus=True
                    break
            if not revival_ok: continue

            bonus=(1 if align_bonus else 0)+(1 if rev_bonus else 0)
            if bonus<BONUS_MIN: continue  # v2筛选 (先不加趋势分)

            ref_b=pt.reference_price if pt.reference_price>0 else pt.confirm_price
            if ref_b<=0: continue
            d='buy' if 'buy' in pk else 'sell'

            # v2.1: 趋势方向加分 — 信号与更长趋势同向+1
            trend_bonus=False
            wider=bars_all[max(0,seg-2000):seg_end]
            if len(wider)>500:
                wp=[b['close'] for b in wider]
                early=sum(wp[:100])/100; late=sum(wp[-100:])/100
                trend_up=late>early*1.05; trend_down=late<early*0.95
                if (d=='buy' and trend_up) or (d=='sell' and trend_down):
                    trend_bonus=True
            bonus+=1 if trend_bonus else 0
            ek=(sym,seg//S,pk,round(ref_b,0))
            if ek in seen: continue
            seen.add(ek)
            si=None;best_d=float('inf')
            for i in range(seg,seg_end):
                dist=abs(bars_all[i]['close']-ref_b)/ref_b
                if dist<best_d: best_d=dist;si=i
            if best_d>0.015 or si is None: continue
            ref=bars_all[si]['close']

            tp=TP_ALT if sym in ('BNBUSDT','ADAUSDT','DOGEUSDT','XRPUSDT','AVAXUSDT') else TP_MAIN

            # v2.1: 结构止损 — 取最近前摆动点, 缺失回退4%
            structural_sl=SL_FALLBACK; sl_source='fallback'
            if d=='buy':
                lows=[]
                for d2 in du:
                    lo=d2.get('to',{}).get('low',d2.get('from',{}).get('low',0)) if isinstance(d2,dict) else 0
                    if lo>0 and lo<ref: lows.append(lo)
                if lows:
                    swing=max(lows); risk=(ref-swing)/ref*100
                    if 2.0<=risk<=8.0:
                        structural_sl=risk; sl_source=f'prior_swing({risk:.1f}%)'
                    else:
                        structural_sl=min(max(risk,4.0),8.0); sl_source=f'prior_swing_clamped({structural_sl:.1f}%)'
            else:
                highs=[]
                for d2 in du:
                    hi=d2.get('to',{}).get('high',d2.get('from',{}).get('high',0)) if isinstance(d2,dict) else 0
                    if hi>ref: highs.append(hi)
                if highs:
                    swing=min(highs); risk=(swing-ref)/ref*100
                    if 2.0<=risk<=8.0:
                        structural_sl=risk; sl_source=f'prior_swing({risk:.1f}%)'
                    else:
                        structural_sl=min(max(risk,4.0),8.0); sl_source=f'prior_swing_clamped({structural_sl:.1f}%)'

            tp_bar=sl_bar=None
            for i in range(si+1,min(si+WIN,len(bars_all)-1)+1):
                bar=bars_all[i]
                if d=='buy':
                    if bar['high']>=ref*(1+tp/100) and tp_bar is None: tp_bar=i
                    if bar['low']<=ref*(1-structural_sl/100) and sl_bar is None: sl_bar=i
                else:
                    if bar['low']<=ref*(1-tp/100) and tp_bar is None: tp_bar=i
                    if bar['high']>=ref*(1+structural_sl/100) and sl_bar is None: sl_bar=i
                if tp_bar and sl_bar: break
            tp_first=tp_bar is not None and (sl_bar is None or tp_bar<sl_bar)
            sl_first=sl_bar is not None and (tp_bar is None or sl_bar<tp_bar)

            end_i=min(si+WIN,len(bars_all)-1);wb=bars_all[si:end_i+1]
            if d=='buy': mae=round((ref-min(b['low'] for b in wb))/ref*100,2)
            else: mae=round((max(b['high'] for b in wb)-ref)/ref*100,2)

            events.append({'sym':sym,'dir':d,'price':ref,'idx':si,'date':bars_all[si]['date'],
                          'bonus':bonus,'align30':align_bonus,'rev_exhaust':rev_bonus,
                          'trend':trend_bonus,'sl_source':sl_source,
                          'tp_first':tp_first,'sl_first':sl_first,'mae':mae,'tp':tp})

# ═══════ 输出 ═══════
buy=[e for e in events if e['dir']=='buy']
sell=[e for e in events if e['dir']=='sell']
# 结构止损覆盖率
struct_sl=[e for e in events if 'fallback' not in e.get('sl_source','fallback')]
print(f'赚钱系统v2.1 (SL=结构位/回退{SL_FALLBACK}% TP={TP_MAIN}%/{TP_ALT}% bonus≥{BONUS_MIN})')
print(f'信号: 买{len(buy)} 卖{len(sell)} 共{len(events)}  结构止损覆盖:{len(struct_sl)}/{len(events)}')
print(f'bonus升级: +30min共振 +力度衰竭 +趋势方向\n')

# 按币种
print(f'{"币种":>10s} | {"信号":>4s} | {"胜率":>6s} | {"SL率":>5s} | {"盈亏比":>7s} | {"最深MAE":>7s}')
print('-'*60)
for sym in SYMS:
    evs=[e for e in events if e['sym']==sym]
    if not evs: continue
    t=len(evs);tp_n=sum(1 for e in evs if e['tp_first']);sl_n=sum(1 for e in evs if e['sl_first'])
    m=max(abs(e['mae']) for e in evs)
    print(f'{sym:>10s} | {t:>4d} | {tp_n/t*100:>5.0f}% | {sl_n/t*100:>4.0f}% | {tp_n/max(sl_n,1):>6.0f}:1 | {m:>6.2f}%')

# bonus分层
print(f'\n{"bonus":>6s} | {"信号":>4s} | {"胜率":>6s} | {"SL率":>5s} | {"盈亏比":>7s} | {"仓位":>4s} | {"趋势+":>5s}')
print('-'*55)
for b in [1,2,3]:
    evs=[e for e in events if e['bonus']==b]
    if not evs: continue
    t=len(evs);tp_n=sum(1 for e in evs if e['tp_first']);sl_n=sum(1 for e in evs if e['sl_first'])
    trend_n=sum(1 for e in evs if e.get('trend'))
    advice='加仓' if b>=3 else ('标准' if b>=1 else '不交易')
    print(f'{b:>6d} | {t:>4d} | {tp_n/t*100:>5.0f}% | {sl_n/t*100:>4.0f}% | {tp_n/max(sl_n,1):>6.0f}:1 | {advice:>4s} | {trend_n:>5d}')
    if not evs: continue
    t=len(evs);tp_n=sum(1 for e in evs if e['tp_first']);sl_n=sum(1 for e in evs if e['sl_first'])
    print(f'{b:>6d} | {t:>4d} | {tp_n/t*100:>5.0f}% | {sl_n/t*100:>4.0f}% | {tp_n/max(sl_n,1):>6.0f}:1 | {"加仓" if b>=2 else "标准":>4s}')

# 汇总
t=len(events);tp_n=sum(1 for e in events if e['tp_first']);sl_n=sum(1 for e in events if e['sl_first'])
print(f'\n{"="*60}')
print(f'汇总: {t}信号 | 胜率={tp_n/t*100:.0f}% SL率={sl_n/t*100:.0f}% 未触达={(t-tp_n-sl_n)/t*100:.0f}%')
print(f'盈亏比={tp_n/max(sl_n,1):.1f}:1')
maes=sorted([abs(e['mae']) for e in events])
print(f'MAE: P50={maes[len(maes)//2]:.2f}% P95={maes[int(len(maes)*0.95)-1]:.2f}% 最深={max(maes):.2f}%')
