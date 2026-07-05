#!/usr/bin/env python3
"""任务：盘古符号推理 — 解读缠论回测 artifact。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "盘古"))

from reasoner import PanguReasoner  # noqa: E402
from tasks.task_base import TaskBase, artifact_dir  # noqa: E402


class PanguInference(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        bt_art = artifacts.get("chanlun_backtest", {})
        cl_path = bt_art.get("artifact_path") or bt_art.get("payload", {}).get("artifact_path")
        if not cl_path or not Path(cl_path).exists():
            raise ValueError("missing artifact from chanlun_backtest")

        replay_art = artifacts.get("run_strategy_replay", {})
        replay_path = replay_art.get("artifact_path") or replay_art.get("payload", {}).get("artifact_path")

        load_art = artifacts.get("load_market_data", {})
        load_summary = load_art.get("summary") or load_art.get("payload", {}).get("summary", {})
        clean_audit = load_summary.get("clean_audit")

        reasoner = PanguReasoner()
        import time

        t_load = time.perf_counter()
        with open(cl_path, encoding="utf-8") as f:
            chanlun_data = json.load(f)
        json_load_sec = time.perf_counter() - t_load

        t_reason = time.perf_counter()
        structure = chanlun_data.get("structure_detail") or {}
        if structure.get("recent_strokes") is not None or structure.get("trade_points"):
            inference = reasoner.reason_from_chanlun(
                structure,
                chanlun_data.get("metrics"),
                chanlun_data.get("audit"),
                clean_audit,
            )
        else:
            inference = reasoner.analyze(replay_path, cl_path, clean_audit=clean_audit)
        reason_sec = time.perf_counter() - t_reason

        perf_audit = {
            "json_load_seconds": round(json_load_sec, 4),
            "reason_from_chanlun_seconds": round(reason_sec, 4),
            "artifact_kb": round(Path(cl_path).stat().st_size / 1024, 2),
        }
        print(
            f"[御史台性能审计] pangu_inference json.load={perf_audit['json_load_seconds']}s "
            f"reason={perf_audit['reason_from_chanlun_seconds']}s "
            f"artifact={perf_audit['artifact_kb']}KB",
            file=sys.stderr,
        )

        inference["perf_audit"] = perf_audit

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "pangu_inference.json"
        artifact_path.write_text(json.dumps(inference, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_path": str(artifact_path),
            "pangu_logic_interpretation": inference["interpretation"],
            "market_state_code": inference["state_code"],
            "confidence": inference["confidence"],
            "semantic_audit": inference.get("semantic_audit", {}),
            "summary": {
                "state_code": inference["state_code"],
                "confidence": inference["confidence"],
                "stroke_index": inference.get("semantic_audit", {}).get("stroke_index"),
                "json_load_seconds": perf_audit["json_load_seconds"],
                "reason_seconds": perf_audit["reason_from_chanlun_seconds"],
            },
        }


if __name__ == "__main__":
    PanguInference().execute()
