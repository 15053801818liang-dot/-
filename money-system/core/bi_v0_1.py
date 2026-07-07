"""
笔 v0.1 — 5个关节全钉死
========================
1. min_bars → mid_index差 ≥ 3
2. 突破 → extreme（分型存 mid + extreme）
3. 同向冲突 → 保留终点更极端者
4. 失败跳过 → candidate跳过，start遇更极端更新
5. 边界 → 包含处理先行，严格>，pending不入confirmed
"""


def find_fenxing_v01(bars: list[dict]) -> list[dict]:
    """
    顶底分型识别 — 同时存 mid 值和 extreme 值

    分型字段:
      type: '顶分型' | '底分型'
      mid_index: 中间K线在bars中的位置
      mid_high, mid_low: 中间K线的高低点
      extreme_high: 三根K线最高点
      extreme_low: 三根K线最低点
      date: 中间K线日期
    """
    fxs = []
    for i in range(1, len(bars) - 1):
        left, mid, right = bars[i-1], bars[i], bars[i+1]

        # 顶分型: mid.high 三根最高，mid.low 三根最高
        if (mid['high'] > left['high'] and mid['high'] > right['high'] and
                mid['low'] > left['low'] and mid['low'] > right['low']):

            # 等高处理: 严格>
            fxs.append({
                'type': '顶分型',
                'mid_index': i,
                'mid_high': mid['high'],
                'mid_low': mid['low'],
                'extreme_high': max(left['high'], mid['high'], right['high']),
                'extreme_low': min(left['low'], mid['low'], right['low']),
                'date': mid['date'],
            })

        # 底分型: mid.low 三根最低，mid.high 三根最低
        if (mid['low'] < left['low'] and mid['low'] < right['low'] and
                mid['high'] < left['high'] and mid['high'] < right['high']):

            fxs.append({
                'type': '底分型',
                'mid_index': i,
                'mid_high': mid['high'],
                'mid_low': mid['low'],
                'extreme_high': max(left['high'], mid['high'], right['high']),
                'extreme_low': min(left['low'], mid['low'], right['low']),
                'date': mid['date'],
            })

    # 去重: 相邻同类型保留更极端的
    cleaned = []
    for fx in fxs:
        if not cleaned:
            cleaned.append(fx)
            continue
        last = cleaned[-1]
        if fx['type'] == last['type']:
            # 顶分型保留 extreme_high 更高的
            if fx['type'] == '顶分型' and fx['extreme_high'] > last['extreme_high']:
                cleaned[-1] = fx
            elif fx['type'] == '顶分型' and fx['extreme_high'] == last['extreme_high']:
                # 等高取 mid_high 更高者
                if fx['mid_high'] > last['mid_high']:
                    cleaned[-1] = fx
            # 底分型保留 extreme_low 更低的
            elif fx['type'] == '底分型' and fx['extreme_low'] < last['extreme_low']:
                cleaned[-1] = fx
            elif fx['type'] == '底分型' and fx['extreme_low'] == last['extreme_low']:
                if fx['mid_low'] < last['mid_low']:
                    cleaned[-1] = fx
        else:
            cleaned.append(fx)

    # 兼容别名（旧代码用 idx/high/low）
    for fx in cleaned:
        fx['idx'] = fx['mid_index']
        fx['high'] = fx['mid_high']
        fx['low'] = fx['mid_low']
    return cleaned


def find_bi_v01(bars: list[dict], fxs: list[dict], min_separation: int = 3) -> list[dict]:
    """
    笔 v0.1 状态机构造

    min_separation: 两个分型 mid_index 的最小差值。
                    3 表示 start_mid, 中间, 中间, end_mid
                    即中间至少隔 2 根独立K线。

    分型间距离: end.mid_index - start.mid_index >= min_separation

    成立条件 向上笔(bottom→top):
      end.extreme_high > max(start.left.high, start.mid.high, start.right.high)

    成立条件 向下笔(top→bottom):
      end.extreme_low < min(start.left.low, start.mid.low, start.right.low)
    """
    if len(fxs) < 2:
        return []

    bis = []
    start = fxs[0]

    for end in fxs[1:]:
        # ── 同向：更新 start（取更极端）──
        if end['type'] == start['type']:
            if start['type'] == '顶分型' and end['extreme_high'] > start['extreme_high']:
                start = end
            elif start['type'] == '底分型' and end['extreme_low'] < start['extreme_low']:
                start = end
            continue

        # ── 反向分型，尝试成笔 ──

        # 条件1: min_separation
        separation = end['mid_index'] - start['mid_index']
        if separation < min_separation:
            # candidate 太近，跳过 candidate，start 不变
            continue

        # 条件2: 突破（用 extreme）
        if start['type'] == '顶分型':
            # 向下笔: end.extreme_low < start的3根K线最低low
            # start是顶分型，start的3根K线最低low = start.extreme_low
            if not (end['extreme_low'] < start['extreme_low']):
                # 条件2失败，跳过 candidate
                continue
            direction = '向下笔'
        else:
            # 向上笔: end.extreme_high > start的3根K线最高high
            if not (end['extreme_high'] > start['extreme_high']):
                continue
            direction = '向上笔'

        # ── 条件1+2都满足 → 候选笔成立 ──
        candidate = {
            'from': start, 'to': end,
            'direction': direction,
            'bar_count': separation,
        }

        if not bis:
            bis.append(candidate)
            start = end
            continue

        # ── 条件3: 方向交替 ──
        last = bis[-1]

        if candidate['direction'] != last['direction']:
            bis.append(candidate)
            start = end
        else:
            # 同向冲突：保留终点更极端者
            if direction == '向上笔':
                # 保留终点 extreme_high 更高者
                if end['extreme_high'] > last['to']['extreme_high']:
                    bis[-1] = candidate
                    start = end
                # 否则丢弃 candidate，start 也不更新
            else:
                # 保留终点 extreme_low 更低者
                if end['extreme_low'] < last['to']['extreme_low']:
                    bis[-1] = candidate
                    start = end

    return bis


# ═══════════════════════════════════════
# 兼容旧接口
# ═══════════════════════════════════════

def find_fenxing(bars: list[dict]) -> list[dict]:
    """旧接口兼容"""
    return find_fenxing_v01(bars)


def find_bi(bars: list[dict], fxs: list[dict], min_bars: int = 5) -> list[dict]:
    """
    旧接口兼容: min_bars 转换为 min_separation
    min_separation = min_bars + 1（因为separation统计的是mid_index差）
    例如 min_bars=2 → min_separation=3（中间隔2根K线）
    """
    return find_bi_v01(bars, fxs, min_separation=min_bars + 1)
