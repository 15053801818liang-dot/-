#!/usr/bin/env python3
"""任务：盘古符号推理 — 优先解读跨域联合报告，降级至缠论 artifact。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.task_base import TaskBase, artifact_dir  # noqa: E402


class PanguReasoner:
    """轻量符号推理：联合报告 / 缠论结构 → 状态码与解释。"""

    def reason_from_union(self, union_data: Dict[str, Any]) -> Dict[str, Any]:
        cross = union_data.get("cross_domain", {})
        chanlun = union_data.get("chanlun", {})
        immune = union_data.get("immune", {})

        align_score = float(cross.get("alignment_score", 0.5))
        status = cross.get("status", "neutral")
        risk = float(cross.get("risk_indicator", 0))

        if status == "aligned":
            state_code = "CROSS_ALIGNED_BULLISH" if align_score >= 0.7 else "CROSS_ALIGNED_NEUTRAL"
            confidence = min(0.95, 0.6 + align_score * 0.35)
        elif status == "misaligned":
            state_code = "CROSS_MISALIGNED_RISK"
            confidence = 0.55
        else:
            state_code = "CROSS_NEUTRAL"
            confidence = 0.65

        interpretation = (
            f"跨域联合分析: 缠论笔数={chanlun.get('bi_count')}, "
            f"免疫AUC={immune.get('auc_loo')}, "
            f"一致性={align_score:.2f}({status}), 风险={risk:.2f}"
        )
        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": round(confidence, 2),
            "cross_domain_align": status == "aligned",
        }

    def reason_from_chanlun(self, chanlun_data: Dict[str, Any]) -> Dict[str, Any]:
        metrics = chanlun_data.get("metrics", {})
        structure = chanlun_data.get("structure", {})

        div_count = metrics.get(
            "divergence_count",
            len(structure.get("divergences", [])),
        )
        bi_count = structure.get("bi_count") or metrics.get("strokes_count", 0)
        total_return = metrics.get("total_return", 0.0)

        if div_count >= 15:
            state_code = "STRUCTURE_CONFLICTED"
            confidence = 0.58
        elif total_return > 0:
            state_code = "TREND_CONTINUATION"
            confidence = 0.72
        else:
            state_code = "RANGE_OR_PULLBACK"
            confidence = 0.65

        interpretation = (
            f"缠论结构推理: 笔数={bi_count}, 背驰事件={div_count}, "
            f"净收益={total_return:.4f}"
        )
        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": confidence,
        }


class PanguInference(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        reasoner = PanguReasoner()
        result: Dict[str, Any]

        union_art = artifacts.get("join_union_report", {})
        union_path = union_art.get("artifact_path") or union_art.get("payload", {}).get("artifact_path")
        if union_path and Path(union_path).exists():
            with open(union_path, encoding="utf-8") as f:
                union_data = json.load(f)
            result = reasoner.reason_from_union(union_data)
        else:
            bt_art = artifacts.get("chanlun_backtest", {})
            chanlun_path = bt_art.get("artifact_path") or bt_art.get("payload", {}).get("artifact_path")
            if not chanlun_path or not Path(chanlun_path).exists():
                raise ValueError("Missing chanlun_backtest artifact and no union report")
            with open(chanlun_path, encoding="utf-8") as f:
                chanlun_data = json.load(f)
            result = reasoner.reason_from_chanlun(chanlun_data)

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "pangu_inference.json"
        artifact_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        payload = {
            "artifact_path": str(artifact_path),
            "pangu_logic_interpretation": result.get("interpretation"),
            "market_state_code": result.get("state_code"),
            "confidence": result.get("confidence"),
        }
        if "cross_domain_align" in result:
            payload["cross_domain_align"] = result["cross_domain_align"]
        return payload


if __name__ == "__main__":
    PanguInference().execute()
