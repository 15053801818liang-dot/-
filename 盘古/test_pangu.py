#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古 v0.9.0 单元测试
覆盖：Term 基本操作、unify/substitute、KB 查询、一致性检查、规则学习、骨骼守护
"""

import unittest
import sys
from io import StringIO
from contextlib import redirect_stdout

import importlib.util
import os
_spec = importlib.util.spec_from_file_location("pangu", os.path.join(os.path.dirname(__file__), "pangu_v0.9.0.py"))
_pangu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pangu)

Term = _pangu.Term
Rule = _pangu.Rule
unify = _pangu.unify
substitute = _pangu.substitute
KB = _pangu.KB
ConsistencyChecker = _pangu.ConsistencyChecker
HealthReport = _pangu.HealthReport
SessionMemory = _pangu.SessionMemory
NLMatcher = _pangu.NLMatcher
BoneGuard = _pangu.BoneGuard
SelfReflection = _pangu.SelfReflection
parse_term = _pangu.parse_term
parse_rule_from_string = _pangu.parse_rule_from_string
SuperBrainAgent = _pangu.SuperBrainAgent


class TestTerm(unittest.TestCase):
    def test_term_creation(self):
        t = Term("father", ("张三", "张父"))
        self.assertEqual(t.name, "father")
        self.assertEqual(t.args, ("张三", "张父"))
        self.assertIn("father", repr(t))

    def test_term_eq(self):
        t1 = Term("parent", ("a", "b"))
        t2 = Term("parent", ("a", "b"))
        t3 = Term("parent", ("a", "c"))
        self.assertEqual(t1, t2)
        self.assertNotEqual(t1, t3)


class TestUnify(unittest.TestCase):
    def test_unify_const_const(self):
        self.assertEqual(unify(1, 1, {}), {})
        with self.assertRaises(Exception):
            unify(1, 2, {})

    def test_unify_var_const(self):
        self.assertEqual(unify("_X", 5, {}), {"_X": 5})

    def test_unify_var_var(self):
        result = unify("_X", "_Y", {})
        result2 = unify("_X", 10, result)
        self.assertEqual(result2, {"_X": "_Y", "_Y": 10})

    def test_unify_term(self):
        t1 = Term("parent", ("_X", "b"))
        t2 = Term("parent", ("a", "_Y"))
        result = unify(t1, t2, {})
        self.assertEqual(result, {"_X": "a", "_Y": "b"})


class TestSubstitute(unittest.TestCase):
    def test_substitute_var(self):
        self.assertEqual(substitute("_X", {"_X": 5}), 5)
        self.assertEqual(substitute("_Y", {"_X": 5}), "_Y")

    def test_substitute_term(self):
        t = Term("parent", ("_X", "b"))
        result = substitute(t, {"_X": "a"})
        self.assertEqual(result, Term("parent", ("a", "b")))


class TestKB(unittest.TestCase):
    def setUp(self):
        self.kb = KB()
        self.kb.add_fact(Term("parent", ("a", "b")))
        self.kb.add_fact(Term("parent", ("b", "c")))
        self.kb.add_rule(Rule(Term("grandparent", ("_X", "_Z")),
                              [Term("parent", ("_X", "_Y")), Term("parent", ("_Y", "_Z"))]))

    def test_query_best_simple(self):
        goal = Term("grandparent", ("a", "_Z"))
        binding = self.kb.query_best(goal)
        self.assertIsNotNone(binding)
        self.assertEqual(binding["_Z"], "c")

    def test_query_best_with_trace(self):
        goal = Term("grandparent", ("a", "_Z"))
        binding, trace = self.kb.query_best_with_trace(goal)
        self.assertIsNotNone(binding)
        self.assertIsNotNone(trace)
        self.assertEqual(binding["_Z"], "c")

    def test_consistency_checker(self):
        checker = ConsistencyChecker(self.kb)
        report = checker.check()
        self.assertEqual(report.total_rules, 1)
        self.assertEqual(report.total_facts, 2)
        self.assertEqual(len(report.orphans), 0)
        self.assertEqual(len(report.cycles), 0)

    def test_arity_mismatch_rejection(self):
        bad_rule = Rule(Term("parent", ("_X",)), [Term("parent", ("_X", "_Y"))])
        with self.assertRaises(ValueError) as ctx:
            self.kb.add_rule(bad_rule)
        self.assertIn("元数不一致", str(ctx.exception))

    def test_undefined_pred_rejection(self):
        bad_rule = Rule(Term("new_pred", ("_X",)), [Term("undefined_pred", ("_X",))])
        with self.assertRaises(ValueError) as ctx:
            self.kb.add_rule(bad_rule)
        self.assertIn("未定义谓词", str(ctx.exception))

    def test_force_add_undefined(self):
        # force=True 应允许添加并标记不可靠
        bad_rule = Rule(Term("new_pred", ("_X",)), [Term("undefined_pred", ("_X",))])
        self.kb.add_rule(bad_rule, force=True)
        self.assertFalse(bad_rule.reliable)
        self.assertIn("强制添加", bad_rule.warning)


class TestSessionMemory(unittest.TestCase):
    def test_fifo(self):
        mem = SessionMemory(max_size=2)
        mem.add_fact(Term("f1", (1,)))
        mem.add_fact(Term("f2", (2,)))
        mem.add_fact(Term("f3", (3,)))
        self.assertEqual(len(mem.recall()), 2)


class TestBoneGuard(unittest.TestCase):
    def test_identity(self):
        guard = BoneGuard()
        self.assertTrue(guard.check("普通问题"))
        self.assertFalse(guard.check("放弃身份"))


class TestParseTerm(unittest.TestCase):
    def test_parse(self):
        t = parse_term("father(张三, 李四)")
        self.assertEqual(t, Term("father", ("张三", "李四")))

    def test_parse_var(self):
        t = parse_term("father(_X, _Y)")
        self.assertEqual(t, Term("father", ("_X", "_Y")))

    def test_parse_constant_no_parens(self):
        t = parse_term("张三")
        self.assertEqual(t, Term("张三"))


class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.agent = SuperBrainAgent(rules_dir="nonexist")

    def test_consistency_command(self):
        with redirect_stdout(StringIO()) as out:
            self.agent.run("检查一致性")
        output = out.getvalue()
        self.assertIn("健康报告", output)


if __name__ == "__main__":
    unittest.main()
