"""缠论数据结构定义。

纯标准库、零外部依赖。所有结构均为不可变或轻量可变的 dataclass，
便于测试与序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Direction(Enum):
    """走势方向。"""

    UP = "up"
    DOWN = "down"


class FractalType(Enum):
    """分型类型。"""

    TOP = "top"      # 顶分型
    BOTTOM = "bottom"  # 底分型


class StrokeStandard(Enum):
    """成笔口径（阿娇缠论 / 缠师108课体系）。

    NEW — 新笔（宽笔）：A 股默认。分型不共用 K 线 + 极值之间至少 3 根原始 K 线。
    OLD — 老笔（严笔）：包含处理后顶底之间至少 5 根合并 K 线。
    """

    NEW = "new"
    OLD = "old"


class TradePointType(Enum):
    """买卖点类型（缠论一/二/三类）。"""

    BUY1 = "buy1"    # 第一类买点：底背驰
    BUY2 = "buy2"    # 第二类买点：第一类买点后回调不创新低
    BUY3 = "buy3"    # 第三类买点：上涨离开中枢后回调不回中枢
    SELL1 = "sell1"  # 第一类卖点：顶背驰
    SELL2 = "sell2"  # 第二类卖点
    SELL3 = "sell3"  # 第三类卖点


@dataclass
class Bar:
    """原始 K 线。

    index 为在原始序列中的位置，便于回溯定位。
    """

    index: int
    high: float
    low: float
    open: float = 0.0
    close: float = 0.0
    volume: float = 0.0

    def contains(self, other: "Bar") -> bool:
        """self 是否完全包含 other（高低区间）。"""
        return self.high >= other.high and self.low <= other.low

    def contained_by(self, other: "Bar") -> bool:
        return other.contains(self)


@dataclass
class MergedBar:
    """经过包含处理后的合并 K 线。

    origin_indices 记录合并了哪些原始 K 线的下标。
    high_index / low_index 记录极值所在的原始 K 线下标（供分型/MACD 对齐）。
    """

    high: float
    low: float
    origin_indices: List[int] = field(default_factory=list)
    direction: Optional[Direction] = None  # 形成该合并K线时的处理方向
    high_index: int = -1
    low_index: int = -1

    @property
    def index(self) -> int:
        """代表性下标（取合并区间的第一根）。"""
        return self.origin_indices[0] if self.origin_indices else -1


@dataclass
class Fractal:
    """分型：由连续三根合并 K 线构成，中间一根为极值。"""

    kind: FractalType
    merged_index: int      # 在合并K线序列中的位置（中间那根）
    bar_index: int         # 对应原始K线下标
    high: float
    low: float

    @property
    def price(self) -> float:
        """分型的极值价：顶分型取高点，底分型取低点。"""
        return self.high if self.kind is FractalType.TOP else self.low

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "merged_index": self.merged_index,
            "bar_index": self.bar_index,
            "high": self.high,
            "low": self.low,
            "price": self.price,
        }


@dataclass
class Stroke:
    """笔：由相邻的一顶一底分型构成，具有明确方向。"""

    direction: Direction
    start: Fractal
    end: Fractal

    @property
    def start_price(self) -> float:
        return self.start.price

    @property
    def end_price(self) -> float:
        return self.end.price

    @property
    def high(self) -> float:
        return max(self.start.price, self.end.price)

    @property
    def low(self) -> float:
        return min(self.start.price, self.end.price)

    @property
    def amplitude(self) -> float:
        """价格幅度（绝对值）。"""
        return abs(self.end_price - self.start_price)

    @property
    def bar_span(self) -> int:
        """跨越的原始 K 线根数。"""
        return abs(self.end.bar_index - self.start.bar_index)

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.value,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_price": self.start_price,
            "end_price": self.end_price,
            "high": self.high,
            "low": self.low,
            "amplitude": self.amplitude,
            "bar_span": self.bar_span,
        }


@dataclass
class Pivot:
    """中枢：由至少三笔的重叠区间构成。

    zd = 中枢下沿 = 各笔低点的最大值
    zg = 中枢上沿 = 各笔高点的最小值
    """

    zg: float          # 中枢上沿
    zd: float          # 中枢下沿
    start_index: int   # 起始笔在笔序列中的下标
    end_index: int     # 结束笔在笔序列中的下标
    strokes: List[Stroke] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.zg + self.zd) / 2.0

    @property
    def height(self) -> float:
        return self.zg - self.zd

    def to_dict(self) -> dict:
        return {
            "zg": self.zg,
            "zd": self.zd,
            "mid": self.mid,
            "height": self.height,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "stroke_count": len(self.strokes),
        }


@dataclass
class TradePoint:
    """买卖点。"""

    kind: TradePointType
    bar_index: int
    price: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "bar_index": self.bar_index,
            "price": self.price,
            "reason": self.reason,
        }
