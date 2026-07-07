#!/usr/bin/env python3
"""盘古推理节点 — 符号知识库 + 仲裁"""
import json, os, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pangu.reasoner import PanguReasoner
from pangu.arbiter import Arbiter


def run(params: dict, workspace: str, dag_id: str, artifacts: dict) -> dict:
    chanlun_artifact = artifacts.get("chanlun_backtest", {}).get("artifact_path", "")
    chanlun_data = {}
    if chanlun_artifact and Path(chanlun_artifact).exists():
        with open(chanlun_artifact) as f:
            chanlun_data = json.load(f)

    bt = chanlun_data.get("backtest", {})
    analysis = chanlun_data.get("analysis", {})

    # 从 chanlun 结果提取特征
    alignment_score = (bt.get("win_rate_pct", 0) / 100 * 0.5) + max(0, bt.get("total_return_pct", 0) / 100 * 0.5)
    biome_features = {
        "cd8_mem_ratio": abs(bt.get("total_return_pct", 0)) / 100,
        "auc_delta": bt.get("sharpe_ratio", 0) / 10,
        "rscore": bt.get("total_return_pct", 0),
        "nr_score": -bt.get("total_return_pct", 0) if bt.get("total_return_pct", 0) < 0 else 0,
    }

    # 盘古推演
    reasoner = PanguReasoner()
    reasoner_result = reasoner.infer(alignment_score, biome_features)

    # 仲裁
    arbiter = Arbiter(workspace)
    verdict = arbiter.adjudicate(reasoner_result)

    # 写产物
    artifact_dir = Path(workspace) / "artifacts" / dag_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with open(artifact_dir / "pangu_inference.json", "w") as f:
        json.dump({"reasoner": reasoner_result, "verdict": verdict, "features": biome_features}, f, indent=2)

    return {
        "state_code": verdict["state_code"],
        "confidence": verdict["confidence"],
        "risk": verdict["risk"],
        "action": verdict["action"],
        "elapsed_ms": verdict["elapsed_ms"],
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
        print(json.dumps({"status": "success", "message": "pangu inference complete", "payload": payload}))
    except Exception as e:
        import traceback
        print(json.dumps({"status": "failed", "message": str(e), "payload": {"traceback": traceback.format_exc()}}))
