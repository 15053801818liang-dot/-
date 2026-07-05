"""合成 K 线样本，供 demo 与测试共用。

通过在一串交替的转折价位之间线性插值，生成带有清晰
分型/笔/中枢/背驰结构的理想化行情，便于稳定演示与断言。
"""

from __future__ import annotations

from typing import List, Sequence

from .models import Bar


def synth_bars(
    turning_points: Sequence[float],
    seg_len: int = 5,
    half_width: float = 0.5,
) -> List[Bar]:
    """在相邻转折价位之间线性插值，生成 Bar 序列。

    每根 K 线的 high/low 取插值中价 ± half_width，close 取中价。
    """
    bars: List[Bar] = []
    idx = 0
    if not turning_points:
        return bars

    prev = turning_points[0]
    for nxt in turning_points[1:]:
        for s in range(1, seg_len + 1):
            p = prev + (nxt - prev) * s / seg_len
            bars.append(
                Bar(
                    index=idx,
                    high=p + half_width,
                    low=p - half_width,
                    open=p,
                    close=p,
                )
            )
            idx += 1
        prev = nxt
    return bars


def sample_bars() -> List[Bar]:
    """下降通道行情：跌幅逐段衰减且连创新低，末端形成底背驰（第一类买点）。

    转折序列前置一段横盘用于让 MACD 收敛，避免指标启动期干扰背驰判定。
    """
    turning_points = [
        200.0, 200.0, 200.0,  # 横盘预热（让 MACD 收敛）
        150.0,  # 第一段大幅下跌（力度大）
        175.0,  # 反弹
        130.0,  # 下跌（创新低）
        160.0,  # 反弹
        118.0,  # 下跌（再创新低，但力度衰减 → 底背驰）
        150.0,  # 反弹
        112.0,  # 收尾
    ]
    return synth_bars(turning_points, seg_len=6, half_width=0.5)


def sample_bars_pivot() -> List[Bar]:
    """盘整中枢 + 向上突破 + 回调不回中枢（第三类买点）。"""
    turning_points = [
        100.0, 100.0,  # 预热
        92.0, 108.0, 94.0, 106.0, 95.0,  # 窄幅震荡构成中枢
        150.0,  # 向上突破，离开中枢
        128.0,  # 回调不回中枢上沿 → 三类买点
        160.0,  # 继续上行
    ]
    return synth_bars(turning_points, seg_len=5, half_width=0.4)
