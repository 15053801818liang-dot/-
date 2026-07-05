"""LLM 客户端占位 — V0.1 不接入模型并发。"""

from __future__ import annotations

from typing import Any, Dict, List


class LLMClient:
    def complete(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        raise NotImplementedError("LLMClient 未接入；V0.1 只做路由与输出策略")
