"""任务状态机 — 上下文与继续/追问流转。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from .input_packet import InputPacket, parse_input
from .intent_router import IntentFrame, route_intent
from .output_policy import OutputPolicyFrame, derive_output_policy


class TaskState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    AWAITING_FOLLOW_UP = "awaiting_follow_up"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    COMPLETED = "completed"


@dataclass
class TaskContext:
    """轻量任务上下文（无数据库）。"""

    state: TaskState = TaskState.IDLE
    last_intent: Optional[str] = None
    last_user_text: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_active_context(self) -> bool:
        return self.state in (
            TaskState.ACTIVE,
            TaskState.AWAITING_FOLLOW_UP,
            TaskState.AWAITING_CLARIFICATION,
        ) and bool(self.last_intent)


@dataclass(frozen=True)
class TurnResult:
    """单轮处理结果。"""

    packet: InputPacket
    intent: IntentFrame
    policy: OutputPolicyFrame
    context: TaskContext


class TaskStateMachine:
    """输入 → 路由 → 输出策略 → 状态更新。"""

    def __init__(self) -> None:
        self.context = TaskContext()

    def reset(self) -> None:
        self.context = TaskContext()

    def process(self, raw_text: str) -> TurnResult:
        packet = parse_input(raw_text)
        intent = route_intent(
            packet,
            has_active_context=self.context.has_active_context,
            last_intent=self.context.last_intent,
        )
        policy = derive_output_policy(intent)
        self._update_state(packet, intent)
        return TurnResult(
            packet=packet,
            intent=intent,
            policy=policy,
            context=self.context,
        )

    def _update_state(self, packet: InputPacket, intent: IntentFrame) -> None:
        if packet.is_empty:
            self.context.state = TaskState.AWAITING_CLARIFICATION
            return

        if intent.needs_clarification:
            self.context.state = TaskState.AWAITING_CLARIFICATION
            self.context.last_user_text = packet.stripped_text
            return

        if intent.intent == "follow_up":
            self.context.state = TaskState.AWAITING_FOLLOW_UP
            self.context.last_user_text = packet.stripped_text
            return

        if intent.intent == "continue" and not intent.needs_clarification:
            self.context.state = TaskState.ACTIVE
            return

        self.context.state = TaskState.ACTIVE
        self.context.last_intent = intent.intent
        self.context.last_user_text = packet.stripped_text
        self.context.payload = dict(intent.slots)
