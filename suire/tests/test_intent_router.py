"""IntentRouter 单元测试 — V0.1 八类意图。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.input_packet import parse_input
from core.intent_router import (
    INTENT_AUDIT,
    INTENT_CHAT,
    INTENT_CODE,
    INTENT_CONTENT,
    INTENT_CONTINUE,
    INTENT_FOLLOW_UP,
    INTENT_MEMORY,
    INTENT_SEARCH,
    route_intent,
)


class TestIntentRouter(unittest.TestCase):
    def test_question_mark_follow_up(self):
        intent = route_intent(parse_input("？"))
        self.assertEqual(intent.intent, INTENT_FOLLOW_UP)

    def test_continue_with_context(self):
        intent = route_intent(parse_input("继续"), has_active_context=True, last_intent="code_task")
        self.assertEqual(intent.intent, INTENT_CONTINUE)
        self.assertFalse(intent.needs_clarification)

    def test_continue_without_context(self):
        intent = route_intent(parse_input("继续"), has_active_context=False)
        self.assertEqual(intent.intent, INTENT_CONTINUE)
        self.assertTrue(intent.needs_clarification)

    def test_search_intent(self):
        intent = route_intent(parse_input("搜索: BTC 行情"))
        self.assertEqual(intent.intent, INTENT_SEARCH)
        self.assertEqual(intent.slots.get("query"), "BTC 行情")

    def test_content_display(self):
        intent = route_intent(parse_input("看内容"))
        self.assertEqual(intent.intent, INTENT_CONTENT)

    def test_code_task(self):
        intent = route_intent(parse_input("帮我改代码"))
        self.assertEqual(intent.intent, INTENT_CODE)

    def test_audit_task(self):
        intent = route_intent(parse_input("审一下"))
        self.assertEqual(intent.intent, INTENT_AUDIT)

    def test_memory_remember(self):
        intent = route_intent(parse_input("记住：明天开会"))
        self.assertEqual(intent.intent, INTENT_MEMORY)
        self.assertEqual(intent.slots.get("operation"), "remember")

    def test_memory_forget(self):
        intent = route_intent(parse_input("忘掉刚才那条"))
        self.assertEqual(intent.intent, INTENT_MEMORY)
        self.assertEqual(intent.slots.get("operation"), "forget")

    def test_chat_default(self):
        intent = route_intent(parse_input("今天天气不错"))
        self.assertEqual(intent.intent, INTENT_CHAT)


if __name__ == "__main__":
    unittest.main()
