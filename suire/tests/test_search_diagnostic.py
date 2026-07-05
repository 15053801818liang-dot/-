"""search_diagnostic 与 adapter HTTP 错误体捕获测试。"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tool_contract import ToolRequest
from tools.search_api import HttpResponse, SearchAPIAdapter
from tools.search_config import SearchConfig
from tools.search_diagnostic import (
    build_adapter_diagnostic,
    classify_adapter_error_kind,
    format_tool_error,
    redact_error_body,
    redact_token_prefix,
)


class FakeFetcher422:
    def __init__(self, body: str):
        self.body = body

    def fetch(self, url: str, *, headers: dict, timeout: float) -> HttpResponse:
        return HttpResponse(422, self.body, error="HTTP Error 422")


class TestSearchDiagnostic(unittest.TestCase):
    def test_redact_token_prefix(self):
        self.assertEqual(redact_token_prefix(""), "none")
        self.assertEqual(redact_token_prefix("sk-785ee6ce9a1841f6b53e8533736b895e"), "sk-7...")

    def test_redact_error_body_strips_api_key(self):
        key = "sk-secret-key-value"
        body = json.dumps({"message": "invalid", "token": key})
        out = redact_error_body(body, api_key=key)
        self.assertNotIn(key, out)
        self.assertIn("invalid", out)

    def test_classify_422_auth_invalid(self):
        kind = classify_adapter_error_kind(422, '{"message":"Invalid subscription token"}')
        self.assertEqual(kind, "auth_invalid")

    def test_classify_429_quota(self):
        self.assertEqual(classify_adapter_error_kind(429, "rate limit"), "quota_or_subscription")

    def test_adapter_captures_http_error_body(self):
        cfg = SearchConfig(
            api_key="test-key-1234",
            provider="brave",
            timeout_seconds=5.0,
            base_url="https://api.search.brave.com/res/v1/web/search",
        )
        body = json.dumps({"message": "Invalid subscription token", "code": "SUBSCRIPTION_INVALID"})
        adapter = SearchAPIAdapter(config=cfg, fetcher=FakeFetcher422(body))
        result = adapter.invoke(
            ToolRequest("search_api", "GPT price", "test", True, 3, "no_ads")
        )
        self.assertEqual(result.status, "tool_failed")
        self.assertIn("http_422", result.error)
        self.assertIn("auth_invalid", result.error)
        self.assertIn("Invalid subscription token", result.error)
        assert adapter.last_diagnostic is not None
        self.assertEqual(adapter.last_diagnostic.http_status, 422)
        self.assertEqual(adapter.last_diagnostic.adapter_error_kind, "auth_invalid")
        self.assertEqual(adapter.last_diagnostic.header_token_prefix_redacted, "test...")
        self.assertNotIn("test-key-1234", adapter.last_diagnostic.error_body_redacted)

    def test_format_tool_error_no_full_key(self):
        diag = build_adapter_diagnostic(
            provider="brave",
            endpoint="https://api.search.brave.com/res/v1/web/search",
            method="GET",
            api_key="abcd-secret",
            query="GPT price",
            count=3,
            http_status=422,
            response_body='{"message":"bad token"}',
        )
        err = format_tool_error(diag)
        self.assertNotIn("abcd-secret", err)
        self.assertIn("http_422:auth_invalid:", err)


if __name__ == "__main__":
    unittest.main()
