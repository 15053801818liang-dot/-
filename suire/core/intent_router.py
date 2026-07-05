"""意图路由 — InputPacket + 上下文 → IntentFrame。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .input_packet import InputPacket


INTENT_FOLLOW_UP = "follow_up"
INTENT_CONTINUE = "continue"
INTENT_SEARCH = "search_intent"
INTENT_CONTENT = "content_display"
INTENT_CODE = "code_task"
INTENT_AUDIT = "audit_task"
INTENT_MEMORY = "memory_task"
INTENT_CHAT = "chat"
INTENT_EMPTY = "empty_input"


@dataclass(frozen=True)
class IntentFrame:
    """路由结果。"""

    intent: str
    confidence: float
    reason: str
    slots: Dict[str, Any] = field(default_factory=dict)
    requires_context: bool = False
    needs_clarification: bool = False


def route_intent(
    packet: InputPacket,
    *,
    has_active_context: bool = False,
    last_intent: Optional[str] = None,
) -> IntentFrame:
    """根据 InputPacket 与任务上下文判定意图。"""
    if packet.is_empty:
        return IntentFrame(
            intent=INTENT_EMPTY,
            confidence=1.0,
            reason="empty input",
            needs_clarification=True,
        )

    if packet.is_question_only:
        return IntentFrame(
            intent=INTENT_FOLLOW_UP,
            confidence=1.0,
            reason="question mark only → follow-up, no search",
            requires_context=not has_active_context,
            needs_clarification=not has_active_context,
        )

    if packet.is_continue:
        if has_active_context:
            return IntentFrame(
                intent=INTENT_CONTINUE,
                confidence=1.0,
                reason="continue with active context",
                slots={"resume_from": last_intent},
            )
        return IntentFrame(
            intent=INTENT_CONTINUE,
            confidence=0.6,
            reason="continue without context → need clarification",
            needs_clarification=True,
        )

    if packet.is_search_prefixed:
        return IntentFrame(
            intent=INTENT_SEARCH,
            confidence=1.0,
            reason="explicit search prefix",
            slots={"query": packet.search_query or ""},
        )

    if packet.has_hint("content"):
        return IntentFrame(
            intent=INTENT_CONTENT,
            confidence=0.95,
            reason="content display cue",
        )

    if packet.has_hint("code"):
        return IntentFrame(
            intent=INTENT_CODE,
            confidence=0.9,
            reason="code task cue",
            slots={"task_text": packet.stripped_text},
        )

    if packet.has_hint("audit"):
        return IntentFrame(
            intent=INTENT_AUDIT,
            confidence=0.9,
            reason="audit task cue",
            slots={"task_text": packet.stripped_text},
        )

    if packet.has_hint("memory"):
        op = _memory_operation(packet.stripped_text)
        return IntentFrame(
            intent=INTENT_MEMORY,
            confidence=0.92,
            reason="memory task cue",
            slots={"operation": op, "task_text": packet.stripped_text},
        )

    return IntentFrame(
        intent=INTENT_CHAT,
        confidence=0.85,
        reason="default chat",
        slots={"message": packet.stripped_text},
    )


def _memory_operation(text: str) -> str:
    forget_words = ("忘掉", "忘记", "删除记忆", "清除记忆")
    if any(w in text for w in forget_words):
        return "forget"
    return "remember"
