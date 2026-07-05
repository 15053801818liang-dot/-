"""文件读取工具 — 受控本地输入。"""

from __future__ import annotations

from pathlib import Path


class FileReader:
    def read_text(self, path: str, *, encoding: str = "utf-8") -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        return p.read_text(encoding=encoding)
