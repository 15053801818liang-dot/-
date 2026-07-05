"""盘古回测推理单元测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reasoner import PanguReasoner


class TestPanguReasoner(unittest.TestCase):
    def test_analyze_chanlun_artifact(self):
        sample = {
            "metrics": {
                "total_return": 0.12,
                "total_return_gross": 0.25,
                "sharpe": 1.2,
                "max_drawdown": -0.08,
                "win_rate": 0.58,
                "total_trades": 42,
                "strokes_count": 120,
                "friction_drag": 0.13,
            },
            "audit": {"analyze_mode": "incremental", "bars": 10000},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample, f)
            path = f.name
        try:
            out = PanguReasoner().analyze(None, path)
            self.assertIn("interpretation", out)
            self.assertIn(
                out["state_code"],
                {"TREND_BULL", "OSC_NEUTRAL", "UNCERTAIN", "FRICTION_HEAVY"},
            )
            self.assertGreater(out["confidence"], 0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
