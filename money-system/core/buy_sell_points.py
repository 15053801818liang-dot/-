# -*- coding: utf-8 -*-
"""
一二类买卖点模块 v0.3 — 双通道 (confirmed_signal / candidate_watch)
====================================================================
v0.1: 基础买卖点检测
v0.2: 背驰状态前置闸 — no_divergence/insufficient_data/failed → no_signal
v0.3: 双通道 — confirmed→信号池/candidate→观察池, 不混算

依赖：背驰 + 区间套 + level_guard
输入：DivergenceResult + NestedDivergenceResult + 走势/笔/线段
输出：BuySellPointResult (含 signal_channel 字段)

双通道规则:
  confirmed_signal: divergence=confirmed + trend_filter≠FORBID → 进入正式信号池
  candidate_watch: divergence=candidate → 进入观察池(不参与胜率统计)
  no_signal: no_divergence/failed/insufficient_data → 无信号

硬闸:
  1. divergence direction 必须匹配 (bottom→buy, top→sell)
  2. divergence status 必须是 candidate/pending/confirmed
  3. no_divergence / insufficient_data / failed → no_signal
  4. point_type 为空 ≠ 有信号 — no_signal 返回 ""

一买/一卖：基于背驰 + 区间套验证 + 反向结构确认
二买/二卖：基于一买确认后回调不破 + 衰竭确认

不动 divergence.py / nested_divergence.py。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ═══════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════

@dataclass
class BuySellPointResult:
    """买卖点检测结果"""
    point_type: str = ""           # first_buy / first_sell / second_buy / second_sell
    direction: str = ""            # buy / sell
    level: str = ""                # 级别
    status: str = "no_signal"      # no_signal / candidate / confirmed / failed
    signal_channel: str = ""       # v0.3: "confirmed_signal" / "candidate_watch" / ""

    # 来源
    source_divergence: Optional[dict] = None    # DivergenceResult.to_dict()
    nested_status: str = ""                     # 区间套状态
    nested_confirmed: bool = False

    # 确认结构
    confirm_structure: str = ""    # "反向笔" / "底分型转强" / "顶分型转弱"
    confirm_price: float = 0.0
    confirm_date: str = ""

    # 关键价位
    reference_price: float = 0.0   # 一买: 最低点; 一卖: 最高点
    reference_date: str = ""

    # 失效条件
    invalidation: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_text(self) -> str:
        type_labels = {
            "first_buy": "一买",
            "first_sell": "一卖",
            "second_buy": "二买",
            "second_sell": "二卖",
        }
        status_labels = {
            "no_signal": "无信号",
            "candidate": "候选",
            "confirmed": "已确认",
            "failed": "已失效",
        }

        lines = [
            f"类型: {type_labels.get(self.point_type, self.point_type)}",
            f"方向: {self.direction}",
            f"级别: {self.level}",
            f"状态: {status_labels.get(self.status, self.status)}",
        ]
        if self.reference_price > 0:
            lines.append(f"参考价: {self.reference_price:.2f} ({self.reference_date})")
        if self.confirm_price > 0:
            lines.append(f"确认价: {self.confirm_price:.2f} ({self.confirm_date})")
            lines.append(f"确认结构: {self.confirm_structure}")
        if self.nested_status:
            lines.append(f"区间套: {self.nested_status}")
        if self.invalidation:
            lines.append(f"失效条件: {self.invalidation}")
        lines.append(f"原因: {self.reason}")
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 一买 / 一卖
# ═══════════════════════════════════════════

def find_first_buy(
    divergence,
    nested=None,
    duans: list[dict] = None,
    bis: list[dict] = None,
    level: str = "日线",
) -> BuySellPointResult:
    """一买检测

    条件:
      1. 底背驰 candidate
      2. 区间套 confirmed 或 pending（如有）
      3. 区间套 failed → 一买 failed
      4. 之后出现向上笔/底分型转强 → confirmed
    """
    # ── 前置：必须是底背驰 ──
    div_dir = _get_div_direction(divergence)
    div_status = _get_div_status(divergence)

    if div_dir != "bottom":
        return BuySellPointResult(
            point_type="", direction="buy", level=level,
            status="no_signal",
            reason=f"不是底背驰（当前={div_dir}），一买只在下跌末端底背驰出现",
        )

    if div_status not in ("candidate", "pending", "confirmed"):
        return BuySellPointResult(
            point_type="", direction="buy", level=level,
            status="no_signal",
            source_divergence=_div_to_dict(divergence),
            reason=f"底背驰状态={div_status}，非 candidate/pending/confirmed，不触发一买",
        )

    # ── 区间套验证 ──
    nested_status = _get_nested_status(nested)
    nested_confirmed = _get_nested_confirmed(nested)

    if nested_status == "failed":
        return BuySellPointResult(
            point_type="first_buy", direction="buy", level=level,
            status="failed",
            source_divergence=_div_to_dict(divergence),
            nested_status=nested_status,
            reason="区间套失败（次级别继续延伸），一买不成立",
            invalidation="次级别未衰竭，高一级别底背驰可能延后或消失",
        )

    if nested_status == "insufficient":
        # 区间套数据不足 → 一买pending
        return BuySellPointResult(
            point_type="first_buy", direction="buy", level=level,
            status="pending",
            source_divergence=_div_to_dict(divergence),
            nested_status=nested_status,
            reason="区间套数据不足，一买待确认",
        )

    # ── 反向确认：找底背驰之后的第一根向上笔 ──
    ref_price, ref_date = _get_div_ref_price(divergence, "bottom")
    confirm = _find_reversal_bi(divergence, bis, duans, direction="up")

    # v0.3: signal_channel — 基于买卖点自身状态(反向笔确认), 不是背驰状态
    pt_status = "confirmed" if confirm else "candidate"
    channel = "confirmed_signal" if pt_status == "confirmed" else "candidate_watch"

    point = BuySellPointResult(
        point_type="first_buy", direction="buy", level=level,
        status=pt_status,
        signal_channel=channel,
        source_divergence=_div_to_dict(divergence),
        nested_status=nested_status or "not_checked",
        nested_confirmed=nested_confirmed,
        reference_price=ref_price,
        reference_date=ref_date,
        reason=(
            f"底背驰{div_status} + 区间套{nested_status or '未检查'} + "
            f"{'反向笔确认' if confirm else '待反向笔确认'}"
        ),
        invalidation="跌破一买低点则失效",
    )

    if confirm:
        point.confirm_structure = "反向向上笔"
        point.confirm_price = confirm.get("price", 0)
        point.confirm_date = confirm.get("date", "")

    return point


def find_first_sell(
    divergence,
    nested=None,
    duans: list[dict] = None,
    bis: list[dict] = None,
    level: str = "日线",
) -> BuySellPointResult:
    """一卖检测

    条件:
      1. 顶背驰 candidate
      2. 区间套 confirmed 或 pending
      3. 之后出现向下笔/顶分型转弱 → confirmed
    """
    div_dir = _get_div_direction(divergence)
    div_status = _get_div_status(divergence)

    if div_dir != "top":
        return BuySellPointResult(
            point_type="", direction="sell", level=level,
            status="no_signal",
            reason=f"不是顶背驰（当前={div_dir}），一卖只在上涨末端顶背驰出现",
        )

    if div_status not in ("candidate", "pending", "confirmed"):
        return BuySellPointResult(
            point_type="", direction="sell", level=level,
            status="no_signal",
            source_divergence=_div_to_dict(divergence),
            reason=f"顶背驰状态={div_status}，非 candidate/pending，不触发一卖",
        )

    nested_status = _get_nested_status(nested)
    nested_confirmed = _get_nested_confirmed(nested)

    if nested_status == "failed":
        return BuySellPointResult(
            point_type="first_sell", direction="sell", level=level,
            status="failed",
            source_divergence=_div_to_dict(divergence),
            nested_status=nested_status,
            reason="区间套失败（次级别继续延伸），一卖不成立",
            invalidation="次级别未衰竭，高一级别顶背驰可能延后或消失",
        )

    if nested_status == "insufficient":
        return BuySellPointResult(
            point_type="first_sell", direction="sell", level=level,
            status="pending",
            source_divergence=_div_to_dict(divergence),
            nested_status=nested_status,
            reason="区间套数据不足，一卖待确认",
        )

    ref_price, ref_date = _get_div_ref_price(divergence, "top")
    confirm = _find_reversal_bi(divergence, bis, duans, direction="down")

    pt_status = "confirmed" if confirm else "candidate"
    channel = "confirmed_signal" if pt_status == "confirmed" else "candidate_watch"

    point = BuySellPointResult(
        point_type="first_sell", direction="sell", level=level,
        status=pt_status,
        signal_channel=channel,
        source_divergence=_div_to_dict(divergence),
        nested_status=nested_status or "not_checked",
        nested_confirmed=nested_confirmed,
        reference_price=ref_price,
        reference_date=ref_date,
        reason=(
            f"顶背驰{div_status} + 区间套{nested_status or '未检查'} + "
            f"{'反向笔确认' if confirm else '待反向笔确认'}"
        ),
        invalidation="涨破一卖高点则失效",
    )

    if confirm:
        point.confirm_structure = "反向向下笔"
        point.confirm_price = confirm.get("price", 0)
        point.confirm_date = confirm.get("date", "")

    return point


# ═══════════════════════════════════════════
# 二买 / 二卖
# ═══════════════════════════════════════════

def find_second_buy(
    first_buy: BuySellPointResult,
    bis: list[dict] = None,
    duans: list[dict] = None,
    level: str = "日线",
) -> BuySellPointResult:
    """二买检测

    条件:
      1. 一买已 confirmed
      2. 之后出现回调
      3. 回调低点 > 一买低点（不破）
      4. 回调段出现底分型转强 → candidate/confirmed
    """
    if first_buy.point_type != "first_buy":
        return BuySellPointResult(
            point_type="second_buy", direction="buy", level=level,
            status="no_signal",
            reason="一买未确认，二买不触发",
        )

    if first_buy.status != "confirmed":
        return BuySellPointResult(
            point_type="second_buy", direction="buy", level=level,
            status="no_signal",
            reason=f"一买状态={first_buy.status}，非confirmed，二买不触发",
        )

    ref_low = first_buy.reference_price

    # 找一买之后的最低回调段
    if bis and len(bis) > 0:
        pullback = _find_pullback_after_buy(bis, duans, ref_low, first_buy)
        if pullback is None:
            return BuySellPointResult(
                point_type="second_buy", direction="buy", level=level,
                status="candidate",
                reason="一买确认后暂无有效回调，二买待观察",
            )

        if pullback["breached"]:
            return BuySellPointResult(
                point_type="second_buy", direction="buy", level=level,
                status="failed",
                reference_price=ref_low,
                confirm_price=pullback.get("low", 0),
                confirm_date=pullback.get("date", ""),
                reason=f"回调低点({pullback.get('low', 0):.2f})跌破一买低点({ref_low:.2f})，二买失效",
                invalidation="一买低点被跌破",
            )

        # 不破 → candidate 或 confirmed
        confirm = pullback.get("reversal", False)
        return BuySellPointResult(
            point_type="second_buy", direction="buy", level=level,
            status="confirmed" if confirm else "candidate",
            reference_price=ref_low,
            confirm_price=pullback.get("low", 0),
            confirm_date=pullback.get("date", ""),
            confirm_structure="底分型转强" if confirm else "",
            reason=(
                f"回调低点({pullback.get('low', 0):.2f})不破一买低点({ref_low:.2f})"
                + (" + 底分型转强确认" if confirm else "，待底分型转强确认")
            ),
            invalidation="跌破一买低点则失效",
        )

    return BuySellPointResult(
        point_type="second_buy", direction="buy", level=level,
        status="candidate",
        reason="笔数据不足，二买待观察",
    )


def find_second_sell(
    first_sell: BuySellPointResult,
    bis: list[dict] = None,
    duans: list[dict] = None,
    level: str = "日线",
) -> BuySellPointResult:
    """二卖检测

    条件:
      1. 一卖已 confirmed
      2. 之后出现反抽
      3. 反抽高点 < 一卖高点（不破）
      4. 反抽段出现顶分型转弱 → candidate/confirmed
    """
    if first_sell.point_type != "first_sell":
        return BuySellPointResult(
            point_type="second_sell", direction="sell", level=level,
            status="no_signal",
            reason="一卖未确认，二卖不触发",
        )

    if first_sell.status != "confirmed":
        return BuySellPointResult(
            point_type="second_sell", direction="sell", level=level,
            status="no_signal",
            reason=f"一卖状态={first_sell.status}，非confirmed，二卖不触发",
        )

    ref_high = first_sell.reference_price

    if bis and len(bis) > 0:
        bounce = _find_bounce_after_sell(bis, duans, ref_high, first_sell)
        if bounce is None:
            return BuySellPointResult(
                point_type="second_sell", direction="sell", level=level,
                status="candidate",
                reason="一卖确认后暂无有效反抽，二卖待观察",
            )

        if bounce["breached"]:
            return BuySellPointResult(
                point_type="second_sell", direction="sell", level=level,
                status="failed",
                reference_price=ref_high,
                confirm_price=bounce.get("high", 0),
                confirm_date=bounce.get("date", ""),
                reason=f"反抽高点({bounce.get('high', 0):.2f})涨破一卖高点({ref_high:.2f})，二卖失效",
                invalidation="一卖高点被涨破",
            )

        confirm = bounce.get("reversal", False)
        return BuySellPointResult(
            point_type="second_sell", direction="sell", level=level,
            status="confirmed" if confirm else "candidate",
            reference_price=ref_high,
            confirm_price=bounce.get("high", 0),
            confirm_date=bounce.get("date", ""),
            confirm_structure="顶分型转弱" if confirm else "",
            reason=(
                f"反抽高点({bounce.get('high', 0):.2f})不破一卖高点({ref_high:.2f})"
                + (" + 顶分型转弱确认" if confirm else "，待顶分型转弱确认")
            ),
            invalidation="涨破一卖高点则失效",
        )

    return BuySellPointResult(
        point_type="second_sell", direction="sell", level=level,
        status="candidate",
        reason="笔数据不足，二卖待观察",
    )


# ═══════════════════════════════════════════
# 集成入口
# ═══════════════════════════════════════════

def detect_buy_sell_points(
    divergence,
    nested=None,
    bis: list[dict] = None,
    duans: list[dict] = None,
    level: str = "日线",
) -> dict[str, BuySellPointResult]:
    """一键检测一二类买卖点

    v0.2 硬闸: no_divergence/insufficient_data/failed → 直接返回全no_signal
    point_type为空 = 无信号

    Returns:
        {"first_buy": ..., "first_sell": ..., "second_buy": ..., "second_sell": ...}
        无有效信号的点 status="no_signal" 且 point_type=""
    """
    no_signal = lambda: BuySellPointResult(point_type="", status="no_signal", reason="背驰状态不满足")

    # ═══════ v0.2 硬闸: 背驰状态前置检查 ═══════
    div_dir = _get_div_direction(divergence)
    div_status = _get_div_status(divergence)

    if div_status in ("no_divergence", "insufficient_data", "failed"):
        return {
            "first_buy": no_signal(),
            "first_sell": no_signal(),
            "second_buy": BuySellPointResult(point_type="", reason=f"背驰={div_status}"),
            "second_sell": BuySellPointResult(point_type="", reason=f"背驰={div_status}"),
        }

    if div_dir == "none":
        return {
            "first_buy": no_signal(),
            "first_sell": no_signal(),
            "second_buy": BuySellPointResult(point_type="", reason="无背驰方向"),
            "second_sell": BuySellPointResult(point_type="", reason="无背驰方向"),
        }

    first_buy = find_first_buy(divergence, nested, duans, bis, level)
    first_sell = find_first_sell(divergence, nested, duans, bis, level)

    # 二买/二卖基于一买/一卖
    second_buy = find_second_buy(first_buy, bis, duans, level) \
        if first_buy.status == "confirmed" \
        else BuySellPointResult(point_type="", reason="一买未确认")

    second_sell = find_second_sell(first_sell, bis, duans, level) \
        if first_sell.status == "confirmed" \
        else BuySellPointResult(point_type="", reason="一卖未确认")

    return {
        "first_buy": first_buy,
        "first_sell": first_sell,
        "second_buy": second_buy,
        "second_sell": second_sell,
    }


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _get_div_direction(divergence) -> str:
    """兼容 dict / DivergenceResult"""
    if isinstance(divergence, dict):
        return divergence.get("direction", "none")
    return getattr(divergence, "direction", "none")


def _get_div_status(divergence) -> str:
    if isinstance(divergence, dict):
        return divergence.get("status", "")
    return getattr(divergence, "status", "")


def _div_to_dict(divergence) -> Optional[dict]:
    if divergence is None:
        return None
    if isinstance(divergence, dict):
        return divergence
    if hasattr(divergence, "to_dict"):
        return divergence.to_dict()
    return None


def _get_div_ref_price(divergence, direction: str) -> tuple:
    """获取背驰参考价（一买=最低点, 一卖=最高点）"""
    if isinstance(divergence, dict):
        seg_b = divergence.get("segment_b")
        if seg_b:
            if isinstance(seg_b, dict):
                if direction == "top":
                    return seg_b.get("price_high", 0), ""
                else:
                    return seg_b.get("price_low", 0), ""
        return divergence.get("price_b", 0), ""
    else:
        if getattr(divergence, "segment_b", None):
            seg_b = divergence.segment_b
            if direction == "top":
                return seg_b.price_high, ""
            else:
                return seg_b.price_low, ""
        return getattr(divergence, "price_b", 0), ""


def _get_nested_status(nested) -> str:
    if nested is None:
        return ""
    if isinstance(nested, dict):
        return nested.get("lower_status", "")
    return getattr(nested, "lower_status", "")


def _get_nested_confirmed(nested) -> bool:
    if nested is None:
        return False
    if isinstance(nested, dict):
        return nested.get("confirmed", False)
    return getattr(nested, "confirmed", False)


def _find_reversal_bi(
    divergence, bis, duans, direction: str = "up"
) -> Optional[dict]:
    """在背驰之后找反向确认笔"""
    if not bis:
        return None

    # 背驰B段的终点位置
    if isinstance(divergence, dict):
        seg_b = divergence.get("segment_b")
        if seg_b and isinstance(seg_b, dict):
            div_end_idx = seg_b.get("end_idx", -1)
        else:
            div_end_idx = -1
    else:
        seg_b = getattr(divergence, "segment_b", None)
        div_end_idx = seg_b.end_idx if seg_b else -1

    if div_end_idx < 0:
        return None

    # 在B段之后找反向笔
    for bi in bis:
        bi_from_idx = bi.get("from", {}).get("idx", bi.get("from_idx", 0))
        if bi_from_idx <= div_end_idx:
            continue
        bi_dir = _bi_direction(bi)
        if bi_dir == direction:
            bi_from = bi.get("from", {})
            return {
                "price": bi_from.get("low" if direction == "up" else "high", 0),
                "date": bi_from.get("date", ""),
                "idx": bi_from_idx,
            }

    return None


def _bi_direction(bi: dict) -> str:
    """笔的方向 → up/down"""
    d = bi.get("direction", "")
    if "向上" in d:
        return "up"
    if "向下" in d:
        return "down"
    return ""


def _find_pullback_after_buy(
    bis, duans, ref_low: float, first_buy: BuySellPointResult
) -> Optional[dict]:
    """找一买后的回调段"""
    if not bis:
        return None

    # 从一买确认位置之后开始
    confirm_idx = first_buy.confirm_date  # 存的是date不是idx，用价格匹配
    pullback_low = float('inf')
    pullback_date = ""
    breached = False

    for bi in bis:
        bi_dir = _bi_direction(bi)
        bi_from = bi.get("from", {})
        bi_to = bi.get("to", {})
        bi_low = min(bi_from.get("low", float('inf')), bi_to.get("low", float('inf')))
        bi_date = bi_from.get("date", "")

        # 找向下笔 → 回调
        if bi_dir == "down":
            if bi_low < ref_low:
                breached = True
                return {"low": bi_low, "date": bi_date, "breached": True}
            if bi_low < pullback_low:
                pullback_low = bi_low
                pullback_date = bi_date
        elif bi_dir == "up" and pullback_low < float('inf'):
            # 回调后出现向上笔 → 可能转强
            return {
                "low": pullback_low, "date": pullback_date,
                "breached": False,
                "reversal": True,
            }

    if pullback_low < float('inf'):
        return {"low": pullback_low, "date": pullback_date, "breached": False}

    return None


def _find_bounce_after_sell(
    bis, duans, ref_high: float, first_sell: BuySellPointResult
) -> Optional[dict]:
    """找一卖后的反抽段"""
    if not bis:
        return None

    bounce_high = 0
    bounce_date = ""
    breached = False

    for bi in bis:
        bi_dir = _bi_direction(bi)
        bi_from = bi.get("from", {})
        bi_to = bi.get("to", {})
        bi_high = max(bi_from.get("high", 0), bi_to.get("high", 0))
        bi_date = bi_from.get("date", "")

        if bi_dir == "up":
            if bi_high > ref_high:
                breached = True
                return {"high": bi_high, "date": bi_date, "breached": True}
            if bi_high > bounce_high:
                bounce_high = bi_high
                bounce_date = bi_date
        elif bi_dir == "down" and bounce_high > 0:
            return {
                "high": bounce_high, "date": bounce_date,
                "breached": False,
                "reversal": True,
            }

    if bounce_high > 0:
        return {"high": bounce_high, "date": bounce_date, "breached": False}

    return None


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import sys, csv
    sys.path.insert(0, '.')
    sys.stdout.reconfigure(encoding='utf-8')

    from draw_chan_ajiao import kxian_baohan, find_zhongshu_from_duan
    from bi_v0_1 import find_fenxing, find_bi
    from duan_v0_1 import find_duan
    from zoushi_type import classify_zoushi
    from divergence import find_divergence

    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "30min"

    bars = []
    path = f"reports/cache/{sym}_{tf}.csv"
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            bars.append({
                'date': row['date'],
                'open': float(row['open']), 'high': float(row['high']),
                'low': float(row['low']), 'close': float(row['close']),
                'volume': float(row.get('volume', 0)),
            })
    for b in bars:
        b['_orig_date'] = b['date']

    bars_bh = kxian_baohan(bars)
    fxs = find_fenxing(bars_bh)
    bis = find_bi(bars_bh, fxs, min_bars=5)
    duans = find_duan(bis)
    zs = find_zhongshu_from_duan(duans)
    zt = classify_zoushi(zs).get('type', '') if zs else ''
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    div = find_divergence(duans, zs, closes, highs, lows,
                          level=tf, zoushi_type=zt)

    print(f"{sym} {tf}: 笔{len(bis)}/段{len(duans)}/中枢{len(zs)}/{zt}")
    print(f"背驰: {div.direction}/{div.status} ratio={div.ratio:.1%}\n")

    points = detect_buy_sell_points(div, None, bis, duans, level=tf)

    for key, pt in points.items():
        if pt.status != "no_signal" or pt.point_type:
            label = {"first_buy": "一买", "first_sell": "一卖",
                     "second_buy": "二买", "second_sell": "二卖"}.get(key, key)
            print(f"─── {label} ───")
            print(pt.to_text())
            print()
