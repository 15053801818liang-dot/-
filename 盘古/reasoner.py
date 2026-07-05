"""盘古回测推理桥接 — 消化 chanlun/ 结构语义（笔/中枢/背驰/买卖点）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _pivot_position(price: float, pivot: Dict[str, Any]) -> str:
    zg, zd = float(pivot["zg"]), float(pivot["zd"])
    if price > zg:
        return "above"
    if price < zd:
        return "below"
    return "inside"


class PanguReasoner:
    """读取缠论 artifact 结构骨架，输出符号化市场解读。"""

    def reason_from_chanlun(
        self,
        structure: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        audit: Optional[Dict[str, Any]] = None,
        clean_audit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metrics = metrics or {}
        audit = audit or {}

        strokes: List[Dict[str, Any]] = structure.get("recent_strokes") or []
        pivots: List[Dict[str, Any]] = structure.get("active_pivots") or []
        divergence = structure.get("last_divergence")
        trade_points: List[Dict[str, Any]] = structure.get("trade_points") or []
        last_stroke = structure.get("last_stroke") or (strokes[-1] if strokes else None)
        last_close = structure.get("last_close")
        total_strokes = int(structure.get("total_strokes") or 0)
        current_idx = int(structure.get("current_stroke_index", -1))

        active_pivot = pivots[-1] if pivots else None
        last_signal = trade_points[-1] if trade_points else None

        state_code = "STRUCT_UNCERTAIN"
        confidence = 0.5

        if not total_strokes:
            return self._pack(
                "结构为空，无法完成缠论语义推理。",
                "NO_STRUCTURE",
                0.2,
                structure,
                metrics,
                semantic_audit={},
            )

        pos_label = "未知"
        if active_pivot and last_close is not None:
            pos = _pivot_position(float(last_close), active_pivot)
            pos_label = {"above": "中枢上方", "below": "中枢下方", "inside": "中枢内部"}[pos]

        # 结构驱动状态码
        if last_signal:
            kind = last_signal.get("kind", "")
            reason = last_signal.get("reason", "")
            if kind == "sell3" and divergence and divergence.get("kind") == "top":
                state_code = "HIGH_RISK_EXIT"
                confidence = 0.88
            elif kind == "sell3":
                state_code = "TREND_BEAR_LEAVE_PIVOT"
                confidence = 0.82
            elif kind == "buy1" and divergence and divergence.get("kind") == "bottom":
                state_code = "BUY_DIVERGENCE_CONFIRM"
                confidence = 0.85
            elif kind == "buy3":
                state_code = "TREND_BULL_LEAVE_PIVOT"
                confidence = 0.8
            elif kind in ("sell1", "sell2"):
                state_code = "TOP_DIVERGENCE_ZONE"
                confidence = 0.78
            elif kind in ("buy1", "buy2"):
                state_code = "BOTTOM_DIVERGENCE_ZONE"
                confidence = 0.78
            elif "背驰" in reason:
                state_code = "DIVERGENCE_ACTIVE"
                confidence = 0.75

        if active_pivot and last_close is not None and state_code == "STRUCT_UNCERTAIN":
            pos = _pivot_position(float(last_close), active_pivot)
            if pos == "inside":
                state_code = "OSC_NEUTRAL"
                confidence = 0.7
            elif pos == "above":
                state_code = "TREND_BULL"
                confidence = 0.72
            else:
                state_code = "TREND_BEAR"
                confidence = 0.72

        if clean_audit and clean_audit.get("gap_warnings", 0) > 10:
            confidence = round(confidence * 0.85, 2)

        semantic_audit = self._build_semantic_audit(
            total_strokes=total_strokes,
            current_idx=current_idx,
            last_stroke=last_stroke,
            active_pivot=active_pivot,
            divergence=divergence,
            last_signal=last_signal,
            pos_label=pos_label,
            last_close=last_close,
        )
        interpretation = self._interpret_structure(semantic_audit, audit)

        return self._pack(
            interpretation,
            state_code,
            confidence,
            structure,
            metrics,
            semantic_audit=semantic_audit,
        )

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
        structure = chanlun.get("structure_detail") or {}

        if structure.get("recent_strokes") is not None or structure.get("trade_points"):
            return self.reason_from_chanlun(structure, metrics, audit, clean_audit)

        return self._metrics_fallback(metrics, audit, clean_audit)

    def _build_semantic_audit(
        self,
        *,
        total_strokes: int,
        current_idx: int,
        last_stroke: Optional[Dict[str, Any]],
        active_pivot: Optional[Dict[str, Any]],
        divergence: Optional[Dict[str, Any]],
        last_signal: Optional[Dict[str, Any]],
        pos_label: str,
        last_close: Optional[float],
    ) -> Dict[str, Any]:
        audit: Dict[str, Any] = {
            "stroke_index": current_idx,
            "total_strokes": total_strokes,
            "pivot_position": pos_label,
        }
        if last_stroke:
            audit["last_stroke"] = {
                "index": last_stroke.get("index", current_idx),
                "direction": last_stroke.get("direction"),
                "end_price": last_stroke.get("end_price"),
            }
        if active_pivot:
            audit["active_pivot"] = {
                "zg": active_pivot.get("zg"),
                "zd": active_pivot.get("zd"),
                "mid": active_pivot.get("mid"),
            }
        if divergence:
            audit["divergence"] = divergence
        if last_signal:
            audit["last_signal"] = {
                "kind": last_signal.get("kind"),
                "reason": last_signal.get("reason"),
                "bar_index": last_signal.get("bar_index"),
                "price": last_signal.get("price"),
            }
        if last_close is not None:
            audit["last_close"] = last_close
        return audit

    def _interpret_structure(
        self,
        semantic: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> str:
        stroke_no = semantic.get("stroke_index", -1) + 1
        total = semantic.get("total_strokes", 0)
        pos = semantic.get("pivot_position", "未知")
        pivot = semantic.get("active_pivot")
        div = semantic.get("divergence")
        sig = semantic.get("last_signal")
        mode = audit.get("analyze_mode", "full")

        parts: List[str] = [
            f"当前处于第 {stroke_no}/{total} 笔（{mode} 分析），"
        ]

        if pivot:
            parts.append(
                f"活跃中枢 ZG={pivot['zg']:.2f}, ZD={pivot['zd']:.2f}，"
                f"末收盘相对中枢位于{pos}。"
            )
        else:
            parts.append("尚未形成有效中枢重叠区间。")

        if div:
            parts.append(
                f"最近背驰：{div.get('reason')}（bar#{div.get('bar_index')}，"
                f"价 {div.get('price')}）。"
            )

        if sig:
            parts.append(
                f"末次信号 `{sig.get('kind')}`：{sig.get('reason')}，"
                f"建议确认点为 bar#{sig.get('bar_index')}。"
            )
        elif div and div.get("kind") == "bottom":
            parts.append("底背驰已出现但尚无对应 buy 信号落点，宜等待笔确认。")

        return "".join(parts)

    def _metrics_fallback(
        self,
        metrics: Dict[str, Any],
        audit: Dict[str, Any],
        clean_audit: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        trades = int(metrics.get("total_trades", 0) or 0)
        if trades < 5:
            state, conf = "INSUFFICIENT_DATA", 0.35
        else:
            state, conf = "METRICS_ONLY", 0.45
        text = (
            "artifact 缺少 structure_detail，已降级为指标推理；"
            "请升级 chanlun_backtest 导出完整结构语义。"
        )
        if clean_audit and clean_audit.get("gap_warnings", 0) > 10:
            conf = round(conf * 0.85, 2)
        return self._pack(text, state, conf, {}, metrics, semantic_audit={})

    def _pack(
        self,
        interpretation: str,
        state_code: str,
        confidence: float,
        structure: Dict[str, Any],
        metrics: Dict[str, Any],
        semantic_audit: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": confidence,
            "semantic_audit": semantic_audit,
            "structure_snapshot": {
                "total_strokes": structure.get("total_strokes"),
                "total_pivots": structure.get("total_pivots"),
                "divergences_count": structure.get("divergences_count"),
                "signals_count": len(structure.get("trade_points") or []),
            },
            "metrics_snapshot": {
                "total_return": metrics.get("total_return"),
                "sharpe": metrics.get("sharpe"),
                "max_drawdown": metrics.get("max_drawdown"),
                "total_trades": metrics.get("total_trades"),
            },
        }
