"""Search adapter 配置 — 仅从环境变量读取，core 不感知。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


ENV_API_KEY = "SUIREN_SEARCH_API_KEY"
ENV_PROVIDER = "SUIREN_SEARCH_PROVIDER"
ENV_TIMEOUT = "SUIREN_SEARCH_TIMEOUT"
ENV_BASE_URL = "SUIREN_SEARCH_BASE_URL"

DEFAULT_PROVIDER = "brave"
DEFAULT_TIMEOUT = 10.0
DEFAULT_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


@dataclass(frozen=True)
class SearchConfig:
    api_key: str
    provider: str
    timeout_seconds: float
    base_url: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    @classmethod
    def from_env(cls, environ: Optional[dict] = None) -> "SearchConfig":
        env = environ if environ is not None else os.environ
        provider = (env.get(ENV_PROVIDER) or DEFAULT_PROVIDER).strip().lower()
        base_url = (env.get(ENV_BASE_URL) or DEFAULT_BRAVE_URL).strip()
        if provider != "brave" and env.get(ENV_BASE_URL) is None:
            base_url = (env.get(ENV_BASE_URL) or "").strip()
        try:
            timeout = float(env.get(ENV_TIMEOUT) or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        return cls(
            api_key=(env.get(ENV_API_KEY) or "").strip(),
            provider=provider,
            timeout_seconds=max(1.0, timeout),
            base_url=base_url or DEFAULT_BRAVE_URL,
        )
