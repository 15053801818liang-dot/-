"""记忆读写 — JSON 文件，无数据库。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class MemoryStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.base_dir / name

    def load(self, name: str) -> Dict[str, Any]:
        p = self._path(name)
        if not p.exists():
            return {}
        with p.open(encoding="utf-8") as f:
            return json.load(f)

    def save(self, name: str, data: Dict[str, Any]) -> None:
        p = self._path(name)
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
