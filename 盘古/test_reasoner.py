"""符号演绎与 SuperBrain 对接单元测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reasoner import PanguReasoner
from symbolic import SymbolicReasoningPipeline, structure_to_facts


SAMPLE_STRUCTURE = {
    "recent_strokes": [
        {"index": 12, "direction": "up", "end_price": 65200.0, "amplitude": 400.0},
        {"index": 13, "direction": "down", "end_price": 64850.0, "amplitude": 350.0},
        {"index": 14, "direction": "down", "end_price": 64700.0, "amplitude": 150.0},
    ],
    "active_pivots": [
        {"zg": 65200.0, "zd": 64800.0, "mid": 65000.0, "start_index": 8, "end_index": 12}
    ],
    "last_divergence": {
        "stroke_index": 14,
        "kind": "bottom",
        "bar_index": 980,
        "price": 64850.0,
        "reason": "底背驰",
    },
    "trade_points": [
        {
            "kind": "buy1",
            "bar_index": 980,
            "price": 64850.0,
            "reason": "底背驰",
        }
    ],
    "current_stroke_index": 14,
    "total_strokes": 15,
    "total_pivots": 2,
    "last_stroke": {"index": 14, "direction": "down", "end_price": 64700.0, "amplitude": 150.0},
    "last_close": 64700.0,
}


class TestSymbolicPipeline(unittest.TestCase):
    def test_structure_to_facts(self):
        facts, logic_kb = structure_to_facts(SAMPLE_STRUCTURE)
        self.assertGreater(len(facts), 0)
        self.assertIn("signal_buy1", logic_kb["tags"])
        self.assertIn("divergence_bottom", logic_kb["tags"])
        self.assertTrue(logic_kb["stroke_exhaustion"])

    def test_deduce_buy_divergence(self):
        out = SymbolicReasoningPipeline().deduce(SAMPLE_STRUCTURE)
        self.assertEqual(out["state_code"], "BUY_DIVERGENCE_CONFIRM")
        self.assertEqual(out["matched_rule"], "buy_divergence_confirm")
        self.assertGreater(len(out["deduction_path"]), 2)
        self.assertIn("buy1", out["interpretation"])

    def test_reasoner_symbolic_output(self):
        out = PanguReasoner().reason_from_chanlun(SAMPLE_STRUCTURE)
        self.assertIn("deduction_path", out)
        self.assertIn("matched_rule", out)
        self.assertEqual(out["state_code"], "BUY_DIVERGENCE_CONFIRM")

    def test_high_risk_exit_rule(self):
        structure = dict(SAMPLE_STRUCTURE)
        structure["trade_points"] = [
            {
                "kind": "sell3",
                "bar_index": 100,
                "price": 64000.0,
                "reason": "下跌离开中枢后反抽不回中枢",
            }
        ]
        structure["last_divergence"] = {
            "kind": "top",
            "reason": "顶背驰",
            "bar_index": 99,
            "price": 65100.0,
        }
        out = PanguReasoner().reason_from_chanlun(structure)
        self.assertEqual(out["state_code"], "HIGH_RISK_EXIT")
        self.assertEqual(out["matched_rule"], "high_risk_exit")

    def test_analyze_artifact_with_structure_detail(self):
        artifact = {
            "metrics": {"total_trades": 10},
            "audit": {"analyze_mode": "incremental"},
            "structure_detail": SAMPLE_STRUCTURE,
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(artifact, f)
            path = f.name
        try:
            out = PanguReasoner().analyze(None, path)
            self.assertEqual(out["state_code"], "BUY_DIVERGENCE_CONFIRM")
            self.assertTrue(out["deduction_path"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
