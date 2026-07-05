#!/usr/bin/env python3
"""任务：缠论结构分析 + 信号回测（替代 matrix_core）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chanlun.backtest import run_chanlun_backtest
from chanlun.data_loader import load_csv
from tasks.task_base import TaskBase, artifact_dir


class ChanlunBacktest(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        upstream = artifacts.get("load_market_data", {})
        market_path = upstream.get("artifact_path") or upstream.get("payload", {}).get("artifact_path")
        if not market_path:
            raise ValueError("missing artifact from load_market_data")
        if not Path(market_path).exists():
            raise FileNotFoundError(f"artifact not found: {market_path}")

        config_path = params.get("strategy_config_path", "configs/chanlun_btc.json")
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        bars = load_csv(market_path)
        result = run_chanlun_backtest(bars, config)

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "chanlun_replay.json"
        with artifact_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        m = result.get("metrics", {})
        return {
            "artifact_path": str(artifact_path),
            "summary": {
                "signals_count": m.get("signals_count", 0),
                "strokes_count": m.get("strokes_count", 0),
                "total_trades": m.get("total_trades", 0),
                "win_rate": m.get("win_rate", 0),
                "sharpe": m.get("sharpe", 0),
                "total_return": m.get("total_return", 0),
                "max_drawdown": m.get("max_drawdown", 0),
            },
        }


if __name__ == "__main__":
    ChanlunBacktest().execute()
