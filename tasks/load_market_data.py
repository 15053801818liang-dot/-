#!/usr/bin/env python3
"""任务：加载市场数据 → Parquet/CSV artifact（Go 侧仅传递路径）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chanlun.data_loader import load_market, save_market
from chanlun.data_clean import clean_bars
from tasks.task_base import TaskBase, artifact_dir


class LoadMarketData(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        source = params.get("source_path", "data/BTCUSDT_5m.csv")
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"market data not found: {src}")

        t0 = time.perf_counter()
        bars = load_market(src)
        load_sec = time.perf_counter() - t0
        if not bars:
            raise ValueError("empty market data")

        if params.get("clean", True):
            bars, clean_audit = clean_bars(bars)
            if not bars:
                raise ValueError("all rows dropped after cleaning")
        else:
            clean_audit = None

        out_dir = artifact_dir(workspace_dir, dag_id)
        prefer_parquet = params.get("prefer_parquet", True)
        artifact_path = save_market(bars, out_dir / "market_data.parquet", prefer_parquet=prefer_parquet)

        summary = {
            "bars": len(bars),
            "source": str(src.resolve()),
            "format": Path(artifact_path).suffix.lstrip("."),
            "load_seconds": round(load_sec, 3),
            "first_close": bars[0].close,
            "last_close": bars[-1].close,
        }
        if clean_audit:
            summary["clean_audit"] = clean_audit.to_dict()

        return {
            "artifact_path": artifact_path,
            "summary": summary,
        }


if __name__ == "__main__":
    LoadMarketData().execute()
