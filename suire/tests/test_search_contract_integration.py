"""Search adapter 与 core 契约集成测试。"""

from __future__ import annotations

import ast
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.evidence_gate import assess_evidence, filter_evidence_items, EvidenceItem
from core.input_packet import parse_input
from core.intent_router import route_intent
from core.safety_gate import check_safety
from core.tool_contract import (
    ToolResult,
    apply_evidence_gate_to_result,
    build_tool_request,
    process_contract_turn,
)
from tools.search_api import HttpResponse, SearchAPIAdapter
from tools.search_config import SearchConfig


SUIRE_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = SUIRE_ROOT / "core"


class FakeFetcher:
    def __init__(self, response: HttpResponse):
        self.response = response

    def fetch(self, url: str, *, headers: dict, timeout: float) -> HttpResponse:
        return self.response


def _adapter_with_body(body: str, *, api_key: str = "test-key") -> SearchAPIAdapter:
    cfg = SearchConfig(
        api_key=api_key,
        provider="brave",
        timeout_seconds=5.0,
        base_url="https://api.search.brave.com/res/v1/web/search",
    )
    return SearchAPIAdapter(config=cfg, fetcher=FakeFetcher(HttpResponse(200, body)))


class TestSearchContractIntegration(unittest.TestCase):
    def test_search_intent_end_to_end(self):
        body = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "GPT Pricing",
                            "url": "https://docs.openai.com/pricing",
                            "description": "official pricing page",
                        }
                    ]
                }
            }
        )
        adapter = _adapter_with_body(body)
        turn = process_contract_turn("搜索: GPT 最新价格", backend=adapter)
        self.assertIsNotNone(turn.tool_request)
        assert turn.tool_result is not None
        self.assertEqual(turn.tool_result.status, "ok")
        self.assertGreater(len(turn.tool_result.citations), 0)
        self.assertEqual(turn.answer_decision, "answer_from_evidence")

    def test_missing_url_rejected_by_evidence_gate(self):
        packet = parse_input("搜索: test")
        intent = route_intent(packet)
        evidence = assess_evidence(packet, intent, check_safety(packet))
        req = build_tool_request(packet, intent, evidence)
        assert req is not None
        raw = ToolResult(
            status="ok",
            items=[
                {"title": "No URL", "snippet": "text only", "source": "unknown", "url": None, "trust_score": 0.9}
            ],
        )
        gated = apply_evidence_gate_to_result(raw, req, evidence)
        self.assertEqual(gated.status, "insufficient_evidence")
        self.assertIn("rejected_missing_citation", gated.error)

    def test_ad_source_rejected_in_pipeline(self):
        body = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "限时推广",
                            "url": "https://promo.example/deal",
                            "description": "赞助内容 广告",
                        }
                    ]
                }
            }
        )
        adapter = _adapter_with_body(body)
        turn = process_contract_turn("搜索: 优惠", backend=adapter)
        assert turn.tool_result is not None
        self.assertEqual(turn.tool_result.status, "insufficient_evidence")
        self.assertEqual(turn.answer_decision, "insufficient_evidence")

    def test_official_source_accepted(self):
        items = [
            EvidenceItem("Docs", "official", "docs.python.org", "https://docs.python.org/3/", 0.95),
        ]
        accepted, rejections = filter_evidence_items(items, source_policy="no_ads")
        self.assertEqual(len(accepted), 1)
        self.assertFalse(rejections)

    def test_not_configured_integration(self):
        cfg = SearchConfig(api_key="", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        adapter = SearchAPIAdapter(config=cfg, fetcher=FakeFetcher(HttpResponse(200, "{}")))
        turn = process_contract_turn("搜索: anything", backend=adapter)
        assert turn.tool_result is not None
        self.assertEqual(turn.tool_result.status, "tool_failed")
        self.assertEqual(turn.tool_result.error, "not_configured")
        self.assertEqual(turn.answer_decision, "tool_failed")

    def test_core_does_not_import_http_libraries(self):
        forbidden = {"requests", "httpx", "aiohttp", "urllib3"}
        for py in CORE_DIR.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        self.assertNotIn(root, forbidden, msg=f"{py.name} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    self.assertNotIn(root, forbidden, msg=f"{py.name} imports from {node.module}")


if __name__ == "__main__":
    unittest.main()
