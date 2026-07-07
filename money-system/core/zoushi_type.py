"""
走势类型 v0.1
=============
输入：中枢序列
输出：盘整 | 上涨 | 下跌

规则：
  盘整：只含1个中枢（或中枢间有重叠，实为同一中枢延伸）
  上涨：≥2个中枢，后一中枢整体高于前一中枢
  下跌：≥2个中枢，后一中枢整体低于前一中枢
"""


def _zs_overlap(z1, z2):
    """两中枢是否有重叠——重叠=同一中枢延伸，不是两个独立中枢"""
    return z2['zg'] > z1['zd'] and z1['zg'] > z2['zd']


def _zs_centroid(z):
    """中枢重心 = (ZG+ZD)/2"""
    return (z['zg'] + z['zd']) / 2


def merge_overlapping_zhongshu(zs_list):
    """
    合并重叠中枢——相邻中枢有重叠视为同一中枢的延伸。
    返回去重后的独立中枢列表。
    """
    if len(zs_list) < 2:
        return zs_list

    merged = [zs_list[0]]
    for z in zs_list[1:]:
        prev = merged[-1]
        if _zs_overlap(prev, z):
            # 重叠→合并（取范围并集）
            merged[-1] = {
                'zg': max(prev['zg'], z['zg']),
                'zd': min(prev['zd'], z['zd']),
                'start_duan': prev.get('start_duan', prev.get('start_idx', 0)),
                'end_duan': z.get('end_duan', z.get('end_idx', 0)),
                'start_idx': min(prev.get('start_idx', 0), z.get('start_idx', 0)),
                'end_idx': max(prev.get('end_idx', 0), z.get('end_idx', 0)),
            }
        else:
            merged.append(z)
    return merged


def classify_zoushi(zs_list):
    """
    走势类型分类

    Args:
        zs_list: 中枢列表，每个元素含 zg, zd

    Returns:
        {
            'type': '盘整' | '上涨' | '下跌' | '未知',
            'zs_count': int,        # 独立中枢数
            'centroids': [float],    # 各中枢重心
            'direction': 'up' | 'down' | 'flat' | 'unknown',
        }
    """
    # 去重：重叠中枢合并
    independent = merge_overlapping_zhongshu(zs_list)
    n = len(independent)

    centroids = [_zs_centroid(z) for z in independent]

    if n == 0:
        return {'type': '未知', 'zs_count': 0, 'centroids': [],
                'direction': 'unknown'}

    if n == 1:
        return {'type': '盘整', 'zs_count': 1, 'centroids': centroids,
                'direction': 'flat'}

    # ≥2个中枢：看重心方向
    ups = sum(1 for i in range(1, n) if centroids[i] > centroids[i-1])
    downs = sum(1 for i in range(1, n) if centroids[i] < centroids[i-1])

    if ups > downs:
        return {'type': '上涨', 'zs_count': n, 'centroids': centroids,
                'direction': 'up'}
    elif downs > ups:
        return {'type': '下跌', 'zs_count': n, 'centroids': centroids,
                'direction': 'down'}
    else:
        # 等数 → 盘整
        return {'type': '盘整', 'zs_count': n, 'centroids': centroids,
                'direction': 'flat'}
