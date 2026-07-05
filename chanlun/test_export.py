"""结构导出测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.analyzer import analyze
from chanlun.export import export_chanlun_structure
from chanlun.sample import sample_bars_pivot


class TestExportStructure(unittest.TestCase):
    def test_export_has_required_keys(self):
        result = analyze(sample_bars_pivot())
        detail = export_chanlun_structure(result)
        for key in (
            "recent_strokes",
            "active_pivots",
            "last_divergence",
            "trade_points",
            "current_stroke_index",
            "total_strokes",
        ):
            self.assertIn(key, detail)

    def test_stroke_to_dict_roundtrip_fields(self):
        result = analyze(sample_bars_pivot())
        detail = export_chanlun_structure(result, recent_strokes=3)
        self.assertGreater(len(detail["recent_strokes"]), 0)
        stroke = detail["recent_strokes"][-1]
        self.assertIn("direction", stroke)
        self.assertIn("start", stroke)
        self.assertIn("end", stroke)
        self.assertIn("index", stroke)

    def test_backtest_includes_structure_detail(self):
        from chanlun.backtest import run_chanlun_backtest
        from chanlun.sample import sample_bars_pivot

        bars = sample_bars_pivot()
        out = run_chanlun_backtest(bars, {"incremental": False})
        self.assertIn("structure_detail", out)
        self.assertIn("trade_points", out["structure_detail"])


if __name__ == "__main__":
    unittest.main()
