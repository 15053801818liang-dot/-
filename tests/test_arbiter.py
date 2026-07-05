"""市场状态裁决器 (pangu.arbiter.Arbiter) 单元测试。

封口条件对应用例：
    test_high_risk_prevails
    test_conflict_triggers_defense
    test_empty_rules
    test_threshold_equal_triggers_defense
    test_unknown_rule_is_reported

运行：
    python -m unittest tests/test_arbiter.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pangu.arbiter import Arbiter  # noqa: E402


class TestArbiter(unittest.TestCase):
    # ---- 封口必测项 ------------------------------------------------

    def test_high_risk_prevails(self):
        rules = [
            {"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"},
            {"state_code": "TREND_BULL_LEAVE_PIVOT", "interpretation": "bull pivot"},
        ]
        arbiter = Arbiter()  # 默认 HIGH_RISK_EXIT=100, TREND_BULL_LEAVE_PIVOT=80
        result = arbiter.reason(rules)
        # 权重差为20（100-80），超过阈值10，不触发防御
        self.assertEqual(result["state_code"], "HIGH_RISK_EXIT")
        self.assertEqual(result["selected_rule"], "HIGH_RISK_EXIT")
        self.assertEqual(result["conflict_sources"], [])

    def test_conflict_triggers_defense(self):
        rules = [
            {"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"},
            {"state_code": "BUY_DIVERGENCE_CONFIRM", "interpretation": "buy div"},
        ]
        # 收窄权重差至阈值以内 → 触发防御。
        arbiter = Arbiter(
            weights={
                "HIGH_RISK_EXIT": 100,
                "BUY_DIVERGENCE_CONFIRM": 95,
                "OSC_NEUTRAL": 10,
            },
            defense_threshold=10,
        )
        result = arbiter.reason(rules)
        self.assertEqual(result["state_code"], "OSC_NEUTRAL")
        self.assertIsNone(result["selected_rule"])
        self.assertIn("HIGH_RISK_EXIT", result["conflict_sources"])
        self.assertIn("BUY_DIVERGENCE_CONFIRM", result["conflict_sources"])

    def test_empty_rules(self):
        arbiter = Arbiter()
        result = arbiter.reason([])
        self.assertEqual(result["state_code"], "NONE")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["unknown_rules"], [])

    def test_threshold_equal_triggers_defense(self):
        rules = [
            {"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"},
            {"state_code": "TREND_BULL_LEAVE_PIVOT", "interpretation": "bull pivot"},
        ]
        arbiter = Arbiter(
            weights={
                "HIGH_RISK_EXIT": 100,
                "TREND_BULL_LEAVE_PIVOT": 90,
                "OSC_NEUTRAL": 10,
            },
            defense_threshold=10,
        )
        # 权重差为10（100-90），等于阈值10 → 触发防御（<= 语义）
        result = arbiter.reason(rules)
        self.assertEqual(result["state_code"], "OSC_NEUTRAL")

    def test_unknown_rule_is_reported(self):
        rules = [
            {"state_code": "UNKNOWN_SIGNAL", "interpretation": "unknown"},
            {"state_code": "OSC_NEUTRAL", "interpretation": "neutral"},
        ]
        arbiter = Arbiter()
        result = arbiter.reason(rules)
        self.assertIn("UNKNOWN_SIGNAL", result["unknown_rules"])

    # ---- 结构稳定性 / schema 加固 ----------------------------------

    def test_winner_schema_is_stable(self):
        """winner 始终带 confidence 等统一字段，避免下游取到 None。"""
        rules = [{"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"}]
        result = Arbiter().reason(rules)
        for key in (
            "interpretation",
            "state_code",
            "confidence",
            "selected_rule",
            "conflict_sources",
            "unknown_rules",
        ):
            self.assertIn(key, result)
        self.assertIsInstance(result["confidence"], float)

    def test_none_input_is_hardened(self):
        """None / 脏输入不炸裁决层。"""
        self.assertEqual(Arbiter().reason(None)["state_code"], "NONE")

    def test_non_dict_candidates_dropped(self):
        rules = [
            "not-a-dict",
            {"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"},
            42,
        ]
        result = Arbiter().reason(rules)
        self.assertEqual(result["state_code"], "HIGH_RISK_EXIT")

    def test_single_winner_confidence_override(self):
        rules = [{"state_code": "HIGH_RISK_EXIT", "confidence": 0.87}]
        result = Arbiter().reason(rules)
        self.assertEqual(result["confidence"], 0.87)

    # ---- Fact 注入桥 (→ KB / SuperBrainAgent) ----------------------

    def test_inject_fact_into_kb(self):
        """裁决结果可注入鸭子类型 KB（对齐 KB.add_fact(Term(name, args)))。"""

        class FakeTerm:
            def __init__(self, name, args):
                self.name = name
                self.args = args

        class FakeKB:
            def __init__(self):
                self.facts = []

            def add_fact(self, fact):
                self.facts.append(fact)

        kb = FakeKB()
        arbiter = Arbiter()
        decision, fact = arbiter.arbitrate_and_inject(
            [{"state_code": "HIGH_RISK_EXIT", "interpretation": "risk exit"}],
            kb,
            FakeTerm,
        )
        self.assertEqual(len(kb.facts), 1)
        self.assertEqual(kb.facts[0].name, "market_state")
        self.assertEqual(kb.facts[0].args[0], "HIGH_RISK_EXIT")
        self.assertEqual(decision["state_code"], "HIGH_RISK_EXIT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
