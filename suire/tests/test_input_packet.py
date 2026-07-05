"""InputPacket 单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.input_packet import parse_input


class TestInputPacket(unittest.TestCase):
    def test_question_only(self):
        p = parse_input("？")
        self.assertTrue(p.is_question_only)
        self.assertFalse(p.is_continue)

    def test_continue(self):
        p = parse_input("继续")
        self.assertTrue(p.is_continue)

    def test_search_prefix(self):
        p = parse_input("搜索: 燧人架构")
        self.assertTrue(p.is_search_prefixed)
        self.assertEqual(p.search_query, "燧人架构")

    def test_hints(self):
        self.assertIn("code", parse_input("帮我改代码").hints)
        self.assertIn("audit", parse_input("审一下").hints)
        self.assertIn("content", parse_input("看内容").hints)
        self.assertIn("memory", parse_input("记住这个").hints)


if __name__ == "__main__":
    unittest.main()
