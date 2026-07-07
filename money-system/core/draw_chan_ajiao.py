"""
缠论画图 — 阿娇A0版（线段→中枢）
================================
A0 = 线段（不是笔）
min_bars = 5（缠师后期标准）
包含处理初始方向 = 可配置参数

对照：原版draw_chan.py用的是 笔→中枢（A0=笔，min_bars=2）
"""

import sys, csv
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.dates import date2num
import matplotlib.font_manager as fm
from datetime import datetime

# CJK字体
for f in fm.fontManager.ttflist:
    if any(k in f.name for k in ['Microsoft YaHei', 'SimHei', 'WenQuanYi',
                                    'CJK', 'Sarasa', 'Source Han']):
        plt.rcParams['font.family'] = f.name
        break
else:
    plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

BASE = Path(__file__).parent
OUT_DIR = BASE / "reports" / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════
# 第1步：K线包含处理（第62课）
# ═══════════════════════════════════════════

def kxian_baohan(bars: list[dict]) -> list[dict]:
    """
    K线包含处理（第62/65课）

    方向不预设。方向从走势中自己长出来：
    - 无包含关系的相邻K线确定方向：gn>=gn-1→向上，dn<=dn-1→向下（65课）
    - 有包含关系时按已确定的方向合并
    - 方向未知时遇到包含：不合并，等方向自己出现

    initial_direction参数已删除——方向不是外部常量，是内生变量。
    """
    if len(bars) < 2:
        return bars

    result = [bars[0]]
    direction = 0  # 0=未知, 1=向上, -1=向下（不从外部注入）

    for i in range(1, len(bars)):
        prev = result[-1]
        curr = bars[i]

        prev_contains_curr = prev['high'] >= curr['high'] and prev['low'] <= curr['low']
        curr_contains_prev = curr['high'] >= prev['high'] and curr['low'] <= prev['low']
        has_inclusion = prev_contains_curr or curr_contains_prev

        if not has_inclusion:
            # 无包含关系 → 用这对K线确定方向（65课）
            # gn>=gn-1 → 向上; dn<=dn-1 → 向下
            # 在无包含前提下，两者互斥且必有一个成立（65课数学证明）
            if curr['high'] >= prev['high']:
                direction = 1
            elif curr['low'] <= prev['low']:
                direction = -1
            # else: highs相等且lows相等 → K线完全相等，极罕见，维持原方向
            result.append(curr)
            continue

        # 有包含关系
        if direction == 0:
            # 方向未知 → 不做合并，等方向从后续K线中自己长出来
            # 这一对K线原样保留，后续无包含K线对会确定方向
            result.append(curr)
            continue

        # 方向已知 → 按方向合并
        if direction == 1:  # 向上：取高高、取高低
            merged = {
                'date': curr['date'],
                'high': max(prev['high'], curr['high']),
                'low': max(prev['low'], curr['low']),
                'open': prev['open'],
                'close': max(prev['close'], curr['close']),
                '_merged_from': [prev.get('_orig_date', prev['date']),
                                 curr.get('_orig_date', curr['date'])],
            }
        else:  # 向下：取低低、取低高
            merged = {
                'date': curr['date'],
                'high': min(prev['high'], curr['high']),
                'low': min(prev['low'], curr['low']),
                'open': prev['open'],
                'close': min(prev['close'], curr['close']),
                '_merged_from': [prev.get('_orig_date', prev['date']),
                                 curr.get('_orig_date', curr['date'])],
            }

        for k in bars[i]:
            if k not in merged:
                merged[k] = bars[i][k]
        result[-1] = merged

    return result


# ═══════════════════════════════════════════
# 第2-3步：分型 + 笔 — 已升级到 bi_v0.1
# ═══════════════════════════════════════════
from bi_v0_1 import find_fenxing, find_bi, find_fenxing_v01, find_bi_v01


# ═══════════════════════════════════════════
# 第4步：线段（第65-71课）— 已升级到 duan_v0.1
# ═══════════════════════════════════════════
from duan_v0_1 import find_duan

def _pen_range(bi: dict) -> tuple:
    """一笔的价格区间"""
    h = max(bi['from']['high'], bi['to']['high'])
    l = min(bi['from']['low'], bi['to']['low'])
    return h, l


def _check_overlap(r1_hi, r1_lo, r2_hi, r2_lo) -> bool:
    """两个区间是否有重叠"""
    return min(r1_hi, r2_hi) > max(r1_lo, r2_lo)


def _build_cs(bis: list[dict], seg_start: int, seg_dir: str) -> list[dict]:
    """
    构建特征序列（67课）

    向上线段→特征序列由向下笔构成（seg_start之后的奇数位置笔）
    向下线段→特征序列由向上笔构成（seg_start之后的奇数位置笔）

    每个特征序列元素用一根"K线"表示：
    high = 笔的高点范围的最高值, low = 笔的低点范围的最低值
    """
    cs = []
    idx = seg_start + 1  # 第一个特征序列元素从第二笔开始
    expected_dir = '向下笔' if seg_dir == '向上线段' else '向上笔'

    while idx < len(bis):
        bi = bis[idx]
        if bi['direction'] == expected_dir:
            h, l = _pen_range(bi)
            cs.append({
                'pen_idx': idx,
                'high': h,
                'low': l,
                'from_date': bi['from']['date'],
                'to_date': bi['to']['date'],
            })
        idx += 2  # 跳一笔（特征序列元素间隔一笔）
    return cs


def _cs_baohan(cs: list[dict]) -> list[dict]:
    """
    特征序列标准化——对CS元素做包含处理（67课）

    方向由线段方向决定。但我们在这里只是做"非包含处理"——
    把重叠的CS元素合并，去除冗余。
    对于向上线段的CS序列，只关心顶分型→向下包含处理方向。
    对于向下线段的CS序列，只关心底分型→向上包含处理方向。

    简化：CS元素按顺序相邻处理，有重叠→合并（取范围并集）
    """
    if len(cs) < 2:
        return cs

    result = [cs[0]]
    for i in range(1, len(cs)):
        prev, curr = result[-1], cs[i]
        # 检查是否有重叠（CS元素间的"包含"）
        prev_contains = prev['high'] >= curr['high'] and prev['low'] <= curr['low']
        curr_contains = curr['high'] >= prev['high'] and curr['low'] <= prev['low']

        if prev_contains or curr_contains:
            # 合并：取范围并集
            result[-1] = {
                'high': max(prev['high'], curr['high']),
                'low': min(prev['low'], curr['low']),
                'pen_idx': curr['pen_idx'],  # 保留较新的索引
                'from_date': prev.get('from_date', ''),
                'to_date': curr.get('to_date', ''),
                '_merged': True,
            }
        else:
            result.append(curr)
    return result


def _find_cs_fx(cs: list[dict], seg_dir: str) -> int:
    """
    在标准特征序列中找分型（67课）

    向上线段→只找顶分型（CS元素构成的顶）
    向下线段→只找底分型（CS元素构成的底）

    返回分型在CS中的索引，-1表示未找到
    """
    if len(cs) < 3:
        return -1

    for i in range(1, len(cs) - 1):
        left, mid, right = cs[i-1], cs[i], cs[i+1]
        if seg_dir == '向上线段':
            # 顶分型：mid.high > left.high AND mid.high > right.high
            #         mid.low > left.low AND mid.low > right.low
            if (mid['high'] > left['high'] and mid['high'] > right['high'] and
                mid['low'] > left['low'] and mid['low'] > right['low']):
                return i
        else:
            # 底分型：mid.low < left.low AND mid.low < right.low
            #         mid.high < left.high AND mid.high < right.high
            if (mid['low'] < left['low'] and mid['low'] < right['low'] and
                mid['high'] < left['high'] and mid['high'] < right['high']):
                return i
    return -1


# find_duan 已升级到 duan_v0_1，见顶部 import


# ═══════════════════════════════════════════
# 第5步：从线段找中枢（第17-20课）
# ═══════════════════════════════════════════

def find_zhongshu_from_duan(duans: list[dict]) -> list[dict]:
    """
    从线段找中枢 — 阿娇A0路径

    中枢：至少连续三段线段的重叠区间
    ZG = 三段线段高点最小值
    ZD = 三段线段低点最大值
    """
    if len(duans) < 3:
        return []

    zhongshu_list = []
    for i in range(len(duans) - 2):
        d1, d2, d3 = duans[i], duans[i+1], duans[i+2]

        all_highs = [max(d['from']['high'], d['to']['high']) for d in [d1, d2, d3]]
        all_lows = [min(d['from']['low'], d['to']['low']) for d in [d1, d2, d3]]

        zg = min(all_highs)
        zd = max(all_lows)

        if zg > zd:
            zhongshu_list.append({
                'zg': zg, 'zd': zd,
                'duan_count': 3,
                'start_duan': i, 'end_duan': i + 2,
                'start_idx': min(d1['start_idx'], d2['start_idx'], d3['start_idx']),
                'end_idx': max(d1['end_idx'], d2['end_idx'], d3['end_idx']),
                'width_pct': round((zg - zd) / zd * 100, 2) if zd > 0 else 0,
            })

    return zhongshu_list


# ═══════════════════════════════════════════
# 画图
# ═══════════════════════════════════════════

def draw_chan(bars: list[dict], fxs: list[dict], bis: list[dict],
              duans: list[dict], zhongshu: list[dict],
              output_path: str, title: str = "", n_bars: int = 100):
    """画K线 + 分型 + 笔 + 线段 + 中枢"""

    plot_bars = bars[-n_bars:]
    offset = len(bars) - n_bars

    # 调整标注index
    plot_fxs = [f for f in fxs if f['idx'] >= offset]
    for f in plot_fxs:
        f['plot_idx'] = f['idx'] - offset

    plot_bis_list = [b for b in bis if b['from']['idx'] >= offset]
    plot_duans = [d for d in duans if d['start_idx'] >= offset]

    dates = [b['date'] for b in plot_bars]
    try:
        x_dates = [datetime.strptime(d, '%Y-%m-%d') for d in dates]
        x_nums = date2num(x_dates)
    except:
        x_dates = list(range(len(dates)))
        x_nums = list(range(len(dates)))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(24, 14),
                                     gridspec_kw={'height_ratios': [3, 1]})

    # ── K线实体 ──
    for i, bar in enumerate(plot_bars):
        x = x_nums[i]
        o, h, l, c = bar['open'], bar['high'], bar['low'], bar['close']
        color = 'red' if c >= o else 'green'
        ax1.plot([x, x], [l, h], color=color, linewidth=0.8)
        body_h = max(abs(c - o), 0.01)
        ax1.add_patch(plt.Rectangle((x - 0.4, min(c, o)), 0.8, body_h,
                                     facecolor=color, edgecolor=color, alpha=0.8))

    # ── 分型 ──
    for fx in plot_fxs:
        xi = fx['plot_idx']
        x = x_nums[xi]
        if fx['type'] == '顶分型':
            ax1.annotate('顶', (x, fx['high']), textcoords="offset points",
                        xytext=(0, 10), ha='center', fontsize=7, color='red',
                        fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='pink', alpha=0.7))
            ax1.plot(x, fx['high'], 'rv', markersize=6)
        else:
            ax1.annotate('底', (x, fx['low']), textcoords="offset points",
                        xytext=(0, -15), ha='center', fontsize=7, color='green',
                        fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='lightgreen', alpha=0.7))
            ax1.plot(x, fx['low'], 'g^', markersize=6)

    # ── 笔 ──
    for bi in plot_bis_list:
        x1 = x_nums[bi['from']['idx'] - offset]
        x2 = x_nums[bi['to']['idx'] - offset]
        y1 = bi['from']['high'] if bi['from']['type'] == '顶分型' else bi['from']['low']
        y2 = bi['to']['low'] if bi['to']['type'] == '底分型' else bi['to']['high']
        bi_color = '#d62728' if bi['direction'] == '向下笔' else '#2ca02c'
        ax1.plot([x1, x2], [y1, y2], color=bi_color, linewidth=1.5, alpha=0.6)

    # ── 线段（阿娇A0）── 粗线突出
    for d in plot_duans:
        x1 = x_nums[d['start_idx'] - offset]
        x2 = x_nums[d['end_idx'] - offset]
        y1 = d['from']['high'] if d['direction'] == '向下线段' else d['from']['low']
        y2 = d['to']['low'] if d['direction'] == '向下线段' else d['to']['high']
        duan_color = '#8B0000' if d['direction'] == '向下线段' else '#006400'
        ax1.plot([x1, x2], [y1, y2], color=duan_color, linewidth=3.5, alpha=0.9)
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        ax1.annotate(f"段({d['bi_count']}笔)", (mid_x, mid_y),
                    fontsize=8, color=duan_color, fontweight='bold', alpha=0.9)

    # ── 中枢（从线段）── 黄色框
    for zs in zhongshu:
        xs = zs['start_idx'] - offset
        xe = zs['end_idx'] - offset
        if xs < 0 or xe >= len(plot_bars):
            continue
        x_start = x_nums[xs]
        x_end = x_nums[xe]
        rect = mpatches.FancyBboxPatch(
            (x_start - 0.2, zs['zd']), x_end - x_start + 0.4, zs['zg'] - zs['zd'],
            boxstyle="round,pad=0.1", facecolor='yellow', edgecolor='orange',
            alpha=0.3, linewidth=2)
        ax1.add_patch(rect)
        mid_x = (x_start + x_end) / 2
        ax1.annotate(f"中枢[{zs['width_pct']}%]\n{zg:.2f}/{zd:.2f}",
                    (mid_x, zs['zg']), fontsize=7, ha='center', color='orange',
                    fontweight='bold')

    # ── 成交量 ──
    vols = [b.get('volume', 0) for b in plot_bars]
    colors_vol = ['red' if b['close'] >= b['open'] else 'green' for b in plot_bars]
    ax2.bar(range(len(vols)), vols, color=colors_vol, alpha=0.5, width=0.8)

    # ── 格式 ──
    ax1.set_title(f"缠论·阿娇A0: {title}\n(▲底/▼顶) 绿线=笔 粗线=线段(A0) 黄框=中枢",
                  fontsize=13)
    ax1.set_ylabel('Price')
    ax2.set_ylabel('Volume')
    if isinstance(x_dates[0], datetime):
        ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y-%m'))
    step = max(1, len(plot_bars) // 12)
    tick_positions = list(range(0, len(plot_bars), step))
    tick_labels = [dates[i][:7] if i < len(dates) else '' for i in tick_positions]
    ax1.set_xticks(tick_positions)
    ax1.set_xticklabels(tick_labels, rotation=45, fontsize=8)
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels(tick_labels, rotation=45, fontsize=8)
    ax1.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  图已保存: {output_path}")


# ═══════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════

def load_data(code="600900", n_bars=200, period=""):
    """加载K线数据。period=""为日线，"30min"等为分钟线"""
    suffix = f"_{period}" if period else ""
    csv_path = BASE / "reports" / "cache" / f"{code}{suffix}.csv"
    if not csv_path.exists():
        print(f"数据不存在: {csv_path}")
        return []
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 兼容不同列名和列序（日线/分钟线CSV格式不同）
            date_val = row.get('date', row.get('日期', row.get('时间', '')))
            o = float(row.get('open', row.get('开盘', 0)))
            c = float(row.get('close', row.get('收盘', 0)))
            h = float(row.get('high', row.get('最高', 0)))
            l = float(row.get('low', row.get('最低', 0)))
            v = float(row.get('volume', row.get('成交量', 0))) if (row.get('volume') or row.get('成交量')) else 0
            rows.append({
                'date': date_val, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v,
            })
    # 按日期排序（分钟线可能乱序）
    rows.sort(key=lambda r: r['date'])
    return rows[-n_bars:]


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

def run(code="600900", n_bars=200, min_bars=5, period=""):
    """
    阿娇A0管线：包含处理 → 分型 → 笔(min_bars=5) → 线段(A0) → 中枢
    period=""=日线, "30min"=30分钟线

    包含处理方向不从外部注入——由走势自身确定（65课：gn>=gn-1→向上,dn<=dn-1→向下）
    """
    print(f"{'='*60}")
    print(f"缠论·阿娇A0管线: {code}, {n_bars}根K线, period={period or '日线'}")
    print(f"A0=线段, min_bars={min_bars}, 包含方向=走势内生")
    print(f"{'='*60}")

    bars = load_data(code, n_bars, period)
    if not bars:
        return None

    for b in bars:
        b['_orig_date'] = b['date']

    # 第1步：包含处理（方向内生，不预设）
    print("\n[1/5] K线包含处理（方向内生）...")
    bars_bh = kxian_baohan(bars)
    print(f"  原始: {len(bars)} → 处理后: {len(bars_bh)} (合并{len(bars)-len(bars_bh)}根)")

    # 第2步：分型
    print("\n[2/5] 顶底分型识别...")
    fxs = find_fenxing(bars_bh)
    tops = sum(1 for f in fxs if f['type'] == '顶分型')
    bots = sum(1 for f in fxs if f['type'] == '底分型')
    print(f"  顶分型: {tops}, 底分型: {bots}")

    # 第3步：笔（min_bars=5）
    print(f"\n[3/5] 笔的构造 (min_bars={min_bars})...")
    bis = find_bi(bars_bh, fxs, min_bars=min_bars)
    ups = sum(1 for b in bis if b['direction'] == '向上笔')
    downs = sum(1 for b in bis if b['direction'] == '向下笔')
    print(f"  向上笔: {ups}, 向下笔: {downs}, 总计: {len(bis)}")

    if len(bis) < 3:
        print("\n  ⚠ 笔不足3根，无法构造线段和中枢")
        return {'bars': bars, 'bars_bh': bars_bh, 'fxs': fxs, 'bis': bis,
                'duans': [], 'zhongshu': []}

    # 第4步：线段（阿娇A0）
    print("\n[4/5] 线段识别（阿娇A0）...")
    duans = find_duan(bis)
    up_duan = sum(1 for d in duans if d['direction'] == '向上线段')
    down_duan = sum(1 for d in duans if d['direction'] == '向下线段')
    print(f"  向上线段: {up_duan}, 向下线段: {down_duan}, 总计: {len(duans)}")
    for i, d in enumerate(duans):
        print(f"    D{i+1}: {d['direction']}, {d['bi_count']}笔, "
              f"从{d['from']['date']}(idx={d['from']['idx']}) → {d['to']['date']}(idx={d['to']['idx']})")

    if len(duans) < 3:
        print("\n  ⚠ 线段不足3段，无法构造中枢")
        # 仍画图，但不标注中枢
        path = str(OUT_DIR / f"{code}_ajiao_A0_no_zs.png")
        draw_chan(bars, fxs, bis, duans, [], path,
                  title=f"{code} 阿娇A0(线段) — 线段<3无中枢 (min_bars={min_bars})",
                  n_bars=min(120, n_bars))
        return {'bars': bars, 'bars_bh': bars_bh, 'fxs': fxs, 'bis': bis,
                'duans': duans, 'zhongshu': []}

    # 第5步：中枢（从线段）
    print("\n[5/5] 中枢识别（从线段）...")
    zhongshu_list = find_zhongshu_from_duan(duans)
    print(f"  中枢数: {len(zhongshu_list)}")
    for i, zs in enumerate(zhongshu_list):
        print(f"    ZS{i+1}: ZG={zs['zg']:.2f} ZD={zs['zd']:.2f} "
              f"宽度={zs['width_pct']}% 段[{zs['start_duan']}-{zs['end_duan']}]")

    # 画图
    print("\n[画图] 生成标注图...")
    path = str(OUT_DIR / f"{code}_ajiao_A0.png")
    draw_chan(bars, fxs, bis, duans, zhongshu_list, path,
              title=f"{code} 阿娇A0(线段→中枢) min_bars={min_bars}",
              n_bars=min(120, n_bars))

    # ── 与原版对比 ──
    print(f"\n{'='*60}")
    print(f"阿娇A0 vs 原版 对比")
    print(f"{'='*60}")
    print(f"  参数差异:")
    print(f"    A0构件:     线段(阿娇) vs 笔(原版)")
    print(f"    min_bars:   {min_bars}(阿娇) vs 2(原版)")
    print(f"    中枢来源:   线段重叠(阿娇) vs 笔重叠(原版)")
    print(f"  结果:")
    print(f"    笔数量:      {len(bis)}")
    print(f"    线段数量:    {len(duans)}")
    print(f"    中枢数量:    {len(zhongshu_list)}")
    if zhongshu_list:
        widths = [zs['width_pct'] for zs in zhongshu_list]
        print(f"    中枢宽度:    min={min(widths)}% max={max(widths)}% avg={sum(widths)/len(widths):.1f}%")
    print(f"  原版中枢数:    0 (笔A0+min_bars=2 → 无重叠)")
    print(f"  结论: 阿娇的线段A0+min_bars=5 {'找到了中枢!' if zhongshu_list else '仍未找到中枢'}")

    # ── 裂缝记录 ──
    print(f"\n[裂缝] 阿娇A0管线:")
    print(f"  1. ✅ 已修复: 包含处理方向 — 内生（65课）")
    print(f"  2. ✅ 已修复: 笔区间高低条件（77课）— 过滤无效笔")
    print(f"  3. ✅ 已修复: 特征序列+第一/第二种情况（67/71课）")
    print(f"  4. 🟡 min_bars语义: 处理后K线计数，缠师推荐5针对日内，日线等比例调整")
    print(f"  5. 🟡 A0近似: 线段替代次级别走势类型（缠论A0研究的核心问题）")

    return {
        'bars': bars, 'bars_bh': bars_bh,
        'fxs': fxs, 'bis': bis,
        'duans': duans, 'zhongshu': zhongshu_list,
    }


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "600900"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    min_b = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    period = sys.argv[4] if len(sys.argv) > 4 else ""
    run(code, n, min_bars=min_b, period=period)
