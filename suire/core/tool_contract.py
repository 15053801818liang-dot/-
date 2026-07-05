"""Core → Tools 调用契约（V0.2：契约为真，工具可假）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from .evidence_gate import (
    EvidenceFrame,
    EvidenceItem,
    assess_evidence,
    citations_from_items,
    filter_evidence_items,
)
from .input_packet import InputPacket, parse_input
from .intent_router import (
    INTENT_CONTENT,
    INTENT_SEARCH,
    IntentFrame,
    route_intent,
)
from .output_policy import OutputPolicyFrame, derive_output_policy
from .safety_gate import SafetyVerdict, check_safety


DEFAULT_SOURCE_POLICY = "no_ads"
DEFAULT_MAX_RESULTS = 5


@dataclass(frozen=True)
class ToolRequest:
    """Core 向 Tools 层发出的受控请求。"""

    tool_name: str
    query: str
    reason: str
    allow_network: bool
    max_results: int
    source_policy: str


@dataclass(frozen=True)
class ToolResult:
    """Tools 层返回的标准结果。"""

    status: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    citations: List[str] = field(default_factory=list)
    raw_allowed: bool = False


class ToolBackend(Protocol):
    def invoke(self, request: ToolRequest) -> ToolResult: ...


def build_tool_request(
    packet: InputPacket,
    intent: IntentFrame,
    evidence: EvidenceFrame,
) -> Optional[ToolRequest]:
    """根据意图与证据门生成 ToolRequest；不需要工具时返回 None。"""
    if intent.intent == INTENT_CONTENT:
        return None

    if intent.intent == INTENT_SEARCH:
        query = (intent.slots or {}).get("query") or packet.search_query or packet.stripped_text
        return ToolRequest(
            tool_name="search_api",
            query=query,
            reason="explicit search prefix",
            allow_network=True,
            max_results=DEFAULT_MAX_RESULTS,
            source_policy=DEFAULT_SOURCE_POLICY,
        )

    if evidence.needs_evidence and evidence.evidence_required_for_answer:
        query = packet.stripped_text
        return ToolRequest(
            tool_name="search_api",
            query=query,
            reason=evidence.reason,
            allow_network=True,
            max_results=DEFAULT_MAX_RESULTS,
            source_policy=DEFAULT_SOURCE_POLICY,
        )

    return None


def execute_tool_request(
    request: ToolRequest,
    backend: ToolBackend,
    *,
    evidence: Optional[EvidenceFrame] = None,
) -> ToolResult:
    """执行工具契约并在 core 层做证据门后处理。"""
    if request.tool_name != "search_api":
        return ToolResult(status="tool_failed", error=f"unknown_tool:{request.tool_name}")

    if not request.allow_network and request.tool_name == "search_api":
        return ToolResult(status="tool_failed", error="network_not_allowed")

    try:
        raw = backend.invoke(request)
    except Exception as exc:  # noqa: BLE001 — 契约层必须吞掉工具异常
        return ToolResult(status="tool_failed", error=str(exc), raw_allowed=False)

    return apply_evidence_gate_to_result(raw, request, evidence)


def apply_evidence_gate_to_result(
    raw: ToolResult,
    request: ToolRequest,
    evidence: Optional[EvidenceFrame] = None,
) -> ToolResult:
    """对工具原始返回做证据门校验。"""
    if raw.status == "tool_failed":
        return ToolResult(
            status="tool_failed",
            error=raw.error or "tool_error",
            citations=[],
            raw_allowed=False,
        )

    if raw.status == "insufficient_evidence" or not raw.items:
        return ToolResult(
            status="insufficient_evidence",
            items=[],
            error=raw.error or "no_evidence_items",
            citations=[],
            raw_allowed=False,
        )

    items = [
        EvidenceItem(
            title=str(it.get("title", "")),
            snippet=str(it.get("snippet", "")),
            source=str(it.get("source", "")),
            url=it.get("url"),
            trust_score=float(it.get("trust_score", 1.0)),
        )
        for it in raw.items
    ]
    accepted, rejections = filter_evidence_items(items, source_policy=request.source_policy)

    if not accepted:
        return ToolResult(
            status="insufficient_evidence",
            items=[],
            error=";".join(rejections) if rejections else "all_items_rejected",
            citations=[],
            raw_allowed=False,
        )

    cites = citations_from_items(accepted)
    ceiling = evidence.confidence_ceiling if evidence else 0.85
    return ToolResult(
        status="ok",
        items=[_item_to_dict(i) for i in accepted],
        citations=cites,
        error="",
        raw_allowed=False,
    )


def resolve_answer_decision(
    evidence: EvidenceFrame,
    tool_request: Optional[ToolRequest],
    tool_result: Optional[ToolResult] = None,
    *,
    needs_clarification: bool = False,
) -> str:
    """Core 层最终作答决策标签。"""
    if needs_clarification and not evidence.needs_evidence:
        return "clarify"

    if not evidence.answer_allowed:
        if tool_request is None and evidence.needs_evidence:
            return "must_use_tool"
        if tool_request is not None and tool_result is None:
            return "awaiting_tool"
        if tool_result is None:
            return "clarify"
        if tool_result.status == "insufficient_evidence":
            return "insufficient_evidence"
        if tool_result.status == "tool_failed":
            return "tool_failed"
        if tool_result.status == "ok":
            return "answer_from_evidence"
        return "awaiting_tool"

    if tool_request is None:
        return "answer_direct"

    if tool_result is None:
        return "awaiting_tool"
    if tool_result.status == "insufficient_evidence":
        return "insufficient_evidence"
    if tool_result.status == "tool_failed":
        return "tool_failed"
    if tool_result.status == "ok":
        return "answer_from_evidence"
    return "awaiting_tool"


@dataclass(frozen=True)
class ContractTurn:
    """单轮契约处理结果（V0.2）。"""

    packet: InputPacket
    intent: IntentFrame
    policy: OutputPolicyFrame
    safety: SafetyVerdict
    evidence: EvidenceFrame
    tool_request: Optional[ToolRequest]
    tool_result: Optional[ToolResult]
    answer_decision: str


def process_contract_turn(
    raw_text: str,
    *,
    has_active_context: bool = False,
    last_intent: Optional[str] = None,
    backend: Optional[ToolBackend] = None,
) -> ContractTurn:
    """V0.2 契约流水线：输入 → 安全 → 路由 → 证据 → ToolRequest → 可选执行。"""
    packet = parse_input(raw_text)
    safety = check_safety(packet)
    intent = route_intent(
        packet,
        has_active_context=has_active_context,
        last_intent=last_intent,
    )
    policy = derive_output_policy(intent)
    evidence = assess_evidence(packet, intent, safety)

    tool_request: Optional[ToolRequest] = None
    tool_result: Optional[ToolResult] = None

    if safety.allowed:
        tool_request = build_tool_request(packet, intent, evidence)
        if tool_request and backend is not None:
            tool_result = execute_tool_request(tool_request, backend, evidence=evidence)

    decision = resolve_answer_decision(
        evidence,
        tool_request,
        tool_result,
        needs_clarification=intent.needs_clarification,
    )
    if not safety.allowed:
        decision = safety.blocked_reason or "blocked"

    return ContractTurn(
        packet=packet,
        intent=intent,
        policy=policy,
        safety=safety,
        evidence=evidence,
        tool_request=tool_request,
        tool_result=tool_result,
        answer_decision=decision,
    )


def _item_to_dict(item: EvidenceItem) -> Dict[str, Any]:
    return {
        "title": item.title,
        "snippet": item.snippet,
        "source": item.source,
        "url": item.url,
        "trust_score": item.trust_score,
    }
