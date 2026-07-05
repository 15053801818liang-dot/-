"""盘古结构语义推理单元测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reasoner import PanguReasoner


SAMPLE_STRUCTURE = {
    "recent_strokes": [
        {
            "index": 14,
            "direction": "down",
            "end_price": 64850.0,
            "start_price": 65200.0,
        }
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
    "last_stroke": {"index": 14, "direction": "down", "end_price": 64850.0},
    "last_close": 64700.0,
}


class TestPanguReasoner(unittest.TestCase):
    def test_reason_from_chanlun_structure(self):
        out = PanguReasoner().reason_from_chanlun(SAMPLE_STRUCTURE)
        self.assertEqual(out["state_code"], "BUY_DIVERGENCE_CONFIRM")
        self.assertIn("第 15/15 笔", out["interpretation"])
        self.assertIn("ZG=65200", out["interpretation"])
        self.assertIn("buy1", out["interpretation"])
        self.assertGreater(out["confidence"], 0.8)
        self.assertIn("semantic_audit", out)

    def test_analyze_artifact_with_structure_detail(self):
        artifact = {
            "metrics": {"total_trades": 10, "sharpe": 1.0},
            "audit": {"analyze_mode": "incremental"},
            "structure_detail": SAMPLE_STRUCTURE,
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(artifact, f)
            path = f.name
        try:
            out = PanguReasoner().analyze(None, path)
            self.assertEqual(out["state_code"], "BUY_DIVERGENCE_CONFIRM")
            self.assertNotEqual(out["state_code"], "METRICS_ONLY")
        finally:
            os.unlink(path)

    def test_sell3_top_divergence_high_risk(self):
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


if __name__ == "__main__":
    unittest.main()
