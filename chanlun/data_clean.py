"""市场数据清洗 — 真实 CSV 异常检测与审计报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .models import Bar


@dataclass
class CleanAudit:
    """御史台数据清洗审计。"""

    input_rows: int = 0
    output_rows: int = 0
    dropped_invalid: int = 0
    dropped_duplicate: int = 0
    fixed_ohlc: int = 0
    gap_warnings: int = 0
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "dropped_invalid": self.dropped_invalid,
            "dropped_duplicate": self.dropped_duplicate,
            "fixed_ohlc": self.fixed_ohlc,
            "gap_warnings": self.gap_warnings,
            "issues": self.issues[:20],
        }


def _valid_prices(o: float, h: float, l: float, c: float) -> bool:
    if any(x <= 0 or x != x for x in (o, h, l, c)):  # NaN check via x!=x
        return False
    if h < l:
        return False
    return True


def _normalize_ohlc(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float, bool]:
    fixed = False
    hi = max(o, h, l, c)
    lo = min(o, h, l, c)
    if hi != h or lo != l:
        fixed = True
        h, l = hi, lo
    return o, h, l, c, fixed


def clean_bars(bars: List[Bar], dedupe: bool = True) -> Tuple[List[Bar], CleanAudit]:
    """清洗 K 线序列，返回 (干净 bars, 审计报告)。"""
    audit = CleanAudit(input_rows=len(bars))
    out: List[Bar] = []
    seen_ts: set = set()
    prev_close: float | None = None

    for b in bars:
        o, h, l, c = b.open, b.high, b.low, b.close
        if not _valid_prices(o, h, l, c):
            audit.dropped_invalid += 1
            continue
        o, h, l, c, fixed = _normalize_ohlc(o, h, l, c)
        if fixed:
            audit.fixed_ohlc += 1

        key = (round(c, 8), round(h, 8), round(l, 8))
        if dedupe and key in seen_ts:
            audit.dropped_duplicate += 1
            continue
        seen_ts.add(key)

        if prev_close is not None and prev_close > 0:
            jump = abs(c - prev_close) / prev_close
            if jump > 0.15:
                audit.gap_warnings += 1
                if len(audit.issues) < 20:
                    audit.issues.append(f"bar#{b.index} price_jump={jump:.2%}")

        out.append(
            Bar(
                index=len(out),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=b.volume,
            )
        )
        prev_close = c

    audit.output_rows = len(out)
    if audit.dropped_invalid:
        audit.issues.insert(0, f"dropped_invalid={audit.dropped_invalid}")
    return out, audit
