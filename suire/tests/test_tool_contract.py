"""ToolContract 单元测试 — V0.2 八场景。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.input_packet import parse_input
from core.intent_router import route_intent
from core.safety_gate import check_safety
from core.evidence_gate import assess_evidence
from core.tool_contract import (
    build_tool_request,
    execute_tool_request,
    process_contract_turn,
    resolve_answer_decision,
)
from tools.mock_backends import MockSearchBackend


class TestToolContract(unittest.TestCase):
    def test_search_prefix_builds_tool_request(self):
        packet = parse_input("搜索: GPT 最新价格")
        intent = route_intent(packet)
        evidence = assess_evidence(packet, intent, check_safety(packet))
        req = build_tool_request(packet, intent, evidence)
        self.assertIsNotNone(req)
        assert req is not None
        self.assertEqual(req.tool_name, "search_api")
        self.assertEqual(req.query, "GPT 最新价格")
        self.assertTrue(req.allow_network)

    def test_crawler_blocked_before_tool_request(self):
        turn = process_contract_turn("爬一下这个网站")
        self.assertFalse(turn.safety.allowed)
        self.assertEqual(turn.safety.blocked_reason, "crawler_not_in_core")
        self.assertIsNone(turn.tool_request)
        self.assertEqual(turn.answer_decision, "crawler_not_in_core")

    def test_factual_chat_needs_evidence_no_direct_answer(self):
        turn = process_contract_turn("你知道今天新闻吗")
        self.assertTrue(turn.evidence.needs_evidence)
        self.assertFalse(turn.evidence.answer_allowed)
        self.assertIsNotNone(turn.tool_request)
        self.assertEqual(turn.answer_decision, "awaiting_tool")

    def test_content_display_no_tool_request(self):
        turn = process_contract_turn("看内容")
        self.assertIsNone(turn.tool_request)
        self.assertTrue(turn.evidence.answer_allowed)
        self.assertEqual(turn.answer_decision, "answer_direct")

    def test_continue_with_context_no_search(self):
        turn = process_contract_turn("继续", has_active_context=True, last_intent="code_task")
        self.assertIsNone(turn.tool_request)
        self.assertFalse(turn.evidence.needs_evidence)
        self.assertEqual(turn.answer_decision, "answer_direct")

    def test_continue_without_context_clarify(self):
        turn = process_contract_turn("继续")
        self.assertFalse(turn.evidence.answer_allowed)
        self.assertIsNone(turn.tool_request)
        self.assertEqual(turn.answer_decision, "clarify")

    def test_empty_search_results_insufficient_evidence(self):
        packet = parse_input("搜索: unknown topic xyz")
        intent = route_intent(packet)
        evidence = assess_evidence(packet, intent, check_safety(packet))
        req = build_tool_request(packet, intent, evidence)
        assert req is not None
        result = execute_tool_request(req, MockSearchBackend(empty=True), evidence=evidence)
        self.assertEqual(result.status, "insufficient_evidence")
        decision = resolve_answer_decision(evidence, req, result)
        self.assertEqual(decision, "insufficient_evidence")

    def test_ad_source_rejected_by_evidence_gate(self):
        packet = parse_input("搜索: 优惠广告")
        intent = route_intent(packet)
        evidence = assess_evidence(packet, intent, check_safety(packet))
        req = build_tool_request(packet, intent, evidence)
        assert req is not None
        backend = MockSearchBackend(
            items=[
                {
                    "title": "限时推广",
                    "snippet": "赞助内容",
                    "source": "ad-network",
                    "url": "https://ads.example/promo",
                    "trust_score": 0.9,
                }
            ]
        )
        result = execute_tool_request(req, backend, evidence=evidence)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIn("rejected", result.error)

    def test_tool_error_does_not_crash(self):
        packet = parse_input("搜索: fail case")
        intent = route_intent(packet)
        evidence = assess_evidence(packet, intent, check_safety(packet))
        req = build_tool_request(packet, intent, evidence)
        assert req is not None
        result = execute_tool_request(
            req,
            MockSearchBackend(fail=True, fail_message="network down"),
            evidence=evidence,
        )
        self.assertEqual(result.status, "tool_failed")
        decision = resolve_answer_decision(evidence, req, result)
        self.assertEqual(decision, "tool_failed")


if __name__ == "__main__":
    unittest.main()
