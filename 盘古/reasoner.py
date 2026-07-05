"""盘古回测推理桥接 — 读取缠论 artifact 并输出符号化市场解读。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _classify_state(metrics: Dict[str, Any]) -> tuple[str, float]:
    """依据回测指标推断市场状态码与置信度。"""
    total_return = float(metrics.get("total_return", 0) or 0)
    sharpe = float(metrics.get("sharpe", 0) or 0)
    max_dd = abs(float(metrics.get("max_drawdown", 0) or 0))
    win_rate = float(metrics.get("win_rate", 0) or 0)
    trades = int(metrics.get("total_trades", 0) or 0)
    friction = float(metrics.get("friction_drag", 0) or 0)

    if trades < 5:
        return "INSUFFICIENT_DATA", 0.35

    if max_dd > 0.25:
        state = "HIGH_VOL"
    elif total_return < -0.05:
        state = "TREND_BEAR"
    elif total_return > 0.15 and sharpe > 1.0:
        state = "TREND_BULL"
    elif friction > 0.3 * max(abs(float(metrics.get("total_return_gross", 0) or 0)), 0.01):
        state = "FRICTION_HEAVY"
    elif 0.45 <= win_rate <= 0.65 and abs(total_return) < 0.1:
        state = "OSC_NEUTRAL"
    elif sharpe > 0.5 and total_return > 0:
        state = "OSC_NEUTRAL"
    else:
        state = "UNCERTAIN"

    sample_conf = min(1.0, trades / 50.0)
    metric_conf = min(1.0, max(0.0, (sharpe + 1.0) / 3.0))
    confidence = round(0.4 * sample_conf + 0.6 * metric_conf, 2)
    return state, confidence


def _interpret(state: str, metrics: Dict[str, Any], audit: Dict[str, Any]) -> str:
    ret = float(metrics.get("total_return", 0) or 0)
    gross = float(metrics.get("total_return_gross", 0) or 0)
    sharpe = float(metrics.get("sharpe", 0) or 0)
    dd = float(metrics.get("max_drawdown", 0) or 0)
    trades = int(metrics.get("total_trades", 0) or 0)
    strokes = int(metrics.get("strokes_count", 0) or 0)
    mode = audit.get("analyze_mode", "full")

    templates = {
        "TREND_BULL": (
            f"缠论结构在 {strokes} 笔尺度上呈现趋势延续特征；"
            f"净收益 {ret:.2%}、夏普 {sharpe:.2f}，策略在样本内具备正向 edge。"
            f"分析模式 {mode}，建议关注摩擦成本对实盘净值的侵蚀。"
        ),
        "TREND_BEAR": (
            f"样本内净收益 {ret:.2%} 为负，最大回撤 {dd:.2%}；"
            f"缠论买卖信号与当前行情相位可能错配，需收紧开仓或切换中枢过滤。"
        ),
        "OSC_NEUTRAL": (
            f"本策略在震荡市中表现相对稳健：胜率 {metrics.get('win_rate', 0):.1%}，"
            f"夏普 {sharpe:.2f}；趋势跟踪信号与盘整结构并存，宜降低仓位或缩短持仓周期。"
        ),
        "HIGH_VOL": (
            f"最大回撤 {dd:.2%} 偏高，波动风险主导；"
            f"缠论笔/中枢重构在剧烈波动下易触发 repaint 类风险，审计应优先验证极值对齐。"
        ),
        "FRICTION_HEAVY": (
            f"毛收益 {gross:.2%} 经摩擦后回落至净收益 {ret:.2%}；"
            f"高频信号 ({trades} 笔成交) 下手续费与滑点显著，实盘需提高信号阈值。"
        ),
        "INSUFFICIENT_DATA": "成交样本过少，符号推理置信度受限；建议扩大回测窗口或降低信号频率后再审计。",
        "UNCERTAIN": (
            f"指标未形成一致趋势画像（净收益 {ret:.2%}，夏普 {sharpe:.2f}）；"
            f"建议结合更高周期中枢与数据清洗审计后再做决策。"
        ),
    }
    return templates.get(state, templates["UNCERTAIN"])


class PanguReasoner:
    """读取回测 artifact，输出盘古逻辑解读。"""

    def analyze(
        self,
        replay_path: Optional[str],
        cl_path: Optional[str],
        clean_audit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        replay = _load_json(replay_path)
        chanlun = _load_json(cl_path)

        metrics = chanlun.get("metrics") or replay.get("metrics") or {}
        audit = chanlun.get("audit") or replay.get("audit") or {}

        if clean_audit:
            dropped = clean_audit.get("dropped_invalid", 0) + clean_audit.get("dropped_duplicate", 0)
            if dropped:
                audit = {**audit, "clean_dropped": dropped}

        state_code, confidence = _classify_state(metrics)
        if clean_audit and clean_audit.get("gap_warnings", 0) > 10:
            confidence = round(confidence * 0.85, 2)

        interpretation = _interpret(state_code, metrics, audit)

        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": confidence,
            "metrics_snapshot": {
                "total_return": metrics.get("total_return"),
                "sharpe": metrics.get("sharpe"),
                "max_drawdown": metrics.get("max_drawdown"),
                "total_trades": metrics.get("total_trades"),
            },
        }
