"""
线段 v0.2 — 5关节 + 4钉子 + 状态机
====================================
关节1: 前三笔方向交替 + 共同重叠区间
关节2: 特征序列 = 反向笔价格区间（隔一取一）
关节3: CS包含处理 → 向上取高高/高低，向下取低低/低高
关节4: CS分型 → 向上只找顶，向下只找底（双层确认）
关节5: 终点确认 → 第一种(无缺口)/第二种(有缺口+反向分型)

状态机: candidate → extending → pending_break → confirmed_end
钉子: CS存source / 包含合并来源 / 缺口后用处理后CS / 奇偶只校验
"""


def _pen_range(bi: dict) -> tuple:
    h = max(bi['from']['extreme_high'], bi['to']['extreme_high'])
    l = min(bi['from']['extreme_low'], bi['to']['extreme_low'])
    return l, h


def _three_overlap(b1, b2, b3) -> bool:
    l1, h1 = _pen_range(b1); l2, h2 = _pen_range(b2); l3, h3 = _pen_range(b3)
    return min(h1, h2, h3) > max(l1, l2, l3)


def _directions_alternate(b1, b2, b3) -> bool:
    return b1['direction'] != b2['direction'] and b2['direction'] != b3['direction']


def build_feature_sequence(bis, start_idx, duan_direction):
    """向上→取向下笔, 向下→取向上笔。隔一取一(start+1,start+3...)"""
    expected = '向下笔' if duan_direction == '向上线段' else '向上笔'
    cs = []
    idx = start_idx + 1
    while idx < len(bis):
        bi = bis[idx]
        if bi['direction'] == expected:
            lo, hi = _pen_range(bi)
            cs.append({'bi_index': idx, 'source_bi_indices': [idx],
                       'low': lo, 'high': hi})
        idx += 2
    return cs


def normalize_cs(cs_list, duan_direction):
    """向上→高高/高低, 向下→低低/低高。合并来源。"""
    if len(cs_list) < 2: return cs_list
    is_up = (duan_direction == '向上线段')
    result = [cs_list[0]]
    for curr in cs_list[1:]:
        prev = result[-1]
        pc = prev['high'] >= curr['high'] and prev['low'] <= curr['low']
        cc = curr['high'] >= prev['high'] and curr['low'] <= prev['low']
        if pc or cc:
            merged = {'high': max(prev['high'], curr['high']),
                      'low': max(prev['low'], curr['low'])} if is_up else \
                     {'high': min(prev['high'], curr['high']),
                      'low': min(prev['low'], curr['low'])}
            result[-1] = {**merged,
                          'bi_index': curr['bi_index'],
                          'source_bi_indices': prev.get('source_bi_indices', [prev['bi_index']]) +
                                               curr.get('source_bi_indices', [curr['bi_index']])}
        else:
            result.append(curr)
    return result


def find_cs_fractal(cs_list, duan_direction):
    """向上找顶分型, 向下找底分型。双层确认(high+low)。"""
    if len(cs_list) < 3: return None
    is_up = (duan_direction == '向上线段')
    for i in range(1, len(cs_list) - 1):
        L, M, R = cs_list[i-1], cs_list[i], cs_list[i+1]
        if is_up:
            if M['high'] > L['high'] and M['high'] > R['high'] and \
               M['low'] > L['low'] and M['low'] > R['low']:
                return {'index': i, 'left': L, 'mid': M, 'right': R}
        else:
            if M['low'] < L['low'] and M['low'] < R['low'] and \
               M['high'] < L['high'] and M['high'] < R['high']:
                return {'index': i, 'left': L, 'mid': M, 'right': R}
    return None


def _has_gap(a, b):
    return a['high'] < b['low'] or b['high'] < a['low']


def confirm_duan_end(cs_std, fractal, duan_direction):
    """关5: 无缺口→直接确认; 有缺口→后继处理后CS找反向分型。"""
    left, mid = fractal['left'], fractal['mid']
    if not _has_gap(left, mid):
        return {'confirmed': True,
                'end_bi_index': max(mid.get('source_bi_indices', [mid['bi_index']])),
                'gap_type': 1}

    after = cs_std[fractal['index'] + 1:]
    if len(after) < 3:
        return {'confirmed': False, 'end_bi_index': None, 'gap_type': 2}

    reverse_dir = '向下线段' if duan_direction == '向上线段' else '向上线段'
    rf = find_cs_fractal(after, reverse_dir)
    if rf is not None:
        return {'confirmed': True,
                'end_bi_index': max(mid.get('source_bi_indices', [mid['bi_index']])),
                'gap_type': 2}
    return {'confirmed': False, 'end_bi_index': None, 'gap_type': 2}


def find_duan(bis):
    """线段 v0.2: 5关节+状态机 extending→pending→confirmed"""
    if len(bis) < 3: return []
    duans = []
    i = 0

    while i <= len(bis) - 3:
        b1, b2, b3 = bis[i], bis[i+1], bis[i+2]
        if not _directions_alternate(b1, b2, b3) or not _three_overlap(b1, b2, b3):
            i += 1; continue

        duan_dir = '向上线段' if b1['direction'] == '向上笔' else '向下线段'
        start = i
        search_offset = 0  # 在cs_std中搜索分型的偏移

        while True:
            cs_raw = build_feature_sequence(bis, start, duan_dir)
            if len(cs_raw) < 3: break
            cs_std = normalize_cs(cs_raw, duan_dir)
            if search_offset >= len(cs_std) - 2: break

            fx = find_cs_fractal(cs_std[search_offset:], duan_dir)
            if fx is None: break

            full_idx = search_offset + fx['index']
            fx_full = {'index': full_idx,
                       'left': cs_std[full_idx-1],
                       'mid': cs_std[full_idx],
                       'right': cs_std[full_idx+1]}

            result = confirm_duan_end(cs_std, fx_full, duan_dir)
            if result['confirmed']:
                end = result['end_bi_index']
                if end - start >= 2:
                    fb, lb = bis[start], bis[end]
                    if fb['direction'] != lb['direction']:
                        duans.append({
                            'from_bi': start, 'to_bi': end,
                            'from': fb['from'], 'to': lb['to'],
                            'direction': duan_dir,
                            'bi_count': end - start + 1,
                            'start_idx': min(fb['from']['mid_index'], fb['to']['mid_index']),
                            'end_idx': max(lb['from']['mid_index'], lb['to']['mid_index']),
                            'gap_type': result['gap_type'],
                        })
                        i = end + 1
                        break  # 线段确认，跳出延伸循环
                # 校验失败，跳过此分型继续
                search_offset = full_idx + 1
                continue

            # pending_break: 有缺口无反确认 → 继续延伸，从下一个CS位置搜索
            search_offset = full_idx + 1

        # 如果没有确认线段，步进
        if i < start + 3 or (duans and duans[-1]['from_bi'] != start):
            i += 1
        # else: i已在确认段中更新

    return duans
