"""盘古回测推理桥接 — SuperBrain 兼容符号演绎 + chanlun 结构语义。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from symbolic import SymbolicReasoningPipeline


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


class PanguReasoner:
    """符号演绎智能体：chanlun 结构 → Fact 注入 → 规则演绎。"""

    def __init__(self, kb_path: Optional[str] = None) -> None:
        path = Path(kb_path) if kb_path else None
        self.pipeline = SymbolicReasoningPipeline(path)

    def reason_from_chanlun(
        self,
        structure: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        audit: Optional[Dict[str, Any]] = None,
        clean_audit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metrics = metrics or {}
        audit = audit or {}

        total_strokes = int(structure.get("total_strokes") or 0)
        if not total_strokes:
            return self._pack(
                "结构为空，无法完成符号演绎。",
                "NO_STRUCTURE",
                0.2,
                structure,
                metrics,
                semantic_audit={},
                deduction_path=[],
                matched_rule=None,
            )

        deduction = self.pipeline.deduce(structure)
        logic_kb = deduction.get("logic_kb") or {}
        state_code = deduction["state_code"]
        confidence = float(deduction["confidence"])
        interpretation = deduction["interpretation"]
        deduction_path: List[str] = deduction.get("deduction_path") or []

        if clean_audit and clean_audit.get("gap_warnings", 0) > 10:
            confidence = round(confidence * 0.85, 2)
            deduction_path.append("PENALTY gap_warnings>10 confidence*0.85")

        current_idx = int(structure.get("current_stroke_index", -1))
        pos_label = "未知"
        tags = logic_kb.get("tags") or []
        if "position_above" in tags:
            pos_label = "中枢上方"
        elif "position_below" in tags:
            pos_label = "中枢下方"
        elif "position_inside" in tags:
            pos_label = "中枢内部"

        semantic_audit = self._build_semantic_audit(
            total_strokes=total_strokes,
            current_idx=current_idx,
            last_stroke=logic_kb.get("last_stroke"),
            active_pivot=logic_kb.get("active_pivot"),
            divergence=logic_kb.get("divergence"),
            last_signal=logic_kb.get("last_signal"),
            pos_label=pos_label,
            last_close=structure.get("last_close"),
        )
        semantic_audit["symbolic_facts"] = logic_kb.get("facts", [])
        semantic_audit["matched_rule"] = deduction.get("matched_rule")

        return self._pack(
            interpretation,
            state_code,
            confidence,
            structure,
            metrics,
            semantic_audit=semantic_audit,
            deduction_path=deduction_path,
            matched_rule=deduction.get("matched_rule"),
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
        return self._pack(
            text, state, conf, {}, metrics,
            semantic_audit={},
            deduction_path=["FALLBACK metrics_only"],
            matched_rule=None,
        )

    def _pack(
        self,
        interpretation: str,
        state_code: str,
        confidence: float,
        structure: Dict[str, Any],
        metrics: Dict[str, Any],
        semantic_audit: Dict[str, Any],
        deduction_path: List[str],
        matched_rule: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": confidence,
            "deduction_path": deduction_path,
            "matched_rule": matched_rule,
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
