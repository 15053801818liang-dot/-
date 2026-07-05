"""SuperBrain 桥接单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from superbrain_bridge import SuperBrainBridge


# 两规则同优先级 (requires_any, conf=0.78) → 必须走 Arbiter
ARBITER_TIE_STRUCTURE = {
    "recent_strokes": [{"index": 10, "direction": "up", "end_price": 100.0, "amplitude": 1.0}],
    "active_pivots": [],
    "last_divergence": {"kind": "top", "bar_index": 99, "price": 101.0, "reason": "顶背驰"},
    "trade_points": [
        {"kind": "buy1", "bar_index": 99, "price": 101.0, "reason": "底背驰"},
    ],
    "last_stroke": {"index": 10, "direction": "up", "end_price": 100.0},
    "last_close": 100.0,
    "total_strokes": 11,
    "current_stroke_index": 10,
}


class TestSuperBrainBridge(unittest.TestCase):
    def test_arbiter_resolves_multi_match(self):
        bridge = SuperBrainBridge()
        out = bridge.deduce(ARBITER_TIE_STRUCTURE)
        self.assertIn(out["state_code"], {"TOP_DIVERGENCE_ZONE", "BOTTOM_DIVERGENCE_ZONE"})
        self.assertTrue(out.get("arbiter_used"))
        self.assertTrue(any("ARBITER" in s for s in out["deduction_path"]))
        self.assertGreaterEqual(len(out.get("candidate_rules") or []), 2)

    def test_single_match_skips_arbiter(self):
        structure = {
            "recent_strokes": [{"index": 5, "direction": "up", "end_price": 100.0, "amplitude": 1.0}],
            "active_pivots": [{"zg": 105.0, "zd": 95.0, "mid": 100.0, "start_index": 2, "end_index": 4}],
            "trade_points": [],
            "last_stroke": {"index": 5, "direction": "up", "end_price": 100.0},
            "last_close": 100.0,
            "total_strokes": 6,
            "current_stroke_index": 5,
        }
        out = SuperBrainBridge().deduce(structure)
        self.assertEqual(out["state_code"], "OSC_NEUTRAL")
        self.assertFalse(out.get("arbiter_used"))


if __name__ == "__main__":
    unittest.main()
