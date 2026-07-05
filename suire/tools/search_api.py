"""真实 Search Adapter — 外网能力仅存在于 tools 层（stdlib urllib）。"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol

from core.tool_contract import ToolRequest, ToolResult

from .search_config import SearchConfig, DEFAULT_BRAVE_URL
from .search_diagnostic import (
    AdapterDiagnostic,
    build_adapter_diagnostic,
    format_tool_error,
)


class HttpFetcher(Protocol):
    """可注入 HTTP 客户端，供测试替换真实网络。"""

    def fetch(self, url: str, *, headers: Dict[str, str], timeout: float) -> "HttpResponse": ...


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: str
    error: str = ""


class UrllibFetcher:
    """默认 stdlib 实现 — 不依赖 requests/httpx。"""

    def fetch(self, url: str, *, headers: Dict[str, str], timeout: float) -> HttpResponse:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return HttpResponse(status_code=getattr(resp, "status", 200) or 200, body=body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return HttpResponse(status_code=exc.code, body=body, error=str(exc))
        except socket.timeout:
            return HttpResponse(status_code=0, body="", error="timeout")
        except urllib.error.URLError as exc:
            return HttpResponse(status_code=0, body="", error=str(exc.reason or exc))
        except Exception as exc:  # noqa: BLE001
            return HttpResponse(status_code=0, body="", error=str(exc))


_OFFICIAL_HINTS = (".gov", ".edu", "docs.", "developer.", "wikipedia.org", "github.com")


def trust_score_for_url(url: str) -> float:
    u = (url or "").lower()
    if not u.startswith("http"):
        return 0.2
    if any(h in u for h in _OFFICIAL_HINTS):
        return 0.95
    if "ad." in u or "ads." in u or "promo." in u:
        return 0.1
    return 0.75


def normalize_brave_results(payload: dict, *, limit: int) -> List[Dict[str, Any]]:
    web = payload.get("web") or {}
    results = web.get("results") or []
    items: List[Dict[str, Any]] = []
    for row in results[:limit]:
        url = row.get("url") or ""
        title = row.get("title") or ""
        snippet = row.get("description") or row.get("snippet") or ""
        if not title and not snippet:
            continue
        source = urllib.parse.urlparse(url).netloc or "unknown"
        items.append(
            {
                "title": str(title),
                "snippet": str(snippet),
                "source": source,
                "url": url or None,
                "trust_score": trust_score_for_url(url),
            }
        )
    return items


def normalize_json_results(payload: dict, *, limit: int) -> List[Dict[str, Any]]:
    """通用 JSON 列表格式 [{title, snippet, source, url}]。"""
    rows = payload if isinstance(payload, list) else payload.get("results") or payload.get("items") or []
    items: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        url = row.get("url") or row.get("link")
        items.append(
            {
                "title": str(row.get("title") or ""),
                "snippet": str(row.get("snippet") or row.get("description") or ""),
                "source": str(row.get("source") or urllib.parse.urlparse(str(url or "")).netloc or "unknown"),
                "url": url,
                "trust_score": float(row.get("trust_score", trust_score_for_url(str(url or "")))),
            }
        )
    return items


class SearchAPIAdapter:
    """V0.3 真实 search adapter — 实现 ToolBackend.invoke。"""

    def __init__(
        self,
        config: Optional[SearchConfig] = None,
        fetcher: Optional[HttpFetcher] = None,
        *,
        response_parser: Optional[Callable[[dict, int], List[Dict[str, Any]]]] = None,
    ) -> None:
        self.config = config or SearchConfig.from_env()
        self.fetcher = fetcher or UrllibFetcher()
        self.response_parser = response_parser or normalize_brave_results
        self.last_diagnostic: Optional[AdapterDiagnostic] = None

    def invoke(self, request: ToolRequest) -> ToolResult:
        self.last_diagnostic = None
        if request.tool_name != "search_api":
            return ToolResult(status="tool_failed", error=f"wrong_tool:{request.tool_name}")

        if not request.allow_network:
            return ToolResult(status="tool_failed", error="network_not_allowed")

        if not self.config.is_configured:
            return ToolResult(status="tool_failed", error="not_configured")

        query = (request.query or "").strip()
        if not query:
            return ToolResult(status="insufficient_evidence", items=[], error="empty_query")

        return self._search(query, limit=request.max_results)

    def _search(self, query: str, *, limit: int) -> ToolResult:
        url = self._build_url(query, limit)
        headers = self._build_headers()
        resp = self.fetcher.fetch(url, headers=headers, timeout=self.config.timeout_seconds)

        if resp.error == "timeout" or "timeout" in resp.error.lower():
            self.last_diagnostic = build_adapter_diagnostic(
                provider=self.config.provider,
                endpoint=url.split("?")[0],
                method="GET",
                api_key=self.config.api_key,
                query=query,
                count=limit,
                http_status=0,
                response_body="timeout",
            )
            return ToolResult(status="tool_failed", error="timeout")

        if resp.status_code == 0 or resp.status_code >= 400:
            endpoint = self.config.base_url.split("?")[0]
            self.last_diagnostic = build_adapter_diagnostic(
                provider=self.config.provider,
                endpoint=endpoint,
                method="GET",
                api_key=self.config.api_key,
                query=query,
                count=limit,
                http_status=resp.status_code,
                response_body=resp.body or resp.error,
            )
            return ToolResult(
                status="tool_failed",
                error=format_tool_error(self.last_diagnostic),
            )

        try:
            payload = json.loads(resp.body) if resp.body else {}
        except json.JSONDecodeError:
            return ToolResult(status="tool_failed", error="invalid_json")

        items = self.response_parser(payload, limit=limit)
        if not items:
            return ToolResult(status="insufficient_evidence", items=[], error="empty_results")

        return ToolResult(status="ok", items=items, raw_allowed=False)

    def _build_url(self, query: str, limit: int) -> str:
        params = urllib.parse.urlencode({"q": query, "count": str(limit)})
        base = self.config.base_url.rstrip("?&")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{params}"

    def _build_headers(self) -> Dict[str, str]:
        if self.config.provider == "brave":
            return {
                "Accept": "application/json",
                "X-Subscription-Token": self.config.api_key,
            }
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }


# 向后兼容旧占位类名
SearchAPI = SearchAPIAdapter
