"""证据门 — 判定是否需要外部证据、能否直接作答。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .input_packet import InputPacket
from .intent_router import (
    INTENT_CHAT,
    INTENT_CONTENT,
    INTENT_CONTINUE,
    INTENT_FOLLOW_UP,
    INTENT_SEARCH,
    IntentFrame,
)
from .safety_gate import SafetyVerdict


_EVIDENCE_CUE_RE = re.compile(
    r"(今天|今日|最新|现在|当前|新闻|头条|股价|价格|行情|天气|汇率|"
    r"多少|几点|何时|什么时候|你知道吗|查一下|帮我查|实时)",
    re.IGNORECASE,
)

_AD_SOURCE_RE = re.compile(
    r"(广告|推广|赞助|sponsored|affiliate|clickbait|seo\s*spam)",
    re.IGNORECASE,
)

_LOW_TRUST_DOMAINS = ("ad.", "ads.", "promo.", "spam.")


@dataclass(frozen=True)
class EvidenceFrame:
    """证据需求与作答许可。"""

    needs_evidence: bool
    evidence_required_for_answer: bool
    confidence_ceiling: float
    answer_allowed: bool
    reason: str


@dataclass(frozen=True)
class EvidenceItem:
    """通过证据门后的单条证据。"""

    title: str
    snippet: str
    source: str
    url: Optional[str] = None
    trust_score: float = 1.0


def assess_evidence(
    packet: InputPacket,
    intent: IntentFrame,
    safety: SafetyVerdict,
) -> EvidenceFrame:
    """根据意图与安全判定证据需求。"""
    if not safety.allowed:
        return EvidenceFrame(
            needs_evidence=False,
            evidence_required_for_answer=False,
            confidence_ceiling=0.0,
            answer_allowed=False,
            reason=safety.blocked_reason or "blocked_by_safety",
        )

    name = intent.intent

    if name == INTENT_SEARCH:
        return EvidenceFrame(
            needs_evidence=True,
            evidence_required_for_answer=True,
            confidence_ceiling=0.85,
            answer_allowed=False,
            reason="explicit search prefix requires tool evidence",
        )

    if name == INTENT_CONTENT:
        return EvidenceFrame(
            needs_evidence=False,
            evidence_required_for_answer=False,
            confidence_ceiling=0.9,
            answer_allowed=True,
            reason="display existing content only",
        )

    if name in (INTENT_FOLLOW_UP, INTENT_CONTINUE):
        return EvidenceFrame(
            needs_evidence=False,
            evidence_required_for_answer=False,
            confidence_ceiling=0.8,
            answer_allowed=not intent.needs_clarification,
            reason="follow_up/continue uses context not external fetch",
        )

    if name == INTENT_CHAT and _EVIDENCE_CUE_RE.search(packet.stripped_text):
        return EvidenceFrame(
            needs_evidence=True,
            evidence_required_for_answer=True,
            confidence_ceiling=0.6,
            answer_allowed=False,
            reason="time-sensitive factual query requires tool evidence",
        )

    return EvidenceFrame(
        needs_evidence=False,
        evidence_required_for_answer=False,
        confidence_ceiling=0.85,
        answer_allowed=True,
        reason="no external evidence required",
    )


def filter_evidence_items(
    items: List[EvidenceItem],
    *,
    source_policy: str = "no_ads",
) -> tuple[List[EvidenceItem], List[str]]:
    """过滤广告/低信任来源，返回可用证据与拒绝原因。"""
    accepted: List[EvidenceItem] = []
    rejections: List[str] = []

    for item in items:
        text_blob = f"{item.title} {item.snippet} {item.source} {item.url or ''}"
        if not item.url or not str(item.url).strip():
            rejections.append(f"rejected_missing_citation:{item.source or 'unknown'}")
            continue
        if source_policy == "no_ads" and _AD_SOURCE_RE.search(text_blob):
            rejections.append(f"rejected_ad_source:{item.source}")
            continue
        if item.url and any(d in item.url.lower() for d in _LOW_TRUST_DOMAINS):
            rejections.append(f"rejected_low_trust_domain:{item.url}")
            continue
        if item.trust_score < 0.4:
            rejections.append(f"rejected_low_trust_score:{item.source}")
            continue
        accepted.append(item)

    return accepted, rejections


def citations_from_items(items: List[EvidenceItem]) -> List[str]:
    cites: List[str] = []
    for i, item in enumerate(items, 1):
        cites.append(f"[{i}] {item.source}: {item.title}")
    return cites
