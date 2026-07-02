#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古 v0.11.0 "索引" — 全面测试

新增测试覆盖：
  - KB 谓词索引 / 事实索引
  - 一致性检查缓存（脏标记）
  - Arbiter 历史学习版 select_methods
  - MCPBridge generate_token / revoke_token / list_callers
  - 无重复 restore_superseded 处理器
"""

import unittest
import tempfile
import shutil
import os
import time
from io import StringIO
from contextlib import redirect_stdout

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "pangu_v011",
    os.path.join(os.path.dirname(__file__), "pangu_v0.11.0.py")
)
_pangu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pangu)

Term = _pangu.Term
Rule = _pangu.Rule
unify = _pangu.unify
substitute = _pangu.substitute
KB = _pangu.KB
ConsistencyChecker = _pangu.ConsistencyChecker
ReasoningMethod = _pangu.ReasoningMethod
CognitiveEngine = _pangu.CognitiveEngine
Arbiter = _pangu.Arbiter
PersistentMemory = _pangu.PersistentMemory
DreamEngine = _pangu.DreamEngine
AutoSkillLearner = _pangu.AutoSkillLearner
KnowledgeGraph = _pangu.KnowledgeGraph
RealitySupervisor = _pangu.RealitySupervisor
MCPBridge = _pangu.MCPBridge
BoneGuard = _pangu.BoneGuard
NLMatcher = _pangu.NLMatcher
SuperBrainAgent = _pangu.SuperBrainAgent
parse_term = _pangu.parse_term
parse_rule_from_string = _pangu.parse_rule_from_string


# ============================================================
# 继承 v0.10.0 全部核心测试（仍需通过）
# ============================================================

class TestCore(unittest.TestCase):
    def test_term(self):
        t = Term("test", (1, "a"))
        self.assertEqual(t.name, "test")

    def test_unify(self):
        self.assertEqual(unify("_X", 5, {}), {"_X": 5})

    def test_substitute(self):
        self.assertEqual(substitute("_X", {"_X": 5}), 5)

    def test_parse_term(self):
        self.assertEqual(parse_term("f(a,b)"), Term("f", ("a", "b")))

    def test_parse_rule(self):
        r = parse_rule_from_string("a(_X) :- b(_X)")
        self.assertEqual(r.head.name, "a")


class TestKBIndexing(unittest.TestCase):
    """v0.11.0 新增：KB谓词/事实索引测试"""

    def setUp(self):
        self.kb = KB()
        self.kb.add_fact(Term("p", ("a", "b")))
        self.kb.add_fact(Term("p", ("b", "c")))
        self.kb.add_fact(Term("q", ("x", "y")))
        self.kb.add_rule(Rule(Term("gp", ("_X", "_Z")),
                              [Term("p", ("_X", "_Y")), Term("p", ("_Y", "_Z"))]))

    def test_fact_index_populated(self):
        """add_fact 后 fact_index 应有正确条目"""
        self.assertIn("p", self.kb.fact_index)
        self.assertEqual(len(self.kb.fact_index["p"]), 2)
        self.assertIn("q", self.kb.fact_index)
        self.assertEqual(len(self.kb.fact_index["q"]), 1)

    def test_predicate_index_populated(self):
        """add_rule 后 predicate_index 应有正确条目"""
        self.assertIn("gp", self.kb.predicate_index)
        self.assertEqual(len(self.kb.predicate_index["gp"]), 1)

    def test_query_uses_index(self):
        """索引不影响查询结果"""
        b = self.kb.query_best(Term("gp", ("a", "_Z")))
        self.assertIsNotNone(b)
        self.assertEqual(b["_Z"], "c")

    def test_index_updated_after_add(self):
        """新增事实后索引实时更新"""
        self.kb.add_fact(Term("p", ("c", "d")))
        self.assertEqual(len(self.kb.fact_index["p"]), 3)

    def test_index_not_polluted_by_unknown_pred(self):
        """未知谓词不应在索引中产生错误结果"""
        b = self.kb.query_best(Term("nonexistent", ("a",)))
        self.assertIsNone(b)

    def test_copy_rebuilds_index(self):
        """_copy() 应重建索引"""
        copy = self.kb._copy()
        self.assertIn("p", copy.fact_index)
        self.assertEqual(len(copy.fact_index["p"]), len(self.kb.fact_index["p"]))
        self.assertIn("gp", copy.predicate_index)


class TestConsistencyCache(unittest.TestCase):
    """v0.11.0 新增：一致性检查缓存测试"""

    def setUp(self):
        self.kb = KB()
        self.kb.add_fact(Term("p", ("a", "b")))
        self.kb.add_rule(Rule(Term("gp", ("_X", "_Z")),
                              [Term("p", ("_X", "_Y")), Term("p", ("_Y", "_Z"))]))

    def test_cache_starts_dirty(self):
        self.assertTrue(self.kb._cache_dirty)

    def test_cache_populated_after_check(self):
        report = self.kb.get_consistency_report()
        self.assertFalse(self.kb._cache_dirty)
        self.assertIsNotNone(self.kb._consistency_cache)

    def test_cache_hit_returns_same_object(self):
        r1 = self.kb.get_consistency_report()
        r2 = self.kb.get_consistency_report()
        self.assertIs(r1, r2)  # same cached object

    def test_cache_invalidated_on_add_fact(self):
        self.kb.get_consistency_report()  # prime cache
        self.kb.add_fact(Term("p", ("b", "c")))
        self.assertTrue(self.kb._cache_dirty)

    def test_cache_invalidated_on_add_rule(self):
        self.kb.get_consistency_report()  # prime cache
        self.kb.add_rule(
            Rule(Term("ancestor", ("_X", "_Y")), [Term("p", ("_X", "_Y"))]),
            force=True
        )
        self.assertTrue(self.kb._cache_dirty)

    def test_report_content_correct(self):
        report = self.kb.get_consistency_report()
        self.assertEqual(report.total_facts, 1)
        self.assertEqual(report.total_rules, 1)


class TestArbiterHistoryLearning(unittest.TestCase):
    """v0.11.0 修复：Arbiter 使用历史学习版 select_methods"""

    def setUp(self):
        self.kb = KB()
        self.kb.add_fact(Term("p", ("a", "b")))
        self.tmpdir = tempfile.mkdtemp()
        self.arbiter = Arbiter(self.kb, self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_select_methods_returns_list(self):
        methods = self.arbiter.select_methods(Term("p", ("a", "_Z")))
        self.assertIsInstance(methods, list)
        self.assertTrue(len(methods) > 0)

    def test_history_is_used(self):
        """记录负反馈后，被降权方法仍在候选集中但排在后面"""
        goal = Term("p", ("a", "_Z"))
        methods_before = self.arbiter.select_methods(goal)
        # 对 COT 记录 20 次负反馈
        for _ in range(20):
            self.arbiter.record_feedback("cot", "factual", False)
        methods_after = self.arbiter.select_methods(goal)
        # COT 仍在候选集（降权不删除）
        cot_values = [m.value for m in methods_after]
        self.assertIn("cot", cot_values)
        # COT 应排在后面（非第一位）
        if len(methods_after) > 1:
            self.assertNotEqual(methods_after[0].value, "cot")

    def test_record_positive_feedback(self):
        self.arbiter.record_feedback("cot", "factual", True)
        key = "(cot,factual)"
        self.assertIn(key, self.arbiter.history)
        self.assertEqual(self.arbiter.history[key], [1])

    def test_reset_stats(self):
        self.arbiter.record_feedback("cot", "factual", True)
        self.arbiter.reset_stats()
        self.assertEqual(len(self.arbiter.history), 0)


class TestMCPTokenManagement(unittest.TestCase):
    """v0.11.0 新增：MCPBridge token管理"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agent = SuperBrainAgent(memory_dir=self.tmpdir)
        self.bridge = self.agent.mcp

    def tearDown(self):
        self.agent.dream.stop()
        shutil.rmtree(self.tmpdir)

    def test_generate_token(self):
        token = self.bridge.generate_token("TestCaller", "readonly")
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_token_adds_to_trusted(self):
        self.bridge.generate_token("NewCaller", "readonly")
        self.assertIn("NewCaller", self.bridge.trusted_callers)

    def test_revoke_token(self):
        self.bridge.generate_token("TempCaller", "readonly")
        result = self.bridge.revoke_token("TempCaller")
        self.assertTrue(result)
        self.assertNotIn("TempCaller", self.bridge.trusted_callers)

    def test_revoke_nonexistent_returns_false(self):
        result = self.bridge.revoke_token("NotRegistered")
        self.assertFalse(result)

    def test_list_callers_empty_initially(self):
        callers = self.bridge.list_callers()
        self.assertIsInstance(callers, list)

    def test_list_callers_after_add(self):
        self.bridge.generate_token("ListCaller", "learn")
        callers = self.bridge.list_callers()
        names = [c["name"] for c in callers]
        self.assertIn("ListCaller", names)

    def test_revoked_caller_not_in_list(self):
        self.bridge.generate_token("ToRevoke", "readonly")
        self.bridge.revoke_token("ToRevoke")
        callers = self.bridge.list_callers()
        names = [c["name"] for c in callers]
        self.assertNotIn("ToRevoke", names)

    def test_mcp_add_then_call(self):
        """通过 perceive() 命令注册调用者，再以其身份调用"""
        with redirect_stdout(StringIO()):
            self.agent.run("mcp_add ExternalBot readonly")
        r = self.bridge.process_request({"method": "health", "caller_id": "ExternalBot"})
        self.assertIn("rules", r)


class TestNoDuplicateRestoreSuperseded(unittest.TestCase):
    """v0.11.0 修复：restore_superseded 无重复处理器"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agent = SuperBrainAgent(memory_dir=self.tmpdir)

    def tearDown(self):
        self.agent.dream.stop()
        shutil.rmtree(self.tmpdir)

    def test_restore_superseded_no_args(self):
        """无参数时列出被替代规则，不重复打印"""
        out = StringIO()
        with redirect_stdout(out):
            self.agent.run("restore_superseded")
        output = out.getvalue()
        # 不应出现两次同样的输出（重复处理器会打印两次）
        self.assertLessEqual(output.count("被替代的规则"), 1)
        self.assertLessEqual(output.count("无被替代的规则"), 1)


class TestKBQueryWithDynamic(unittest.TestCase):
    """索引化 _backtrack 仍支持 dynamic facts"""

    def setUp(self):
        self.kb = KB()
        self.kb.add_fact(Term("p", ("a", "b")))
        self.kb.add_rule(Rule(Term("gp", ("_X", "_Z")),
                              [Term("p", ("_X", "_Y")), Term("p", ("_Y", "_Z"))]))

    def test_dynamic_facts_still_work(self):
        dynamic = [Term("p", ("b", "c"))]
        b = self.kb.query_best(Term("gp", ("a", "_Z")), dynamic=dynamic)
        self.assertIsNotNone(b)
        self.assertEqual(b["_Z"], "c")


class TestAll16Methods(unittest.TestCase):
    def test_16_methods_defined(self):
        self.assertEqual(len(ReasoningMethod), 16)


class TestSuperBrainAgent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agent = SuperBrainAgent(memory_dir=self.tmpdir)

    def tearDown(self):
        self.agent.dream.stop()
        shutil.rmtree(self.tmpdir)

    def test_health_report(self):
        out = StringIO()
        with redirect_stdout(out):
            self.agent.run("检查一致性")
        self.assertIn("健康报告", out.getvalue())

    def test_remember(self):
        out = StringIO()
        with redirect_stdout(out):
            self.agent.run("记住 测试(abc)")
        self.assertIn("已存储", out.getvalue())

    def test_mcp_health(self):
        r = self.agent.process_mcp({"method": "health", "caller_id": "SanLife"})
        self.assertIn("rules", r)

    def test_bone_guard_blocks_violation(self):
        out = StringIO()
        with redirect_stdout(out):
            self.agent.run("放弃身份")
        self.assertIn("拒绝", out.getvalue())

    def test_learn_rule(self):
        out = StringIO()
        with redirect_stdout(out):
            self.agent.run("学习规则 cousin(_X, _Y) :- parent(_Z, _X), parent(_Z, _Y).")
        self.assertIn("已学习规则", out.getvalue())

    def test_version_string(self):
        """版本号应为 0.11.0"""
        identity = self.agent.memory.get_identity()
        self.assertEqual(identity["version"], "0.11.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
