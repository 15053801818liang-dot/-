"""缠论（缠中说禅）技术分析内核 —— 纯 Python、零外部依赖。

流水线：K线包含处理 → 分型 → 笔 → 中枢 → MACD 背驰 → 一/二/三类买卖点。

快速上手::

    from chanlun import analyze, bars_from_hl

    bars = bars_from_hl([(10, 9), (11, 10), ...])
    result = analyze(bars)
    for tp in result.trade_points:
        print(tp.kind, tp.bar_index, tp.price, tp.reason)
"""

from .analyzer import (
    ChanAnalyzer,
    ChanResult,
    analyze,
    bars_from_hl,
    bars_from_ohlc,
)
from .fractal import find_fractals
from .kline import process_inclusion
from .macd import MACDResult, area, ema, macd
from .models import (
    Bar,
    Direction,
    Fractal,
    FractalType,
    MergedBar,
    Pivot,
    Stroke,
    StrokeStandard,
    TradePoint,
    TradePointType,
)
from .backtest import run_chanlun_backtest
from .data_loader import load_csv, save_csv
from .pivot import find_pivots
from .sample import sample_bars, sample_bars_pivot, synth_bars
from .signals import find_divergences, generate_trade_points
from .stroke import build_strokes

__version__ = "0.1.0"

__all__ = [
    "ChanAnalyzer",
    "ChanResult",
    "analyze",
    "bars_from_hl",
    "bars_from_ohlc",
    "process_inclusion",
    "find_fractals",
    "build_strokes",
    "find_pivots",
    "find_divergences",
    "generate_trade_points",
    "sample_bars",
    "sample_bars_pivot",
    "synth_bars",
    "macd",
    "ema",
    "area",
    "MACDResult",
    "Bar",
    "MergedBar",
    "Fractal",
    "Stroke",
    "Pivot",
    "TradePoint",
    "Direction",
    "FractalType",
    "StrokeStandard",
    "valid_stroke_pair",
    "run_chanlun_backtest",
    "load_csv",
    "save_csv",
    "__version__",
]
