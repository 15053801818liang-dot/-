"""燧人核心 — 可控输入智能体（无爬虫）。"""

from .input_packet import InputPacket, parse_input
from .intent_router import IntentFrame, route_intent
from .output_policy import OutputPolicyFrame, derive_output_policy
from .task_state import TaskContext, TaskState, TaskStateMachine
from .safety_gate import SafetyVerdict, check_safety

__all__ = [
    "InputPacket",
    "parse_input",
    "IntentFrame",
    "route_intent",
    "OutputPolicyFrame",
    "derive_output_policy",
    "TaskContext",
    "TaskState",
    "TaskStateMachine",
    "SafetyVerdict",
    "check_safety",
]
