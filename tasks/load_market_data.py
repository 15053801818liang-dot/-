#!/usr/bin/env python3
"""任务：加载市场数据 CSV → 标准化 artifact。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chanlun.data_loader import load_csv, save_csv
from tasks.task_base import TaskBase, artifact_dir


class LoadMarketData(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        source = params.get("source_path", "data/BTCUSDT_5m.csv")
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"market data not found: {src}")

        bars = load_csv(src)
        if not bars:
            raise ValueError("empty market data")

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "market_data.csv"
        save_csv(bars, artifact_path)

        return {
            "artifact_path": str(artifact_path),
            "summary": {
                "bars": len(bars),
                "source": str(src.resolve()),
                "first_close": bars[0].close,
                "last_close": bars[-1].close,
            },
        }


if __name__ == "__main__":
    LoadMarketData().execute()
