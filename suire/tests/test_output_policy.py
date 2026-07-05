"""OutputPolicy 单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.input_packet import parse_input
from core.intent_router import route_intent
from core.output_policy import apply_output_policy, derive_output_policy


class TestOutputPolicy(unittest.TestCase):
    def test_follow_up_no_search_brief(self):
        intent = route_intent(parse_input("？"), has_active_context=True)
        policy = derive_output_policy(intent)
        self.assertFalse(policy.allow_search)
        self.assertTrue(policy.require_brief)
        self.assertLessEqual(policy.max_chars, 120)

    def test_question_mark_not_long_form(self):
        intent = route_intent(parse_input("？？"))
        policy = derive_output_policy(intent)
        long_text = "。".join(["这是一段很长的废话"] * 20)
        out = apply_output_policy(long_text, policy)
        self.assertLessEqual(len(out), policy.max_chars)

    def test_search_uses_tool_layer_flag(self):
        intent = route_intent(parse_input("搜索: test"))
        policy = derive_output_policy(intent)
        self.assertTrue(policy.allow_search)
        self.assertTrue(policy.allow_tool_fetch)
        self.assertIn("工具", policy.note)

    def test_chat_short_question_brief(self):
        intent = route_intent(parse_input("你好"))
        policy = derive_output_policy(intent)
        self.assertTrue(policy.require_brief)
        self.assertEqual(policy.mode, "chat_brief")

    def test_continue_no_context_clarify(self):
        intent = route_intent(parse_input("继续"), has_active_context=False)
        policy = derive_output_policy(intent)
        self.assertTrue(policy.clarification_only)


if __name__ == "__main__":
    unittest.main()
