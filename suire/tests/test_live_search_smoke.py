"""live_search_smoke 格式与验收逻辑测试 — 使用 Mock，不接 live API。"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tool_contract import ToolRequest, ToolResult
from tools.live_search_smoke import SmokeReport, _evaluate_pass, run_live_smoke
from tools.mock_backends import MockSearchBackend
from tools.search_api import HttpResponse, SearchAPIAdapter
from tools.search_config import SearchConfig


class TestLiveSearchSmoke(unittest.TestCase):
    def test_no_api_key_reports_not_configured(self):
        cfg = SearchConfig(api_key="", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        adapter = SearchAPIAdapter(config=cfg)
        report = run_live_smoke("GPT price", config=cfg, adapter=adapter)
        self.assertFalse(report.api_key_present)
        self.assertFalse(report.smoke_pass)
        self.assertIn("SKIP", report.smoke_notes[0])

    def test_mock_ok_passes_with_citations(self):
        cfg = SearchConfig(api_key="secret-key-xyz", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")
        backend = MockSearchBackend(
            items=[
                {
                    "title": "GPT Pricing",
                    "snippet": "official",
                    "source": "docs.openai.com",
                    "url": "https://docs.openai.com/pricing",
                    "trust_score": 0.95,
                }
            ]
        )

        class MockAdapter:
            def invoke(self, request: ToolRequest) -> ToolResult:
                return backend.invoke(request)

        report = run_live_smoke("GPT price", config=cfg, adapter=MockAdapter())
        output = "\n".join(report.to_log_lines())
        self.assertNotIn("secret-key-xyz", output)
        self.assertTrue(report.api_key_present)
        self.assertEqual(report.status, "ok")
        self.assertGreaterEqual(report.citations_count, 1)
        self.assertEqual(report.missing_url_count, 0)
        self.assertTrue(report.smoke_pass)

    def test_tool_failed_explicit_pass_with_notes(self):
        cfg = SearchConfig(api_key="key", provider="brave", timeout_seconds=5.0, base_url="https://api.example/search")

        class FailAdapter:
            def invoke(self, request: ToolRequest) -> ToolResult:
                return ToolResult(status="tool_failed", error="timeout")

        report = run_live_smoke("GPT price", config=cfg, adapter=FailAdapter())
        self.assertEqual(report.status, "tool_failed")
        self.assertTrue(report.smoke_pass)
        self.assertIn("PASS_WITH_TOOL_FAILED", report.smoke_notes[0])

    def test_report_fields_present(self):
        report = SmokeReport(
            timestamp="2026-07-05T22:00:00Z",
            provider="brave",
            api_key_present=True,
            query="GPT price",
            status="ok",
            error="",
            item_count=1,
            citations_count=1,
            missing_url_count=0,
            ads_rejected_count=0,
            elapsed_ms=120,
            smoke_pass=True,
            smoke_notes=["PASS"],
        )
        text = "\n".join(report.to_log_lines())
        for key in (
            "provider=brave",
            "api_key_present=True",
            'query="GPT price"',
            "status=ok",
            "citations_count=1",
            "missing_url_count=0",
            "elapsed_ms=120",
        ):
            self.assertIn(key, text)

    def test_evaluate_fail_ok_without_citations(self):
        report = SmokeReport(
            timestamp="t",
            provider="brave",
            api_key_present=True,
            query="q",
            status="ok",
            error="",
            item_count=0,
            citations_count=0,
            missing_url_count=0,
            ads_rejected_count=0,
            elapsed_ms=1,
            smoke_pass=False,
            smoke_notes=[],
        )
        passed, notes = _evaluate_pass(report)
        self.assertFalse(passed)
        self.assertIn("citations_count", notes[0])


if __name__ == "__main__":
    unittest.main()
