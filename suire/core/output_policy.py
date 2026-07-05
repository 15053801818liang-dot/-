"""输出裁剪 — IntentFrame → OutputPolicyFrame。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .intent_router import (
    INTENT_AUDIT,
    INTENT_CHAT,
    INTENT_CODE,
    INTENT_CONTENT,
    INTENT_CONTINUE,
    INTENT_EMPTY,
    INTENT_FOLLOW_UP,
    INTENT_MEMORY,
    INTENT_SEARCH,
    IntentFrame,
)


@dataclass(frozen=True)
class OutputPolicyFrame:
    """输出策略约束。"""

    mode: str
    max_sentences: int
    max_chars: int
    allow_search: bool
    allow_tool_fetch: bool
    suppress_expansion: bool
    require_brief: bool
    clarification_only: bool
    note: str


def derive_output_policy(intent: IntentFrame) -> OutputPolicyFrame:
    """根据意图生成输出裁剪策略。"""
    name = intent.intent

    if name == INTENT_FOLLOW_UP:
        return OutputPolicyFrame(
            mode="follow_up",
            max_sentences=2,
            max_chars=120,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=True,
            require_brief=True,
            clarification_only=intent.needs_clarification,
            note="追问：短答，不补搜，不长篇",
        )

    if name == INTENT_CONTINUE:
        if intent.needs_clarification:
            return OutputPolicyFrame(
                mode="clarify_continue",
                max_sentences=2,
                max_chars=100,
                allow_search=False,
                allow_tool_fetch=False,
                suppress_expansion=True,
                require_brief=True,
                clarification_only=True,
                note="无上下文继续 → 先追问",
            )
        return OutputPolicyFrame(
            mode="resume",
            max_sentences=6,
            max_chars=800,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=False,
            require_brief=False,
            clarification_only=False,
            note="有上下文继续任务",
        )

    if name == INTENT_SEARCH:
        return OutputPolicyFrame(
            mode="search",
            max_sentences=4,
            max_chars=400,
            allow_search=True,
            allow_tool_fetch=True,
            suppress_expansion=True,
            require_brief=True,
            clarification_only=False,
            note="搜索走受控工具层，核心不爬虫",
        )

    if name == INTENT_CONTENT:
        return OutputPolicyFrame(
            mode="display",
            max_sentences=8,
            max_chars=1200,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=True,
            require_brief=False,
            clarification_only=False,
            note="展示已有内容，不外扩",
        )

    if name in (INTENT_CODE, INTENT_AUDIT):
        return OutputPolicyFrame(
            mode="task",
            max_sentences=12,
            max_chars=2000,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=True,
            require_brief=False,
            clarification_only=False,
            note="任务型输出，聚焦变更/结论",
        )

    if name == INTENT_MEMORY:
        return OutputPolicyFrame(
            mode="memory_ack",
            max_sentences=2,
            max_chars=80,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=True,
            require_brief=True,
            clarification_only=False,
            note="记忆确认短答",
        )

    if name == INTENT_EMPTY:
        return OutputPolicyFrame(
            mode="empty",
            max_sentences=1,
            max_chars=60,
            allow_search=False,
            allow_tool_fetch=False,
            suppress_expansion=True,
            require_brief=True,
            clarification_only=True,
            note="空输入提示",
        )

    # chat default — 短问短答
    msg = (intent.slots or {}).get("message", "")
    is_short = len(msg) <= 12
    return OutputPolicyFrame(
        mode="chat_brief" if is_short else "chat",
        max_sentences=2 if is_short else 5,
        max_chars=120 if is_short else 600,
        allow_search=False,
        allow_tool_fetch=False,
        suppress_expansion=is_short,
        require_brief=is_short,
        clarification_only=False,
        note="普通聊天：短问短答",
    )


def apply_output_policy(text: str, policy: OutputPolicyFrame) -> str:
    """按策略裁剪输出文本（句子/字符双限）。"""
    if not text:
        return text
    trimmed = text.strip()
    if len(trimmed) <= policy.max_chars:
        clipped = trimmed
    else:
        clipped = trimmed[: policy.max_chars].rstrip()
        if clipped and clipped[-1] not in "。！？?!.":
            clipped += "…"

    sentences = _split_sentences(clipped)
    if len(sentences) > policy.max_sentences:
        clipped = "".join(sentences[: policy.max_sentences])
    return clipped


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？!?.\n":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts if parts else [text]
