"""假工具后端 — 仅用于契约测试，不接外网。"""

from __future__ import annotations

from typing import Callable, List, Optional

from core.tool_contract import ToolBackend, ToolRequest, ToolResult


class MockSearchBackend:
    """可配置的 search_api 假后端。"""

    def __init__(
        self,
        *,
        items: Optional[List[dict]] = None,
        empty: bool = False,
        fail: bool = False,
        fail_message: str = "mock_search_error",
    ) -> None:
        self.items = items
        self.empty = empty
        self.fail = fail
        self.fail_message = fail_message

    def invoke(self, request: ToolRequest) -> ToolResult:
        if self.fail:
            raise RuntimeError(self.fail_message)

        if self.empty or self.items == []:
            return ToolResult(status="insufficient_evidence", items=[], error="empty_results")

        if self.items is not None:
            return ToolResult(status="ok", items=list(self.items), raw_allowed=False)

        return ToolResult(
            status="ok",
            items=[
                {
                    "title": f"Result for {request.query}",
                    "snippet": "official data",
                    "source": "example.gov",
                    "url": "https://example.gov/data",
                    "trust_score": 0.95,
                }
            ],
            raw_allowed=False,
        )


def make_callable_backend(fn: Callable[[ToolRequest], ToolResult]) -> ToolBackend:
    class _FnBackend:
        def invoke(self, request: ToolRequest) -> ToolResult:
            return fn(request)

    return _FnBackend()
