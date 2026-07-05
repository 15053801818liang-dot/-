"""输入标准化 — 用户原话 → InputPacket。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional


_WS_RE = re.compile(r"\s+")
_SEARCH_PREFIX_RE = re.compile(r"^搜索\s*[:：]\s*(.+)$", re.IGNORECASE)
_QUESTION_ONLY_RE = re.compile(r"^[？?…\.。!！,，;；\s]+$")
_CONTINUE_RE = re.compile(r"^(继续|接着|往下|go\s*on|continue)\s*[。.!！?？]?$", re.IGNORECASE)
_MEMORY_RE = re.compile(r"(记住|记下|保存|忘掉|忘记|删除记忆)", re.IGNORECASE)
_CODE_RE = re.compile(r"(改代码|写代码|修代码|帮我改|帮我写|fix\s*code|write\s*code)", re.IGNORECASE)
_AUDIT_RE = re.compile(r"(审一下|审查|审计|检查一下|review|audit)", re.IGNORECASE)
_CONTENT_RE = re.compile(r"(看内容|显示内容|展示内容|show\s*content)", re.IGNORECASE)


@dataclass(frozen=True)
class InputPacket:
    """标准化后的用户输入。"""

    raw_text: str
    normalized_text: str
    stripped_text: str
    char_count: int
    is_empty: bool
    is_question_only: bool
    is_continue: bool
    is_search_prefixed: bool
    search_query: Optional[str]
    hints: List[str] = field(default_factory=list)

    def has_hint(self, name: str) -> bool:
        return name in self.hints


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = _WS_RE.sub(" ", text).strip()
    return text


def _collect_hints(text: str) -> List[str]:
    hints: List[str] = []
    if _MEMORY_RE.search(text):
        hints.append("memory")
    if _CODE_RE.search(text):
        hints.append("code")
    if _AUDIT_RE.search(text):
        hints.append("audit")
    if _CONTENT_RE.search(text):
        hints.append("content")
    return hints


def parse_input(raw_text: str) -> InputPacket:
    """将用户原话解析为 InputPacket。"""
    raw = raw_text if raw_text is not None else ""
    normalized = _normalize(raw)
    stripped = normalized.strip()

    search_query: Optional[str] = None
    is_search_prefixed = False
    m = _SEARCH_PREFIX_RE.match(stripped)
    if m:
        is_search_prefixed = True
        search_query = m.group(1).strip() or None

    is_question_only = bool(stripped) and bool(_QUESTION_ONLY_RE.match(stripped))
    is_continue = bool(_CONTINUE_RE.match(stripped))

    return InputPacket(
        raw_text=raw,
        normalized_text=normalized,
        stripped_text=stripped,
        char_count=len(stripped),
        is_empty=not stripped,
        is_question_only=is_question_only,
        is_continue=is_continue,
        is_search_prefixed=is_search_prefixed,
        search_query=search_query,
        hints=_collect_hints(stripped),
    )
