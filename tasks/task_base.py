#!/usr/bin/env python3
"""任务基类 — 与 Go JSONExecutor 的标准 stdin/stdout 协议。"""

from __future__ import annotations

import json
import sys
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class TaskBase(ABC):
    """Python 任务单元基类。"""

    @abstractmethod
    def run(
        self,
        params: Dict[str, Any],
        workspace_dir: str,
        dag_id: str,
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行任务并返回 payload（不含 status）。"""

    def execute(self) -> None:
        raw = sys.stdin.read()
        if not raw.strip():
            self._emit("failed", "no input", {})
            sys.exit(1)
        try:
            data = json.loads(raw)
            payload = self.run(
                params=data.get("params", {}),
                workspace_dir=data.get("workspace_dir", "workspace"),
                dag_id=data.get("dag_id", "unknown"),
                artifacts=data.get("artifacts", {}),
            )
            self._emit("success", "ok", payload)
        except Exception as exc:
            self._emit("failed", str(exc), {"traceback": traceback.format_exc()})
            sys.exit(1)

    @staticmethod
    def _emit(status: str, message: str, payload: Dict[str, Any]) -> None:
        print(json.dumps({"status": status, "message": message, "payload": payload}, ensure_ascii=False))


def artifact_dir(workspace_dir: str, dag_id: str) -> Path:
    p = Path(workspace_dir) / "artifacts" / dag_id
    p.mkdir(parents=True, exist_ok=True)
    return p
