"""Brave search adapter 诊断 — 仅 tools 层，不改 core。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional


_TOKEN_LIKE_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE)
_SUBSCRIPTION_TOKEN_RE = re.compile(r"(subscription[_\s-]?token|X-Subscription-Token)", re.IGNORECASE)


@dataclass(frozen=True)
class AdapterDiagnostic:
    provider: str
    endpoint: str
    method: str
    header_token_present: bool
    header_token_prefix_redacted: str
    query_present: bool
    count: int
    http_status: int
    error_body_redacted: str
    adapter_error_kind: str

    def to_log_lines(self) -> list[str]:
        return [
            f"diag_provider={self.provider}",
            f"diag_endpoint={self.endpoint}",
            f"diag_method={self.method}",
            f"diag_header_token_present={self.header_token_present}",
            f"diag_header_token_prefix_redacted={self.header_token_prefix_redacted}",
            f"diag_query_present={self.query_present}",
            f"diag_count={self.count}",
            f"diag_http_status={self.http_status}",
            f"diag_adapter_error_kind={self.adapter_error_kind}",
            f"diag_error_body_redacted={self.error_body_redacted or 'none'}",
        ]


def redact_token_prefix(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return "none"
    if len(key) <= 4:
        return "****"
    return f"{key[:4]}..."


def redact_error_body(body: str, *, api_key: str = "", limit: int = 500) -> str:
    text = body or ""
    if api_key:
        text = text.replace(api_key, "[REDACTED_KEY]")
    text = _TOKEN_LIKE_RE.sub("[REDACTED_TOKEN]", text)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def classify_adapter_error_kind(http_status: int, body: str) -> str:
    blob = (body or "").lower()
    if http_status in (401, 403):
        return "auth_invalid"
    if http_status == 422:
        if any(k in blob for k in ("subscription", "token", "invalid key", "unauthorized")):
            return "auth_invalid"
        return "provider_422"
    if http_status == 400:
        return "bad_request"
    if http_status == 429:
        return "quota_or_subscription"
    if http_status >= 500:
        return "unknown_http_error"
    if http_status >= 400:
        return "unknown_http_error"
    return "unknown_http_error"


def summarize_json_error(body: str) -> str:
    if not body:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:200]
    if isinstance(data, dict):
        for key in ("message", "error", "detail", "title", "code"):
            if key in data and data[key]:
                return str(data[key])[:200]
    return body[:200]


def build_adapter_diagnostic(
    *,
    provider: str,
    endpoint: str,
    method: str,
    api_key: str,
    query: str,
    count: int,
    http_status: int,
    response_body: str,
) -> AdapterDiagnostic:
    body_redacted = redact_error_body(response_body, api_key=api_key)
    summary = summarize_json_error(response_body)
    if summary and summary not in body_redacted:
        body_redacted = f"{summary} | {body_redacted}".strip(" |")

    return AdapterDiagnostic(
        provider=provider,
        endpoint=endpoint,
        method=method,
        header_token_present=bool(api_key.strip()),
        header_token_prefix_redacted=redact_token_prefix(api_key),
        query_present=bool((query or "").strip()),
        count=count,
        http_status=http_status,
        error_body_redacted=body_redacted,
        adapter_error_kind=classify_adapter_error_kind(http_status, response_body or summary),
    )


def format_tool_error(diagnostic: AdapterDiagnostic) -> str:
    """结构化 tool_failed error 字符串（不含完整 key）。"""
    return (
        f"http_{diagnostic.http_status}:"
        f"{diagnostic.adapter_error_kind}:"
        f"{diagnostic.error_body_redacted or 'no_body'}"
    )
