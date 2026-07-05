"""增量分析一致性测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.incremental import analyze_incremental, verify_incremental_matches
from chanlun.sample import sample_bars, sample_bars_pivot, synth_bars


class TestIncremental(unittest.TestCase):
    def test_matches_full_on_samples(self):
        self.assertTrue(verify_incremental_matches(sample_bars()))
        self.assertTrue(verify_incremental_matches(sample_bars_pivot()))

    def test_larger_synthetic(self):
        bars = synth_bars([100, 105, 98, 110, 95, 108, 90, 100], seg_len=4)
        self.assertTrue(verify_incremental_matches(bars))

    def test_incremental_produces_strokes(self):
        r = analyze_incremental(sample_bars())
        self.assertGreater(len(r.strokes), 0)
        self.assertGreater(len(r.trade_points), 0)


if __name__ == "__main__":
    unittest.main()
