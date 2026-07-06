"""回测摩擦成本单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chanlun.backtest import run_chanlun_backtest
from chanlun.sample import sample_bars


class TestFriction(unittest.TestCase):
    def test_friction_reduces_return(self):
        bars = sample_bars()
        gross = run_chanlun_backtest(bars, {"commission": 0, "slippage": 0, "initial_capital": 1.0})
        net = run_chanlun_backtest(
            bars,
            {"commission": 0.0005, "slippage": 0.0001, "initial_capital": 1.0},
        )
        g = gross["metrics"]["total_return"]
        n = net["metrics"]["total_return"]
        self.assertGreaterEqual(g, n)
        self.assertGreater(net["metrics"]["total_commission"], 0)
        self.assertGreater(net["metrics"]["friction_drag"], 0)


if __name__ == "__main__":
    unittest.main()
