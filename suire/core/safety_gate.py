"""最小边界门 — 不接爬虫，只拦明显越界输入。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .input_packet import InputPacket


_CRAWLER_CUE_RE = re.compile(
    r"(爬取|爬一下|爬网页|爬这个|爬虫|抓取网页|批量采集|scrape|crawl|spider)",
    re.IGNORECASE,
)
_AUTO_EXEC_RE = re.compile(
    r"(自动执行|帮我运行|直接执行|rm\s+-rf|format\s+c:)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SafetyVerdict:
    allowed: bool
    blocked_reason: str = ""
    warnings: List[str] = field(default_factory=list)


def check_safety(packet: InputPacket) -> SafetyVerdict:
    """最小安全门：拒绝核心层爬虫/auto-exec 诉求。"""
    text = packet.stripped_text
    warnings: List[str] = []

    if _CRAWLER_CUE_RE.search(text):
        return SafetyVerdict(
            allowed=False,
            blocked_reason="crawler_not_in_core",
            warnings=["搜索请走 tools/search_api，核心不接爬虫"],
        )

    if _AUTO_EXEC_RE.search(text):
        return SafetyVerdict(
            allowed=False,
            blocked_reason="auto_exec_not_in_v01",
            warnings=["V0.1 不接自动执行"],
        )

    if len(text) > 8000:
        warnings.append("input_truncated_recommended")

    return SafetyVerdict(allowed=True, warnings=warnings)
