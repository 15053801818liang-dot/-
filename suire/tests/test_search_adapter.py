"""SearchAPIAdapter 单元测试 — V0.3 八门禁。"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tool_contract import ToolRequest
from tools.search_api import HttpResponse, SearchAPIAdapter, normalize_brave_results, trust_score_for_url
from tools.search_config import SearchConfig


def _req(query: str = "test") -> ToolRequest:
    return ToolRequest(
        tool_name="search_api",
        query=query,
        reason="test",
        allow_network=True,
        max_results=5,
        source_policy="no_ads",
    )


class FakeFetcher:
    def __init__(self, response: HttpResponse):
        self.response = response
        self.calls = 0

    def fetch(self, url: str, *, headers: dict, timeout: float) -> HttpResponse:
        self.calls += 1
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout
        return self.response


class TestSearchAdapter(unittest.TestCase):
    def test_no_api_key_not_configured(self):
        cfg = SearchConfig(api_key="", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        adapter = SearchAPIAdapter(config=cfg, fetcher=FakeFetcher(HttpResponse(200, "{}")))
        result = adapter.invoke(_req())
        self.assertEqual(result.status, "tool_failed")
        self.assertEqual(result.error, "not_configured")

    def test_timeout_returns_tool_failed(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=1.0, base_url="https://api.example/search")
        fetcher = FakeFetcher(HttpResponse(0, "", error="timeout"))
        result = SearchAPIAdapter(config=cfg, fetcher=fetcher).invoke(_req())
        self.assertEqual(result.status, "tool_failed")
        self.assertEqual(result.error, "timeout")

    def test_empty_results_insufficient_evidence(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        body = json.dumps({"web": {"results": []}})
        fetcher = FakeFetcher(HttpResponse(200, body))
        result = SearchAPIAdapter(config=cfg, fetcher=fetcher).invoke(_req())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.error, "empty_results")

    def test_http_error_tool_failed(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        fetcher = FakeFetcher(HttpResponse(401, "", error="http_401"))
        result = SearchAPIAdapter(config=cfg, fetcher=fetcher).invoke(_req())
        self.assertEqual(result.status, "tool_failed")

    def test_brave_parser_official_source_high_trust(self):
        payload = {
            "web": {
                "results": [
                    {
                        "title": "Python Docs",
                        "url": "https://docs.python.org/3/",
                        "description": "official documentation",
                    }
                ]
            }
        }
        items = normalize_brave_results(payload, limit=5)
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(items[0]["trust_score"], 0.9)
        self.assertIn("docs.", items[0]["url"])

    def test_trust_score_low_for_ad_domain(self):
        score = trust_score_for_url("https://ads.example/promo")
        self.assertLess(score, 0.4)

    def test_successful_search_returns_ok_with_items(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        body = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "GPT price",
                            "url": "https://example.gov/gpt",
                            "description": "market data",
                        }
                    ]
                }
            }
        )
        fetcher = FakeFetcher(HttpResponse(200, body))
        result = SearchAPIAdapter(config=cfg, fetcher=fetcher).invoke(_req("GPT 最新价格"))
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.items), 1)
        self.assertTrue(result.items[0]["url"])
        self.assertEqual(fetcher.calls, 1)

    def test_network_disabled_on_request(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        req = ToolRequest(
            tool_name="search_api",
            query="x",
            reason="test",
            allow_network=False,
            max_results=5,
            source_policy="no_ads",
        )
        result = SearchAPIAdapter(config=cfg, fetcher=FakeFetcher(HttpResponse(200, "{}"))).invoke(req)
        self.assertEqual(result.status, "tool_failed")
        self.assertEqual(result.error, "network_not_allowed")


if __name__ == "__main__":
    unittest.main()
