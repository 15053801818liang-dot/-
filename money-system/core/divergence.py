# -*- coding: utf-8 -*-
"""
背驰检测模块 v0.2 — 级别权限集成
================================
v0.1: 最小可执行版 — MACD计算 + A/B段检测 + 6态状态机
v0.2: 级别权限集成 — 必须先过 level_guard，同级别才比较

输入：中枢 + 走势类型 + K线数据 + 级别
输出：DivergenceResult（6态状态机）

状态机：
  insufficient_data → no_divergence → pending → candidate → confirmed → failed

核心逻辑（24课）：
  顶背驰：B段价格创新高，但B段MACD面积 < A段MACD面积
  底背驰：B段价格创新低，但B段MACD面积 < A段MACD面积
  前提：已确认中枢 + 同向A/B离开段 + 同级别（level_guard）

背驰只能回答：同级别走势力度是否衰竭。
不能回答：趋势一定结束 / 买点成立 / 大级别反转确认。

用法：
  from divergence import find_divergence, compute_macd
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

# v0.2: 级别权限闸
try:
    from level_guard import (
        check_divergence_permission, GateStatus, GateReason
    )
    LEVEL_GUARD_AVAILABLE = True
except ImportError:
    LEVEL_GUARD_AVAILABLE = False


# ═══════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════

@dataclass
class MACDData:
    """单根K线的MACD指标"""
    ema12: float = 0.0
    ema26: float = 0.0
    dif: float = 0.0
    dea: float = 0.0
    bar: float = 0.0       # MACD柱 = (DIF - DEA) × 2


@dataclass
class SegmentInfo:
    """离开段信息（A或B段）"""
    start_idx: int = 0
    end_idx: int = 0
    direction: str = ""         # "向上" | "向下"
    price_start: float = 0.0
    price_end: float = 0.0
    price_high: float = 0.0     # 该段最高价
    price_low: float = 0.0      # 该段最低价
    macd_area: float = 0.0      # MACD柱面积（绝对值求和）


@dataclass
class DivergenceResult:
    """背驰检测结果"""
    direction: str = "none"     # "top" | "bottom" | "none"
    level: str = ""             # 级别
    status: str = "no_divergence"
    # insufficient_data | no_divergence | pending | candidate | confirmed | failed

    # 比较段
    segment_a: Optional[SegmentInfo] = None
    segment_b: Optional[SegmentInfo] = None

    # 关键指标
    price_a: float = 0.0
    price_b: float = 0.0
    area_a: float = 0.0
    area_b: float = 0.0
    ratio: float = 0.0          # area_b / area_a

    # 布尔判定
    price_break: bool = False   # B段价格创新高/低
    area_shrink: bool = False   # B段面积小于A段

    # 中枢
    zhongshu_idx: int = -1      # 中枢在列表中的索引
    zhongshu_zg: float = 0.0
    zhongshu_zd: float = 0.0

    reason: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.segment_a:
            d["segment_a"] = asdict(self.segment_a)
        if self.segment_b:
            d["segment_b"] = asdict(self.segment_b)
        return d

    def to_text(self) -> str:
        status_labels = {
            "no_divergence": "无背驰",
            "insufficient_data": "数据不足",
            "pending": "待确认（走势未完成）",
            "candidate": "背驰候选",
            "confirmed": "背驰确认",
            "failed": "背驰失败",
        }
        direction_labels = {
            "top": "顶背驰",
            "bottom": "底背驰",
            "none": "无",
        }

        lines = [
            f"方向: {direction_labels.get(self.direction, self.direction)}",
            f"状态: {status_labels.get(self.status, self.status)}",
            f"价格突破: {'是' if self.price_break else '否'}",
            f"面积缩小: {'是' if self.area_shrink else '否'}",
        ]
        if self.segment_a and self.segment_b:
            lines.append(f"A段面积: {self.area_a:.4f}")
            lines.append(f"B段面积: {self.area_b:.4f}")
            lines.append(f"面积比:  {self.ratio:.2%}")
            lines.append(f"A段价格: {self.price_a:.2f}")
            lines.append(f"B段价格: {self.price_b:.2f}")
        if self.zhongshu_zg > 0:
            lines.append(f"中枢: ZG={self.zhongshu_zg:.2f} ZD={self.zhongshu_zd:.2f}")
        lines.append(f"原因: {self.reason}")
        return "\n".join(lines)


# ═══════════════════════════════════════════
# MACD 计算
# ═══════════════════════════════════════════

def compute_macd(closes: list[float],
                 fast: int = 12, slow: int = 26, signal: int = 9
                 ) -> list[MACDData]:
    """计算MACD序列

    Args:
        closes: 收盘价序列
        fast/slow/signal: EMA周期（默认12/26/9）

    Returns:
        MACDData 列表，与输入等长
    """
    if len(closes) < slow:
        return []

    result = []
    ema12 = closes[0]
    ema26 = closes[0]
    dea = 0.0

    alpha12 = 2.0 / (fast + 1)
    alpha26 = 2.0 / (slow + 1)
    alpha9 = 2.0 / (signal + 1)

    for i, c in enumerate(closes):
        if i == 0:
            ema12 = c
            ema26 = c
        else:
            ema12 = c * alpha12 + ema12 * (1 - alpha12)
            ema26 = c * alpha26 + ema26 * (1 - alpha26)

        dif = ema12 - ema26

        if i == 0:
            dea = dif
        else:
            dea = dif * alpha9 + dea * (1 - alpha9)

        bar = (dif - dea) * 2
        result.append(MACDData(
            ema12=round(ema12, 4),
            ema26=round(ema26, 4),
            dif=round(dif, 4),
            dea=round(dea, 4),
            bar=round(bar, 4),
        ))

    return result


# ═══════════════════════════════════════════
# 背驰检测
# ═══════════════════════════════════════════

def find_divergence(
    duans: list[dict],
    zhongshu_list: list[dict],
    closes: list[float],
    highs: list[float],
    lows: list[float],
    level: str = "日线",
    zoushi_type: str = "",
) -> DivergenceResult:
    """检测走势末端的背驰

    Args:
        duans: 线段列表（A0构件），每个含 direction/start_idx/end_idx
        zhongshu_list: 中枢列表，每个含 zg/zd/start_idx/end_idx/start_duan/end_duan
        closes: 收盘价序列（与K线一一对应）
        highs/lows: 最高/最低价序列
        level: 级别
        zoushi_type: 走势类型（上涨/下跌/盘整）

    Returns:
        DivergenceResult
    """
    # ── 级别权限检查 (v0.2) ──
    if LEVEL_GUARD_AVAILABLE:
        guard = check_divergence_permission(level, level)
        if guard.blocked:
            return DivergenceResult(
                status="insufficient_data", level=level,
                reason=f"级别权限阻断: {guard.detail}"
            )
        if guard.status == GateStatus.WARN:
            # WARN 不阻断，但记录
            pass

    # ── 前置检查 ──
    if not zhongshu_list:
        return DivergenceResult(
            status="no_divergence", level=level,
            reason="无中枢，不判背驰"
        )

    if len(closes) < 26:
        return DivergenceResult(
            status="insufficient_data", level=level,
            reason=f"数据不足（需≥26根K线，当前{len(closes)}根）"
        )

    if len(duans) < 3:
        return DivergenceResult(
            status="insufficient_data", level=level,
            reason=f"线段不足（需≥3段，当前{len(duans)}段）"
        )

    # ── 计算MACD ──
    macd_seq = compute_macd(closes)
    if not macd_seq:
        return DivergenceResult(
            status="insufficient_data", level=level,
            reason="MACD计算失败"
        )

    # ── 遍历全部中枢，取最强背驰 ──
    best_result: Optional[DivergenceResult] = None
    scanned = 0
    found_ab = 0

    for zi, zs in enumerate(zhongshu_list):
        trend_direction = _infer_trend(duans, zs, zoushi_type)
        seg_a, seg_b = _find_ab_segments(
            duans, zs, trend_direction, closes, highs, lows, macd_seq
        )

        if seg_a is None or seg_b is None:
            scanned += 1
            continue

        found_ab += 1

        # ── 判断背驰条件 ──
        price_break = False
        area_shrink = False
        direction = "none"

        if trend_direction == "up":
            direction = "top"
            price_break = seg_b.price_high > seg_a.price_high
            area_shrink = abs(seg_b.macd_area) < abs(seg_a.macd_area)
        elif trend_direction == "down":
            direction = "bottom"
            price_break = seg_b.price_low < seg_a.price_low
            area_shrink = abs(seg_b.macd_area) < abs(seg_a.macd_area)

        ratio = abs(seg_b.macd_area) / max(abs(seg_a.macd_area), 1e-10)
        status, reason = _determine_status(
            price_break, area_shrink, seg_a, seg_b, zoushi_type, trend_direction
        )

        candidate = DivergenceResult(
            direction=direction,
            level=level,
            status=status,
            segment_a=seg_a,
            segment_b=seg_b,
            price_a=seg_a.price_high if trend_direction == "up" else seg_a.price_low,
            price_b=seg_b.price_high if trend_direction == "up" else seg_b.price_low,
            area_a=round(seg_a.macd_area, 6),
            area_b=round(seg_b.macd_area, 6),
            ratio=round(ratio, 4),
            price_break=price_break,
            area_shrink=area_shrink,
            zhongshu_idx=zs.get("start_idx", -1),
            zhongshu_zg=zs.get("zg", 0),
            zhongshu_zd=zs.get("zd", 0),
            reason=reason,
        )

        # 保留最强候选：优先 candidate/pending，其次面积比最小
        if best_result is None:
            best_result = candidate
        elif candidate.status in ("candidate", "pending") and \
             best_result.status not in ("candidate", "pending"):
            best_result = candidate
        elif candidate.status in ("candidate", "pending") and \
             best_result.status in ("candidate", "pending"):
            if candidate.ratio < best_result.ratio:
                best_result = candidate
        elif candidate.status == best_result.status and \
             candidate.ratio < best_result.ratio:
            best_result = candidate

    if best_result is not None:
        return best_result

    # 全扫描过，无完整A/B段
    reason = ("无中枢，不判背驰" if not zhongshu_list
              else f"扫描{len(zhongshu_list)}个中枢，{found_ab}个有A/B段但均不满足背驰条件"
              if found_ab > 0
              else f"扫描{len(zhongshu_list)}个中枢，均无完整A/B离开段")

    return DivergenceResult(
        status="no_divergence", level=level,
        reason=reason,
    )


def _infer_trend(duans: list[dict], zs: dict, zoushi_type: str) -> str:
    """推断走势方向

    用中枢之前的离开段方向定趋势——这是最可靠的定义。
    缠论规律：上涨走势→中枢由 down-up-down 构成→离开段是向上。
    """
    if zoushi_type in ("上涨", "up"):
        return "up"
    if zoushi_type in ("下跌", "down"):
        return "down"

    # 看中枢前第一条非同向段的方向 = 趋势方向
    # 中枢第一段的反方向 = 趋势方向（down→up, up→down）
    zs_start = zs.get("start_duan", 0)

    # 方法：取中枢前第一条段的方向，如果不存在则反推
    if zs_start > 0:
        before = duans[zs_start - 1]
        before_dir = _duan_direction(before)
        if before_dir in ("向上", "向下"):
            return "up" if before_dir == "向上" else "down"

    # 回退：中枢第一段的反方向
    if zs_start < len(duans):
        d = duans[zs_start]
        d_dir = _duan_direction(d)
        if d_dir == "向上":
            return "down"
        elif d_dir == "向下":
            return "up"

    return "up"


def _find_ab_segments(
    duans: list[dict],
    zs: dict,
    trend_direction: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    macd_seq: list[MACDData],
) -> tuple:
    """找中枢前后的同向离开段 A 和 B

    A段：中枢前的同向段（离开→进入中枢的前一段）
    B段：中枢后的同向段（离开中枢的后一段）

    对于上涨走势：
      中枢由 down-up-down 三段构成
      A = 中枢前的向上段
      B = 中枢后的向上段

    对于下跌走势：
      中枢由 up-down-up 三段构成
      A = 中枢前的向下段
      B = 中枢后的向下段
    """
    zs_start = zs.get("start_duan", 0)
    zs_end = zs.get("end_duan", 0)

    # 确定同向方向
    same_dir = "向上" if trend_direction == "up" else "向下"

    # A段：中枢前第一个同向段
    seg_a = None
    for i in range(zs_start - 1, -1, -1):
        d = duans[i]
        d_dir = _duan_direction(d)
        if d_dir == same_dir:
            seg_a = _build_segment(d, closes, highs, lows, macd_seq)
            break

    # B段：中枢后第一个同向段
    seg_b = None
    for i in range(zs_end + 1, len(duans)):
        d = duans[i]
        d_dir = _duan_direction(d)
        if d_dir == same_dir:
            seg_b = _build_segment(d, closes, highs, lows, macd_seq)
            break

    return seg_a, seg_b


def _duan_direction(d: dict) -> str:
    """统一方向名称"""
    d_dir = d.get("direction", "")
    if "向上" in d_dir:
        return "向上"
    elif "向下" in d_dir:
        return "向下"
    return d_dir


def _build_segment(
    d: dict,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    macd_seq: list[MACDData],
) -> SegmentInfo:
    """构建离开段信息，含MACD面积"""
    start = max(0, d.get("start_idx", 0))
    end = min(len(closes) - 1, d.get("end_idx", 0))
    d_dir = _duan_direction(d)

    # 价格信息
    seg_highs = highs[start:end + 1] if start <= end <= len(highs) - 1 else [0]
    seg_lows = lows[start:end + 1] if start <= end <= len(lows) - 1 else [0]
    seg_closes = closes[start:end + 1] if start <= end <= len(closes) - 1 else [0]

    # MACD面积 = MACD柱在该段范围内的总和
    macd_bars = [m.bar for m in macd_seq[start:end + 1]] if start <= end < len(macd_seq) else []

    return SegmentInfo(
        start_idx=start,
        end_idx=end,
        direction=d_dir,
        price_start=closes[start] if start < len(closes) else 0,
        price_end=closes[end] if end < len(closes) else 0,
        price_high=max(seg_highs) if seg_highs else 0,
        price_low=min(seg_lows) if seg_lows else 0,
        macd_area=sum(macd_bars) if macd_bars else 0,
    )


def _determine_status(
    price_break: bool,
    area_shrink: bool,
    seg_a: SegmentInfo,
    seg_b: SegmentInfo,
    zoushi_type: str,
    trend_direction: str,
) -> tuple[str, str]:
    """判定背驰状态

    Returns:
        (status, reason)
    """
    # 价格没突破 → 不构成背驰
    if not price_break:
        return (
            "no_divergence",
            f"B段价格未{'创新高' if trend_direction == 'up' else '创新低'}，不构成背驰条件"
        )

    # 面积没缩小 → 不构成背驰
    if not area_shrink:
        return (
            "no_divergence",
            f"B段MACD面积({seg_b.macd_area:.4f})未小于A段({seg_a.macd_area:.4f})，不构成背驰"
        )

    # 走势类型判断
    if zoushi_type in ("盘整", ""):
        # 盘整中背驰候选 → pending（需走势类型确认）
        return (
            "pending",
            f"价格突破+面积缩小，但走势类型为盘整，待走势完成确认"
        )

    # 满足条件 → candidate
    reason_parts = [
        f"B段{'创新高' if trend_direction == 'up' else '创新低'}",
        f"B段MACD面积({seg_b.macd_area:.4f}) < A段({seg_a.macd_area:.4f})",
        f"面积比={abs(seg_b.macd_area) / max(abs(seg_a.macd_area), 1e-10):.2%}",
    ]
    return ("candidate", "；".join(reason_parts))


# ═══════════════════════════════════════════
# 背驰确认/否定（用于后续K线更新）
# ═══════════════════════════════════════════

def confirm_divergence(
    result: DivergenceResult,
    reversal_duan: dict,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> DivergenceResult:
    """candidate 后出现反向线段 → confirmed"""
    if result.status != "candidate":
        return result

    rev_dir = _duan_direction(reversal_duan)
    expected_reversal = "向下" if result.direction == "top" else "向上"

    if rev_dir == expected_reversal:
        result.status = "confirmed"
        result.reason = f"{result.reason}；反向线段确认背驰"
    else:
        result.status = "failed"
        result.reason = f"{result.reason}；反向确认失败（方向不符: {rev_dir}）"

    return result


def fail_divergence(
    result: DivergenceResult,
    reason: str = "",
    new_macd_area_b: float = 0.0,
) -> DivergenceResult:
    """candidate 后MACD面积重新放大或价格继续推进 → failed"""
    if result.status not in ("candidate", "pending"):
        return result

    result.status = "failed"
    if new_macd_area_b > 0 and result.segment_b:
        reason = (f"{reason}；B段MACD面积从{result.area_b:.4f}扩大到"
                  f"{new_macd_area_b:.4f}") if reason else reason
    result.reason = reason or "背驰候选被否定"
    return result


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import csv
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    sys.stdout.reconfigure(encoding="utf-8")

    from draw_chan_ajiao import kxian_baohan, load_data
    from bi_v0_1 import find_fenxing, find_bi
    from duan_v0_1 import find_duan
    from zoushi_type import classify_zoushi

    code = sys.argv[1] if len(sys.argv) > 1 else "600900"
    n_bars = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    print(f"背驰检测: {code}, {n_bars}根K线")
    print("=" * 60)

    # 加载数据
    bars = load_data(code, n_bars)
    if not bars:
        print("数据加载失败")
        sys.exit(1)

    for b in bars:
        b['_orig_date'] = b['date']

    # 底层链
    bars_bh = kxian_baohan(bars)
    fxs = find_fenxing(bars_bh)
    bis = find_bi(bars_bh, fxs, min_bars=5)
    duans = find_duan(bis)
    from draw_chan_ajiao import find_zhongshu_from_duan
    zhongshu_list = find_zhongshu_from_duan(duans)

    print(f"包含处理: {len(bars)}→{len(bars_bh)}")
    print(f"分型: 顶{sum(1 for f in fxs if f['type']=='顶分型')} "
          f"底{sum(1 for f in fxs if f['type']=='底分型')}")
    print(f"笔: {len(bis)}")
    print(f"线段: {len(duans)}")
    print(f"中枢: {len(zhongshu_list)}")

    if not zhongshu_list:
        print("\n⚠ 无中枢，无法检测背驰")
        sys.exit(0)

    # 走势类型
    zt_result = classify_zoushi(zhongshu_list)
    zt = zt_result.get("type", "")
    print(f"走势类型: {zt}")

    # 背驰检测
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]

    result = find_divergence(duans, zhongshu_list, closes, highs, lows,
                             level="日线", zoushi_type=zt)

    print("\n" + "=" * 60)
    print(result.to_text())
