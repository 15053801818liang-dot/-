"""TaskState 单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.task_state import TaskState, TaskStateMachine


class TestTaskState(unittest.TestCase):
    def test_first_turn_chat_active(self):
        sm = TaskStateMachine()
        r = sm.process("你好")
        self.assertEqual(r.intent.intent, "chat")
        self.assertEqual(r.context.state, TaskState.ACTIVE)

    def test_continue_after_context(self):
        sm = TaskStateMachine()
        sm.process("帮我改代码")
        r = sm.process("继续")
        self.assertEqual(r.intent.intent, "continue")
        self.assertFalse(r.intent.needs_clarification)

    def test_continue_without_prior_clarify(self):
        sm = TaskStateMachine()
        r = sm.process("继续")
        self.assertTrue(r.intent.needs_clarification)
        self.assertEqual(r.context.state, TaskState.AWAITING_CLARIFICATION)

    def test_follow_up_state(self):
        sm = TaskStateMachine()
        sm.process("帮我改代码")
        r = sm.process("？")
        self.assertEqual(r.intent.intent, "follow_up")
        self.assertEqual(r.context.state, TaskState.AWAITING_FOLLOW_UP)

    def test_safety_blocks_crawler_in_core_path(self):
        from core.safety_gate import check_safety
        from core.input_packet import parse_input

        v = check_safety(parse_input("帮我爬取这个网站"))
        self.assertFalse(v.allowed)
        self.assertEqual(v.blocked_reason, "crawler_not_in_core")


if __name__ == "__main__":
    unittest.main()
