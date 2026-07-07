#!/usr/bin/env python3
"""缠论回测节点 — 接 czsc 真引擎"""
import sys, json, os
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from internal.chanlun.duan_engine import DuanEngine
from internal.chanlun.chanlun_engine import ChanlunEngine
from internal.chanlun.backtest import run_backtest
from internal.chanlun.artifact_loader import load_market_data, to_raw_bars


def run(params: dict, workspace_dir: str, dag_id: str, artifacts: dict) -> dict:
    market_artifact = artifacts.get("load_market_data", {}).get("artifact_path")
    if market_artifact and Path(market_artifact).exists():
        df = load_market_data(market_artifact)
    else:
        # 生成模拟 K 线用于测试
        import numpy as np
        np.random.seed(42)
        n = 500
        dates = pd.date_range("2024-01-01", periods=n, freq="5min")
        price = 50000 + np.cumsum(np.random.randn(n) * 100)
        df = pd.DataFrame({
            "dt": dates, "open": price, "high": price + np.abs(np.random.randn(n) * 80),
            "low": price - np.abs(np.random.randn(n) * 80), "close": price + np.random.randn(n) * 40,
            "vol": np.random.randint(1, 100, n), "amount": np.random.randint(1, 100, n) * 50000,
        })

    freq = params.get("interval", "5min")
    bars = to_raw_bars(df, freq)

    # 线段分解
    duan = DuanEngine()
    duan_result = duan.decompose(bars)

    # 缠论信号
    chanlun = ChanlunEngine()
    result = chanlun.run(bars, duan_result)

    # 回测
    bt = run_backtest(bars, result)

    # 写产物
    artifact_dir = Path(workspace_dir) / "artifacts" / dag_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "chanlun_result.json"
    with open(artifact_path, "w") as f:
        json.dump({"duan": duan_result, "analysis": result, "backtest": bt}, f, indent=2, default=str)

    return {
        "artifact_path": str(artifact_path),
        "bi_count": duan_result.get("bi_count", 0),
        "zs_count": duan_result.get("zs_count", 0),
        "divergence_signals": len(result.get("signals", [])),
        "buy_points": len(result.get("buy_points", [])),
        "sell_points": len(result.get("sell_points", [])),
        "total_return_pct": bt.get("total_return_pct", 0),
        "sharpe_ratio": bt.get("sharpe_ratio", 0),
        "win_rate_pct": bt.get("win_rate_pct", 0),
        "num_trades": bt.get("num_trades", 0),
    }


if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw:
        print(json.dumps({"status": "failed", "message": "no input"}))
        sys.exit(1)
    try:
        data = json.loads(raw)
        payload = run(
            data.get("params", {}),
            data.get("workspace_dir", "workspace"),
            data.get("dag_id", "test"),
            data.get("artifacts", {}),
        )
        print(json.dumps({"status": "success", "message": "chanlun analysis completed", "payload": payload}))
    except Exception as e:
        import traceback
        print(json.dumps({"status": "failed", "message": str(e), "payload": {"traceback": traceback.format_exc()}}))
