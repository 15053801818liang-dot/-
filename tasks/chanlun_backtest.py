#!/usr/bin/env python3
"""任务：PR 缠论引擎（czsc 因果笔 + 线段 + 背驰）结构分析与回测。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# internal/chanlun 与顶层 chanlun/ 包同名，仅在本任务内优先加载 PR 引擎
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "internal"))

from chanlun.artifact_loader import load_bars_from_artifact  # noqa: E402
from chanlun.backtest import evaluate_trades, run_backtest  # noqa: E402
from chanlun.chanlun_engine import ChanEngine  # noqa: E402
from chanlun.duan_engine import build_duan_list  # noqa: E402
from tasks.task_base import TaskBase, artifact_dir  # noqa: E402

POLL_CHUNK = {"1m": 500, "5m": 200, "30m": 50}
WARMUP = {"1m": 300, "5m": 300, "30m": 150}


def _point_to_dict(p) -> dict:
    return {
        "kind": p.kind,
        "side": p.side,
        "dt": p.dt.isoformat() if hasattr(p.dt, "isoformat") else str(p.dt),
        "price": p.price,
        "bar_id": p.bar_id,
    }


def _duan_to_dict(duan) -> dict:
    return {
        "direction": duan.direction.value if hasattr(duan.direction, "value") else str(duan.direction),
        "bi_count": len(duan.bis),
        "start_dt": duan.fx_a.dt.isoformat(),
        "end_dt": duan.fx_b.dt.isoformat(),
        "high": duan.high,
        "low": duan.low,
    }


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

        symbol = config.get("symbol", "BTCUSDT")
        freq = config.get("interval", "5m")
        fee = float(config.get("commission", 0.0005)) + float(config.get("slippage", 0.0001))
        verify = params.get("verify_no_lookahead", True)

        bars = load_bars_from_artifact(market_path, symbol=symbol, freq_key=freq)
        warmup = min(WARMUP.get(freq, 300), max(len(bars) // 3, 50))
        if len(bars) < warmup + 10:
            raise ValueError(f"insufficient bars: {len(bars)} (need at least {warmup + 10})")

        safety_margin = int(params.get("safety_margin", 2))
        while True:
            try:
                engine = ChanEngine(bars)
                points, exec_bar_ids, czsc_obj, verify_stats, confirmed_bis = engine.run(
                    warmup=warmup,
                    poll_chunk=min(POLL_CHUNK.get(freq, 200), max(len(bars) // 4, 20)),
                    safety_margin=safety_margin,
                    verify=verify,
                )
                break
            except RuntimeError as exc:
                if not verify:
                    raise
                safety_margin += 2
                if safety_margin > 20:
                    raise RuntimeError(f"safety_margin exhausted: {exc}") from exc

        duans = build_duan_list(confirmed_bis)
        zs_list = engine.build_zhongshu_list(confirmed_bis)
        trades = run_backtest(bars, points, exec_bar_ids, fee_rate=fee / 2)
        bt_stats = evaluate_trades(trades)

        divergences = [p for p in points if p.kind in ("一买", "一卖")]

        result = {
            "metrics": {
                "fractals_count": 0,
                "strokes_count": len(confirmed_bis),
                "pivots_count": len(zs_list),
                "signals_count": len(points),
                "divergence_count": len(divergences),
                "duan_count": len(duans),
                "total_trades": bt_stats.get("交易笔数", 0),
                "win_rate": bt_stats.get("胜率", 0.0),
                "win_rate_gross": bt_stats.get("胜率", 0.0),
                "total_return": bt_stats.get("累计收益率", 0.0),
                "total_return_gross": bt_stats.get("累计收益率", 0.0),
                "max_drawdown": bt_stats.get("最大回撤", 0.0),
                "max_drawdown_gross": bt_stats.get("最大回撤", 0.0),
                "sharpe": 0.0,
                "sharpe_gross": 0.0,
                "friction_drag": 0.0,
                "total_commission": 0.0,
                "total_slippage_cost": 0.0,
                "commission_rate": config.get("commission", 0.0),
                "slippage_rate": config.get("slippage", 0.0),
            },
            "audit": {
                "engine": "pr_chanlun_czsc",
                "version": "migrated-from-claude-code-hardened",
                "stroke_standard": "czsc_rs_czsc",
                "bars": len(bars),
                "verify_stats": verify_stats,
                "safety_margin_used": safety_margin,
            },
            "structure": {
                "bi_count": len(confirmed_bis),
                "duan": [_duan_to_dict(d) for d in duans],
                "divergences": [_point_to_dict(p) for p in divergences],
                "signals": [_point_to_dict(p) for p in points],
            },
        }

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "chanlun_replay.json"
        with artifact_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        m = result["metrics"]
        return {
            "artifact_path": str(artifact_path),
            "summary": {
                "signals_count": m["signals_count"],
                "strokes_count": m["strokes_count"],
                "duan_count": m["duan_count"],
                "divergence_events": m["divergence_count"],
                "total_trades": m["total_trades"],
                "win_rate": m["win_rate"],
                "total_return": m["total_return"],
                "max_drawdown": m["max_drawdown"],
            },
        }


if __name__ == "__main__":
    ChanlunBacktest().execute()
