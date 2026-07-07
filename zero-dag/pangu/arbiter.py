"""盘古裁决层 — Arbiter"""
import json
import os
import time


class Arbiter:
    """Final decision layer. Logs every inference to yushitai audit trail."""

    def __init__(self, workspace: str = None):
        self.workspace = workspace or os.environ.get("WORKSPACE", "workspace")

    def adjudicate(self, reasoner_result: dict) -> dict:
        """Apply risk checks and emit auditable verdict."""
        start = time.time()
        verdict = {
            "state_code": reasoner_result["state_code"],
            "confidence": reasoner_result["confidence"],
            "explanation": reasoner_result["explanation"],
        }

        # Risk gate
        if reasoner_result["confidence"] < 0.6:
            verdict["risk"] = "HIGH"
            verdict["action"] = "HOLD"
        elif reasoner_result["confidence"] >= 0.85:
            verdict["risk"] = "LOW"
            verdict["action"] = reasoner_result["signals"][0]["direction"] if reasoner_result["signals"] else "HOLD"
        else:
            verdict["risk"] = "MEDIUM"
            verdict["action"] = "PAPER_TRADE"

        verdict["elapsed_ms"] = round((time.time() - start) * 1000, 2)

        # 御史台 audit log
        log_path = os.path.join(self.workspace, "logs", "yushitai_audit.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": time.time(),
                "phase": "arbiter_adjudicate",
                "verdict": verdict,
            }, ensure_ascii=False) + "\n")

        return verdict
