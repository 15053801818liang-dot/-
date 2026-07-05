"""Windows IPC 队列冒烟测试（非 Windows 自动 skip）。"""

import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class TestQueueBridge(unittest.TestCase):
    def setUp(self) -> None:
        from queue_bridge import QueueBridge

        self.bridge = QueueBridge("queue_core.dll")
        self.assertTrue(self.bridge.init())

    def tearDown(self) -> None:
        self.bridge.cleanup()

    def test_push_pop(self) -> None:
        self.assertEqual(self.bridge.push(b"Hello, Pangu!"), 0)
        code, data = self.bridge.pop()
        self.assertEqual(code, 0)
        self.assertEqual(data, b"Hello, Pangu!")

    def test_empty_pop(self) -> None:
        code, _ = self.bridge.pop()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
