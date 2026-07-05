"""符号演绎层单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from symbolic import load_symbolic_kb, structure_to_facts, SymbolicReasoningPipeline


class TestSymbolicKB(unittest.TestCase):
    def test_kb_loads(self):
        kb = load_symbolic_kb()
        self.assertGreaterEqual(len(kb.get("rules", [])), 5)

    def test_osc_neutral_inside_pivot(self):
        structure = {
            "recent_strokes": [{"index": 5, "direction": "up", "end_price": 100.0, "amplitude": 1.0}],
            "active_pivots": [{"zg": 105.0, "zd": 95.0, "mid": 100.0, "start_index": 2, "end_index": 4}],
            "trade_points": [],
            "last_stroke": {"index": 5, "direction": "up", "end_price": 100.0},
            "last_close": 100.0,
            "total_strokes": 6,
            "current_stroke_index": 5,
        }
        out = SymbolicReasoningPipeline().deduce(structure)
        self.assertEqual(out["state_code"], "OSC_NEUTRAL")


if __name__ == "__main__":
    unittest.main()
