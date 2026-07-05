#!/usr/bin/env python3
"""100k 结构语义压测 — artifact 体积 + JSON 序列化 + PanguReasoner 性能。"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "盘古"))

from chanlun.backtest import run_chanlun_backtest
from chanlun.data_loader import load_market
from reasoner import PanguReasoner


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def file_kb(path: Path) -> float:
    return path.stat().st_size / 1024.0 if path.exists() else 0.0


def run_case(name: str, csv_path: str, out_path: Path, config: dict) -> dict:
    bars = load_market(csv_path)
    t0 = time.perf_counter()
    tracemalloc.start()
    result = run_chanlun_backtest(bars, config)
    backtest_sec = time.perf_counter() - t0
    peak_mem = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    t0 = time.perf_counter()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    write_sec = time.perf_counter() - t0

    t0 = time.perf_counter()
    with out_path.open(encoding="utf-8") as f:
        loaded = json.load(f)
    load_sec = time.perf_counter() - t0

    t0 = time.perf_counter()
    inference = PanguReasoner().reason_from_chanlun(
        loaded.get("structure_detail") or {},
        loaded.get("metrics"),
        loaded.get("audit"),
    )
    reason_sec = time.perf_counter() - t0

    sd = loaded.get("structure_detail") or {}
    return {
        "name": name,
        "bars": len(bars),
        "backtest_sec": round(backtest_sec, 3),
        "json_write_sec": round(write_sec, 3),
        "json_load_sec": round(load_sec, 3),
        "reason_sec": round(reason_sec, 3),
        "artifact_kb": round(file_kb(out_path), 2),
        "rss_mb": round(rss_mb(), 1),
        "peak_traced_mb": round(peak_mem / 1e6, 2),
        "strokes": sd.get("total_strokes", 0),
        "pivots": sd.get("total_pivots", 0),
        "trade_points": len(sd.get("trade_points") or []),
        "recent_strokes": len(sd.get("recent_strokes") or []),
        "state_code": inference.get("state_code"),
    }


def main() -> None:
    config = json.loads((ROOT / "configs/chanlun_btc.json").read_text())
    out_dir = ROOT / "workspace" / "artifacts" / "stress_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)

    demo = run_case(
        "demo_108",
        str(ROOT / "data/BTCUSDT_5m.csv"),
        out_dir / "demo_replay.json",
        {**config, "incremental": False},
    )
    large = run_case(
        "large_100k",
        str(ROOT / "data/BTCUSDT_5m_large.csv"),
        out_dir / "large_100k_replay.json",
        config,
    )

    inflation = large["artifact_kb"] / max(demo["artifact_kb"], 0.01)
    bar_ratio = large["bars"] / max(demo["bars"], 1)

    summary = {
        "demo": demo,
        "large_100k": large,
        "inflation": {
            "bar_ratio": round(bar_ratio, 1),
            "artifact_size_ratio": round(inflation, 2),
            "artifact_kb_per_1k_bars_demo": round(demo["artifact_kb"] / demo["bars"] * 1000, 3),
            "artifact_kb_per_1k_bars_100k": round(large["artifact_kb"] / large["bars"] * 1000, 3),
        },
    }

    report_path = ROOT / "workspace" / "reports" / "stress_100k_benchmark.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== 100k 结构语义压测报告 ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n报告已写入: {report_path}")


if __name__ == "__main__":
    main()
