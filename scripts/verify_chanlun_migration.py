#!/usr/bin/env python3
"""Compare PR repo engines vs myth002 internal/chanlun on the same parquet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PR_DIR = ROOT / "claude-code-hardened" / "chanlun_backtest"
sys.path.insert(0, str(PR_DIR))
sys.path.insert(0, str(ROOT / "internal"))

from chanlun_engine import ChanEngine as PREngine, load_bars as pr_load_bars  # noqa: E402
from duan_engine import build_duan_list as pr_build_duan  # noqa: E402

from chanlun.artifact_loader import load_bars_from_artifact  # noqa: E402
from chanlun.chanlun_engine import ChanEngine as MythEngine  # noqa: E402
from chanlun.duan_engine import build_duan_list as myth_build_duan  # noqa: E402

POLL_CHUNK = {"1m": 500, "5m": 200, "30m": 50}
WARMUP = {"1m": 300, "5m": 300, "30m": 150}


def _run_engine(engine_cls, bars, freq: str):
    safety_margin = 2
    while True:
        try:
            engine = engine_cls(bars)
            points, _, _, stats, confirmed_bis = engine.run(
                warmup=WARMUP[freq],
                poll_chunk=POLL_CHUNK[freq],
                safety_margin=safety_margin,
                verify=True,
            )
            break
        except RuntimeError:
            safety_margin += 2
            if safety_margin > 20:
                raise
    duans = pr_build_duan(confirmed_bis) if engine_cls is PREngine else myth_build_duan(confirmed_bis)
    divergences = [p for p in points if p.kind in ("一买", "一卖")]
    return {
        "bi_count": len(confirmed_bis),
        "duan_count": len(duans),
        "signals_count": len(points),
        "divergence_count": len(divergences),
        "verify_stats": stats,
        "safety_margin": safety_margin,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: verify_chanlun_migration.py <parquet> [symbol] [freq]")
        sys.exit(1)

    parquet = Path(sys.argv[1])
    symbol = sys.argv[2] if len(sys.argv) > 2 else "PEPEUSDT"
    freq = sys.argv[3] if len(sys.argv) > 3 else "5m"

    pr_bars = pr_load_bars(str(parquet), symbol, freq)
    myth_bars = load_bars_from_artifact(parquet, symbol, freq)

    pr_result = _run_engine(PREngine, pr_bars, freq)
    myth_result = _run_engine(MythEngine, myth_bars, freq)

    report = {
        "parquet": str(parquet),
        "bars": len(pr_bars),
        "pr": pr_result,
        "myth002": myth_result,
        "match": {
            k: pr_result[k] == myth_result[k]
            for k in ("bi_count", "duan_count", "signals_count", "divergence_count")
        },
        "all_match": all(
            pr_result[k] == myth_result[k]
            for k in ("bi_count", "duan_count", "signals_count", "divergence_count")
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["all_match"] else 1)


if __name__ == "__main__":
    main()
