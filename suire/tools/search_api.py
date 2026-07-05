"""搜索 API 占位 — 非爬虫，V0.1 仅声明接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SearchResult:
    title: str
    snippet: str
    source: str
    url: Optional[str] = None


class SearchAPI:
    """受控搜索工具。V0.1 不实现网络调用。"""

    def search(self, query: str, *, limit: int = 5) -> List[SearchResult]:
        if not query or not query.strip():
            return []
        raise NotImplementedError(
            "SearchAPI.search 未接入；V0.1 仅路由 search_intent，不抓网页"
        )
