#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古 v0.11.0 测试套件
测试 OpenClaw 配置体系 (ConfigLoader) 和 ds4 本地推理引擎接口 (LocalInferenceEngine)
"""

import sys
import os
import json
import tempfile
import shutil
import unittest

# ── 路径处理：支持从任意目录运行 ──────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("pangu_v0_11_0",
                                     os.path.join(_DIR, "pangu_v0.11.0.py"))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ConfigLoader = _mod.ConfigLoader
LocalInferenceEngine = _mod.LocalInferenceEngine
SuperBrainAgent = _mod.SuperBrainAgent
KB = _mod.KB
Term = _mod.Term
Rule = _mod.Rule
parse_term = _mod.parse_term
parse_rule_from_string = _mod.parse_rule_from_string


# ════════════════════════════════════════════════════════════════════════════
# 辅助：临时目录 mixin
# ════════════════════════════════════════════════════════════════════════════
class TempDirMixin:
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════════════
# 1. ConfigLoader 测试
# ════════════════════════════════════════════════════════════════════════════
class TestConfigLoaderDefaults(TempDirMixin, unittest.TestCase):
    """没有配置文件时，ConfigLoader 使用默认值。"""

    def setUp(self):
        super().setUp()
        self.cfg = ConfigLoader(self.tmpdir).load()

    def test_soul_defaults(self):
        self.assertEqual(self.cfg.get_identity_name(), "SanLife")
        self.assertEqual(self.cfg.soul["sovereignty"], "inviolable")

    def test_agents_defaults(self):
        self.assertTrue(self.cfg.module_enabled("dream_engine"))
        self.assertTrue(self.cfg.module_enabled("knowledge_graph"))

    def test_user_defaults(self):
        self.assertEqual(self.cfg.get_user_pref("language"), "auto")
        self.assertEqual(self.cfg.get_user_pref("memory_limit"), 1000)
        self.assertFalse(self.cfg.get_user_pref("show_think_log"))

    def test_no_files_loaded(self):
        self.assertEqual(self.cfg._loaded_files, [])


class TestConfigLoaderSoulFile(TempDirMixin, unittest.TestCase):
    """SOUL.md 加载与解析。"""

    def _write(self, content):
        with open(os.path.join(self.tmpdir, "SOUL.md"), "w", encoding="utf-8") as f:
            f.write(content)

    def test_custom_identity_name(self):
        self._write("## Identity\n- name: Athena\n- version: 1.0.0\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.get_identity_name(), "Athena")

    def test_custom_sovereignty(self):
        self._write("## Values\n- sovereignty: absolute\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.soul.get("sovereignty"), "absolute")

    def test_loaded_files_recorded(self):
        self._write("## Identity\n- name: X\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertIn("SOUL.md", cfg._loaded_files)

    def test_boolean_values(self):
        self._write("## Values\n- active: true\n- debug: false\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertTrue(cfg.soul.get("active"))
        self.assertFalse(cfg.soul.get("debug"))

    def test_integer_value(self):
        self._write("## Limits\n- max_depth: 42\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.soul.get("max_depth"), 42)

    def test_comments_ignored(self):
        self._write("# A comment\n## Identity\n- name: Zeus\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.get_identity_name(), "Zeus")


class TestConfigLoaderAgentsFile(TempDirMixin, unittest.TestCase):
    """AGENTS.md 加载与模块开关。"""

    def test_disable_dream_engine(self):
        with open(os.path.join(self.tmpdir, "AGENTS.md"), "w") as f:
            f.write("## Modules\n- dream_engine: false\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertFalse(cfg.module_enabled("dream_engine"))

    def test_module_missing_uses_default(self):
        with open(os.path.join(self.tmpdir, "AGENTS.md"), "w") as f:
            f.write("## Modules\n- arbiter: true\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertTrue(cfg.module_enabled("knowledge_graph"))  # default True


class TestConfigLoaderUserFile(TempDirMixin, unittest.TestCase):
    """USER.md 加载与用户偏好。"""

    def test_custom_language(self):
        with open(os.path.join(self.tmpdir, "USER.md"), "w") as f:
            f.write("## Preferences\n- language: zh\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.get_user_pref("language"), "zh")

    def test_custom_memory_limit(self):
        with open(os.path.join(self.tmpdir, "USER.md"), "w") as f:
            f.write("## Preferences\n- memory_limit: 500\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.get_user_pref("memory_limit"), 500)

    def test_show_think_log_true(self):
        with open(os.path.join(self.tmpdir, "USER.md"), "w") as f:
            f.write("## Preferences\n- show_think_log: true\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertTrue(cfg.get_user_pref("show_think_log"))

    def test_missing_key_uses_default(self):
        with open(os.path.join(self.tmpdir, "USER.md"), "w") as f:
            f.write("## Preferences\n- language: en\n")
        cfg = ConfigLoader(self.tmpdir).load()
        self.assertEqual(cfg.get_user_pref("max_search_results"), 5)


class TestConfigLoaderWriteDefaults(TempDirMixin, unittest.TestCase):
    """write_defaults 生成模板文件。"""

    def test_creates_all_three_files(self):
        cfg = ConfigLoader(self.tmpdir).load()
        cfg.write_defaults()
        for fname in ("SOUL.md", "AGENTS.md", "USER.md"):
            self.assertTrue(os.path.exists(os.path.join(self.tmpdir, fname)),
                            f"{fname} 应该被创建")

    def test_does_not_overwrite_existing(self):
        path = os.path.join(self.tmpdir, "SOUL.md")
        with open(path, "w") as f:
            f.write("## Identity\n- name: Custom\n")
        cfg = ConfigLoader(self.tmpdir).load()
        cfg.write_defaults()
        with open(path) as f:
            content = f.read()
        self.assertIn("Custom", content)


# ════════════════════════════════════════════════════════════════════════════
# 2. LocalInferenceEngine 测试
# ════════════════════════════════════════════════════════════════════════════
class LocalEngineBase(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.engine = LocalInferenceEngine(
            config_dir=self.tmpdir,
            memory_dir=self.tmpdir,
            enable_dream=False,
        )

    def tearDown(self):
        self.engine.stop()
        super().tearDown()


class TestLocalEngineBasic(LocalEngineBase):
    """基本推理能力。"""

    def test_infer_builtin_grandparent(self):
        result = self.engine.infer("grandparent(a, _Z)")
        self.assertTrue(result["success"], result)
        self.assertIn("_Z", result["result"])

    def test_infer_no_solution(self):
        result = self.engine.infer("nonexistent(x, y)")
        self.assertFalse(result["success"])
        self.assertEqual(result["result"], None)

    def test_infer_method_returned(self):
        result = self.engine.infer("grandparent(a, _Z)", method="cot")
        self.assertEqual(result["method"], "cot")

    def test_infer_auto_method(self):
        result = self.engine.infer("grandparent(a, _Z)", method="auto")
        self.assertTrue(result["success"])
        self.assertIn("method", result)

    def test_infer_bad_goal_string(self):
        result = self.engine.infer("!!invalid!!")
        # 要么解析失败，要么推理无结果
        self.assertIn("success", result)

    def test_infer_all_returns_dict(self):
        results = self.engine.infer_all("grandparent(a, _Z)")
        self.assertIsInstance(results, dict)
        self.assertIn("cot", results)

    def test_infer_all_cot_succeeds(self):
        results = self.engine.infer_all("grandparent(a, _Z)")
        self.assertIn("result", results["cot"])


class TestLocalEngineLearn(LocalEngineBase):
    """规则学习功能。"""

    def test_learn_fact(self):
        r = self.engine.learn("king(Arthur).")
        self.assertTrue(r["success"], r)
        self.assertIn("king", r["message"])

    def test_learn_rule(self):
        self.engine.learn("child(a).")
        # Orphan rules require force=True (is_child has no callers)
        r = self.engine.learn("is_child(_X) :- child(_X).", force=True)
        self.assertTrue(r["success"], r)

    def test_learn_then_infer(self):
        self.engine.learn("mortal(Socrates).")
        # Use variable query so binding is non-empty
        result = self.engine.infer("mortal(_Who)")
        self.assertTrue(result["success"])

    def test_learn_invalid_rule_error(self):
        # 空字符串应该不崩溃
        r = self.engine.learn("")
        self.assertIn("success", r)

    def test_learn_force_flag(self):
        # 使用 force=True 跳过一致性检查
        r = self.engine.learn("orphan_rule(_X) :- undefined_pred(_X).", force=True)
        self.assertTrue(r["success"])


class TestLocalEngineMemory(LocalEngineBase):
    """记忆存储与召回。"""

    def test_remember_returns_success(self):
        r = self.engine.remember("color(sky, blue)")
        self.assertTrue(r["success"])

    def test_remember_and_recall(self):
        self.engine.remember("color(sky, blue)")
        r = self.engine.recall("color")
        self.assertIn("memories", r)
        self.assertIsInstance(r["memories"], list)

    def test_recall_empty(self):
        r = self.engine.recall("nonexistent_query_xyz")
        self.assertIn("memories", r)

    def test_remember_then_infer(self):
        self.engine.remember("favorite(user, coffee)")
        # Use variable query so binding is non-empty
        result = self.engine.infer("favorite(user, _Drink)")
        self.assertTrue(result["success"])


class TestLocalEngineSearch(LocalEngineBase):
    """知识图谱搜索。"""

    def test_search_returns_results(self):
        r = self.engine.search("parent")
        self.assertIn("results", r)
        self.assertIsInstance(r["results"], list)

    def test_search_empty_query(self):
        r = self.engine.search("")
        self.assertIn("results", r)


class TestLocalEngineHealth(LocalEngineBase):
    """健康报告。"""

    def test_health_structure(self):
        h = self.engine.health()
        for key in ("rules", "facts", "orphans", "cycles", "trust_score", "skills"):
            self.assertIn(key, h, f"Missing key: {key}")

    def test_health_types(self):
        h = self.engine.health()
        self.assertIsInstance(h["rules"], int)
        self.assertIsInstance(h["facts"], int)
        self.assertIsInstance(h["orphans"], list)
        self.assertIsInstance(h["trust_score"], float)


class TestLocalEngineDream(LocalEngineBase):
    """梦境引擎触发。"""

    def test_dream_returns_log(self):
        r = self.engine.dream()
        self.assertIn("dream", r)
        self.assertIsInstance(r["dream"], str)


class TestLocalEngineSoulInfo(LocalEngineBase):
    """身份与配置内省。"""

    def test_soul_info_has_identity(self):
        info = self.engine.soul_info()
        self.assertIn("identity", info)
        self.assertIn("soul", info)

    def test_agents_info(self):
        info = self.engine.agents_info()
        self.assertIn("agents", info)

    def test_user_prefs(self):
        info = self.engine.user_prefs()
        self.assertIn("user", info)


class TestLocalEngineCustomSoul(TempDirMixin, unittest.TestCase):
    """自定义 SOUL.md 影响引擎身份。"""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.tmpdir, "SOUL.md"), "w") as f:
            f.write("## Identity\n- name: Prometheus\n")
        self.engine = LocalInferenceEngine(
            config_dir=self.tmpdir,
            memory_dir=self.tmpdir,
            enable_dream=False,
        )

    def tearDown(self):
        self.engine.stop()
        super().tearDown()

    def test_identity_from_soul_md(self):
        info = self.engine.soul_info()
        self.assertEqual(info["identity"], "Prometheus")


# ════════════════════════════════════════════════════════════════════════════
# 3. SuperBrainAgent 集成 ConfigLoader
# ════════════════════════════════════════════════════════════════════════════
class TestSuperBrainAgentConfig(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.tmpdir, "SOUL.md"), "w") as f:
            f.write("## Identity\n- name: Helios\n")
        self.agent = SuperBrainAgent(
            memory_dir=self.tmpdir,
            _config=ConfigLoader(self.tmpdir).load(),
        )
        self.agent.dream.stop()

    def test_agent_uses_soul_identity(self):
        self.assertEqual(self.agent.bone.identity, "Helios")

    def test_agent_config_attribute(self):
        self.assertIsInstance(self.agent.config, ConfigLoader)

    def test_agent_config_dir_not_required(self):
        # 默认构造（无配置文件）不崩溃
        a = SuperBrainAgent(memory_dir=self.tmpdir)
        a.dream.stop()
        self.assertIsNotNone(a.config)


# ════════════════════════════════════════════════════════════════════════════
# 4. 版本标识
# ════════════════════════════════════════════════════════════════════════════
class TestVersion(unittest.TestCase):
    def test_version_in_module_docstring(self):
        doc = _mod.__doc__ or ""
        self.assertIn("0.11.0", doc)

    def test_version_in_agent_attribute(self):
        """知识库中 pangu.version 属性为 0.11.0"""
        tmpdir = tempfile.mkdtemp()
        try:
            agent = SuperBrainAgent(memory_dir=tmpdir)
            agent.dream.stop()
            # 验证内置事实包含版本号
            version_facts = [
                f for f in agent.kb.facts
                if f.name == "attribute" and "0.11.0" in str(f.args)
            ]
            self.assertTrue(len(version_facts) > 0, "应有 attribute(pangu, version, 0.11.0) 事实")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
