"""缠论内核演示脚本。

运行：``python3 -m chanlun.demo``

在两组合成行情上跑完整流水线，打印分型 / 笔 / 中枢 / 买卖点。
"""

from __future__ import annotations

from typing import List

from .analyzer import ChanResult, analyze
from .models import Bar, FractalType
from .sample import sample_bars, sample_bars_pivot


def _print_result(title: str, bars: List[Bar]) -> ChanResult:
    result = analyze(bars)
    print(f"\n=== {title} ===")
    print(
        f"原始K线 {len(result.bars)}  合并K线 {len(result.merged)}  "
        f"分型 {len(result.fractals)}  笔 {len(result.strokes)}  "
        f"中枢 {len(result.pivots)}"
    )

    print("笔:")
    for i, s in enumerate(result.strokes):
        arrow = "↑" if s.direction.value == "up" else "↓"
        print(
            f"  笔{i} {arrow} {s.start_price:.1f} -> {s.end_price:.1f} "
            f"(K线 {s.start.bar_index}->{s.end.bar_index}, 幅度 {s.amplitude:.1f})"
        )

    print("中枢:")
    if result.pivots:
        for p in result.pivots:
            print(
                f"  ZG={p.zg:.1f} ZD={p.zd:.1f} 高度={p.height:.1f} "
                f"含笔 {len(p.strokes)} (笔{p.start_index}..{p.end_index})"
            )
    else:
        print("  （无）")

    print("买卖点:")
    if result.trade_points:
        for t in result.trade_points:
            print(
                f"  [{t.kind.value.upper()}] K线{t.bar_index} @ {t.price:.2f}  —— {t.reason}"
            )
    else:
        print("  （无）")

    return result


def main() -> None:
    print("缠论内核演示 (chanlun v" + __import__("chanlun").__version__ + ")")
    _print_result("场景一：下降通道底背驰 → 第一类买点", sample_bars())
    _print_result("场景二：中枢突破回调 → 第三类买点", sample_bars_pivot())
    print("\n演示完成。")


if __name__ == "__main__":
    main()
