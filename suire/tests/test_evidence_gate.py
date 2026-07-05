"""EvidenceGate 单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.evidence_gate import EvidenceItem, assess_evidence, filter_evidence_items
from core.input_packet import parse_input
from core.intent_router import route_intent
from core.safety_gate import check_safety


class TestEvidenceGate(unittest.TestCase):
    def test_search_requires_evidence(self):
        packet = parse_input("搜索: BTC")
        intent = route_intent(packet)
        ev = assess_evidence(packet, intent, check_safety(packet))
        self.assertTrue(ev.needs_evidence)
        self.assertTrue(ev.evidence_required_for_answer)
        self.assertFalse(ev.answer_allowed)

    def test_chat_news_requires_evidence(self):
        packet = parse_input("你知道今天新闻吗")
        intent = route_intent(packet)
        ev = assess_evidence(packet, intent, check_safety(packet))
        self.assertTrue(ev.needs_evidence)
        self.assertFalse(ev.answer_allowed)

    def test_casual_chat_allowed(self):
        packet = parse_input("你好，介绍一下你自己")
        intent = route_intent(packet)
        ev = assess_evidence(packet, intent, check_safety(packet))
        self.assertFalse(ev.needs_evidence)
        self.assertTrue(ev.answer_allowed)

    def test_filter_rejects_ad_sources(self):
        items = [
            EvidenceItem("推广", "赞助", "ad-network", "https://ads.example/x", 0.9),
            EvidenceItem("官方", "数据", "gov.cn", "https://gov.cn/data", 0.95),
        ]
        accepted, rejections = filter_evidence_items(items, source_policy="no_ads")
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].source, "gov.cn")
        self.assertTrue(rejections)


if __name__ == "__main__":
    unittest.main()
