#!/usr/bin/env python3
"""盘古符号推理节点：基于联合报告或缠论结果生成逻辑解释。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.task_base import TaskBase, artifact_dir


class PanguReasoner:
    """轻量符号推理器（跨域联合报告 → 市场状态编码）。"""

    def reason_from_union(self, union_data: Dict[str, Any]) -> Dict[str, Any]:
        chanlun = union_data.get("chanlun", {})
        immune = union_data.get("immune", {})
        cross = union_data.get("cross_domain", {})

        align_score = cross.get("alignment_score", 0.5)
        risk = cross.get("risk_indicator", 0.0)
        status = cross.get("status", "neutral")

        if status == "aligned" and align_score >= 0.65:
            state_code = "S1_RESPONDER_STABLE"
            interpretation = (
                "缠论结构稳定且免疫特征呈应答者型（记忆T/耗竭T比值偏高），"
                "跨域信号一致，偏向趋势延续或低风险区间。"
            )
            confidence = min(0.95, 0.55 + align_score * 0.4)
        elif status == "misaligned" or risk >= 0.5:
            state_code = "S3_CONFLICT_HIGH_RISK"
            interpretation = (
                "缠论背驰/结构冲突与免疫耗竭倾向并存，跨域不一致，"
                "提示高波动或反转风险升高。"
            )
            confidence = min(0.9, 0.45 + risk * 0.45)
        else:
            state_code = "S2_NEUTRAL_OBSERVE"
            interpretation = (
                "缠论与免疫信号未形成强一致结论，建议观察等待结构确认。"
            )
            confidence = 0.5

        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": round(confidence, 3),
            "cross_domain_align": status == "aligned",
            "immune_auc": immune.get("auc_loo"),
            "chanlun_bi_count": chanlun.get("bi_count"),
        }

    def reason_from_chanlun(self, chanlun_data: Dict[str, Any]) -> Dict[str, Any]:
        metrics = chanlun_data.get("metrics", {})
        structure = chanlun_data.get("structure", {})
        div_count = metrics.get("divergence_count", len(structure.get("divergences", [])))

        if div_count >= 10:
            state_code = "C2_DIVERGENCE_ELEVATED"
            interpretation = "缠论背驰事件偏多，结构进入冲突态，谨慎追势。"
            confidence = 0.62
        else:
            state_code = "C1_STRUCTURE_STABLE"
            interpretation = "缠论结构自洽，背驰事件有限，可继续跟踪笔/线段演化。"
            confidence = 0.68

        return {
            "interpretation": interpretation,
            "state_code": state_code,
            "confidence": confidence,
            "cross_domain_align": False,
        }


def _artifact_path(artifacts: Dict[str, Any], node_id: str) -> str | None:
    entry = artifacts.get(node_id, {})
    return entry.get("artifact_path") or (entry.get("payload") or {}).get("artifact_path")


class PanguInference(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        reasoner = PanguReasoner()

        union_path = _artifact_path(artifacts, "join_union_report")
        if union_path and Path(union_path).exists():
            with open(union_path, encoding="utf-8") as f:
                union_data = json.load(f)
            result = reasoner.reason_from_union(union_data)
        else:
            chanlun_path = _artifact_path(artifacts, "chanlun_backtest")
            if not chanlun_path or not Path(chanlun_path).exists():
                raise ValueError("missing chanlun_backtest artifact and no union report")
            with open(chanlun_path, encoding="utf-8") as f:
                chanlun_data = json.load(f)
            result = reasoner.reason_from_chanlun(chanlun_data)

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "pangu_inference.json"
        artifact_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_path": str(artifact_path),
            "pangu_logic_interpretation": result.get("interpretation"),
            "market_state_code": result.get("state_code"),
            "confidence": result.get("confidence"),
            "cross_domain_align": result.get("cross_domain_align", False),
        }


if __name__ == "__main__":
    PanguInference().execute()
