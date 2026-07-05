"""燧人核心 — 可控输入智能体（无爬虫）。"""

from .input_packet import InputPacket, parse_input
from .intent_router import IntentFrame, route_intent
from .output_policy import OutputPolicyFrame, derive_output_policy
from .task_state import TaskContext, TaskState, TaskStateMachine
from .safety_gate import SafetyVerdict, check_safety
from .tool_contract import (
    ContractTurn,
    ToolRequest,
    ToolResult,
    build_tool_request,
    execute_tool_request,
    process_contract_turn,
    resolve_answer_decision,
)
from .evidence_gate import EvidenceFrame, assess_evidence

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
    "EvidenceFrame",
    "assess_evidence",
    "ToolRequest",
    "ToolResult",
    "ContractTurn",
    "build_tool_request",
    "execute_tool_request",
    "process_contract_turn",
    "resolve_answer_decision",
]
