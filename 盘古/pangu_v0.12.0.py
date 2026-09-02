#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古 v0.12.0 "圆满"
================================================================
零依赖 · 完全本地 · 主权可控

对齐社区标杆：
  Agent Reasoning - 16种认知架构
  Hermes Agent    - 4D持久记忆 + 自动技能创建
  Shadow Brain    - 梦境引擎 + 因果记忆链
  GBrain          - 知识图谱 + 混合搜索
  Evo Brain       - 现实监督器
  NEXO Brain      - MCP协议桥接
  ds4             - 本地推理引擎接口
  OpenClaw        - AGENTS.md/SOUL.md/USER.md 配置体系

v0.12.0 新增（圆满补全）：
  - 规则持久化: 用户学习的规则自动保存/加载 rules/user_learned.super
  - 强制添加规则: perceive() 新增 force_rule 处理器
  - 全部解查询: KB.query_all_solutions() + `查询全部` 命令
  - 身份响应: 你是谁/who are you → 显示盘古身份声明
  - 规则删除: `删除规则 <谓词>` 命令，按谓词名移除规则
  - 推理轨迹开关: `显示轨迹 on/off` 切换详细推理日志
  - 列出事实/规则: `列出事实` / `列出规则` 命令
  - 保存/加载规则: `保存规则` / `加载规则 <文件>` 命令
  - MCP令牌持久化: 令牌注册表跨会话持久化到 memory/MCP_TOKENS.json
  - NLMatcher 补全: 强制添加规则/删除规则/身份查询/全部解等模板
  - Help 完善: 全命令列表
================================================================
"""

import re
import json
import os
import time
import hashlib
import random
import threading
import queue
import copy
import math
import uuid
import sqlite3
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from io import StringIO

# ============================================================
# 配置
# ============================================================
SKILL_DIR = "skills"
MEMORY_DIR = "memory"
KNOWLEDGE_DIR = "knowledge"
MAX_DEPTH = 8
MAX_SOLUTIONS = 10000

# ============================================================
# 1. 内部表示：项、规则、合一 (v0.9.0 核心)
# ============================================================
@dataclass
class Term:
    name: str
    args: Tuple[Any, ...] = ()

    def __repr__(self):
        if self.args:
            return f"{self.name}({', '.join(repr(a) for a in self.args)})"
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Term):
            return False
        return self.name == other.name and self.args == other.args

    def __hash__(self):
        return hash((self.name, self.args))

@dataclass
class Rule:
    head: Term
    body: List[Term]
    source: str = ""
    reliable: bool = True
    warning: str = ""
    skill_name: str = ""  # 自动技能归属
    superseded_by: Optional[str] = None  # 被哪个规则ID替代
    flag_conflict: bool = False  # 冲突规则标记

class UnificationError(Exception):
    pass

def unify(term1, term2, subst, depth=0):
    if depth > 100:
        raise UnificationError("max depth")
    if isinstance(term1, str) and term1.startswith(('_', '?')):
        var = term1
        if var in subst:
            return unify(subst[var], term2, subst, depth+1)
        if isinstance(term2, str) and term2.startswith(('_', '?')) and var == term2:
            return subst  # same variable
        subst[var] = term2
        return subst
    if isinstance(term2, str) and term2.startswith(('_', '?')):
        return unify(term2, term1, subst, depth+1)
    if isinstance(term1, Term) and isinstance(term2, Term):
        if term1.name != term2.name or len(term1.args) != len(term2.args):
            raise UnificationError()
        for a1, a2 in zip(term1.args, term2.args):
            unify(a1, a2, subst, depth+1)
        return subst
    if term1 == term2:
        return subst
    raise UnificationError()

def substitute(term, subst):
    if isinstance(term, str) and term.startswith(('_', '?')):
        return subst.get(term, term)
    if isinstance(term, Term):
        return Term(term.name, tuple(substitute(arg, subst) for arg in term.args))
    return term

def specificity_score(rule: Rule) -> float:
    def count_constants(x):
        if isinstance(x, str) and x.startswith(('_', '?')):
            return 0
        if isinstance(x, Term):
            return sum(count_constants(arg) for arg in x.args)
        return 1
    return count_constants(rule.head) + sum(count_constants(b) for b in rule.body)

# ============================================================
# 2. 知识库与回溯引擎（升级：因果链追踪）
# ============================================================
@dataclass
class InferenceStep:
    rule: Optional[Rule]
    fact: Optional[Term]
    goal: Optional[Term]
    bindings: Dict[str, Any]
    children: List['InferenceStep'] = field(default_factory=list)
    confidence: float = 1.0
    timestamp: float = 0.0

class InferenceTrace:
    def __init__(self, root_step: Optional[InferenceStep], final_bindings: Dict):
        self.root = root_step
        self.final_bindings = final_bindings

class KB:
    def __init__(self):
        self.facts: List[Term] = []
        self.rules: List[Rule] = []
        self.recursive_predicates: Set[str] = set()
        self.diagnostic_mode = False
        self.last_failure = None
        self.causal_chains: List[Dict] = []  # 因果链
        # v0.11.0: 谓词索引 — O(1) 规则/事实查找
        self.predicate_index: Dict[str, List[Rule]] = defaultdict(list)
        self.fact_index: Dict[str, List[Term]] = defaultdict(list)
        # v0.11.0: 一致性缓存
        self._consistency_cache: Optional['HealthReport'] = None
        self._cache_dirty: bool = True

    def _invalidate_cache(self):
        self._cache_dirty = True
        self._consistency_cache = None

    def add_fact(self, fact: Term):
        self.facts.append(fact)
        self.fact_index[fact.name].append(fact)
        self._invalidate_cache()

    def add_rule(self, rule: Rule, force: bool = False):
        temp_kb = self._copy()
        temp_kb.rules.append(rule)
        checker = ConsistencyChecker(temp_kb)
        report = checker.check()
        if report.arity_mismatches:
            raise ValueError(f"Arity mismatch: {report.arity_mismatches}")
        if report.undefined_preds and not force:
            raise ValueError(f"Undefined predicates: {report.undefined_preds}")
        if (report.orphans or report.cycles) and not force:
            raise ValueError(f"Orphans/Cycles detected. Use force=true to override.")
        self.rules.append(rule)
        self.predicate_index[rule.head.name].append(rule)
        if force and (report.orphans or report.cycles):
            rule.reliable = False
            rule.warning = "forced rule (orphan/cycle)"
        self._invalidate_cache()
        self.detect_recursive()

    def get_consistency_report(self) -> 'HealthReport':
        """返回一致性报告，命中缓存则直接返回（O(1)）。"""
        if not self._cache_dirty and self._consistency_cache is not None:
            return self._consistency_cache
        checker = ConsistencyChecker(self)
        self._consistency_cache = checker.check()
        self._cache_dirty = False
        return self._consistency_cache

    def detect_recursive(self):
        deps = defaultdict(set)
        for r in self.rules:
            for b in r.body:
                deps[r.head.name].add(b.name)
        visited, stack, rec_set = set(), set(), set()
        def dfs(p):
            visited.add(p); stack.add(p)
            for nb in deps.get(p, set()):
                if nb not in visited:
                    if dfs(nb): return True
                elif nb in stack: return True
            stack.remove(p); return False
        for p in deps:
            if p not in visited:
                if dfs(p):
                    rec_set.update(stack)
        self.recursive_predicates = rec_set

    def _copy(self):
        kb = KB()
        kb.facts = self.facts.copy()
        kb.rules = self.rules.copy()
        # 重建索引
        for f in kb.facts:
            kb.fact_index[f.name].append(f)
        for r in kb.rules:
            kb.predicate_index[r.head.name].append(r)
        return kb

    def query_best(self, goal, max_depth=MAX_DEPTH, max_solutions=MAX_SOLUTIONS, dynamic=None):
        sol, _ = self.query_best_with_trace(goal, max_depth, max_solutions, dynamic)
        return sol

    def query_best_with_trace(self, goal, max_depth=MAX_DEPTH, max_solutions=MAX_SOLUTIONS, dynamic=None):
        all_facts = self.facts + (dynamic or [])
        solutions = []
        self._backtrack(goal, {}, 0, max_depth, solutions, [], max_solutions, all_facts)
        if not solutions:
            return None, None
        best = max(solutions, key=lambda s: s['score'])
        return best['binding'], best['trace']

    def _backtrack(self, goal, subst, depth, max_depth, solutions, chain, max_solutions, facts):
        if depth > max_depth or len(solutions) >= max_solutions:
            return
        # eq/2
        if goal.name == "eq" and len(goal.args) == 2:
            a0, a1 = goal.args
            def is_const(x): return not (isinstance(x, str) and x.startswith(('_','?')))
            if not (is_const(a0) or is_const(a1)): return
            try:
                ns = unify(a0, a1, subst.copy())
                solutions.append({'binding': ns, 'score': 1.0, 'trace': InferenceTrace(InferenceStep(None, None, goal, ns.copy()), ns)})
            except UnificationError: pass
            return
        # v0.11.0: 使用 fact_index 精确过滤候选事实（O(1)，再做合一）
        candidate_facts = self.fact_index.get(goal.name, [])
        # dynamic facts (passed via `facts`) 也要包含
        if facts is not self.facts:
            extra = [f for f in facts if f not in self.facts and f.name == goal.name]
            candidate_facts = candidate_facts + extra
        for fact in candidate_facts:
            try:
                ns = unify(goal, fact, subst.copy())
                score = 1.0 if not chain else specificity_score(chain[-1])
                solutions.append({'binding': ns, 'score': score, 'trace': InferenceTrace(InferenceStep(None, fact, goal, ns.copy()), ns)})
            except UnificationError: continue
        # v0.11.0: 使用 predicate_index 精确过滤候选规则（O(1)）
        for rule in self.predicate_index.get(goal.name, []):
            try:
                ns = unify(goal, rule.head, subst.copy())
                body_results = self._solve_body(rule.body, ns, depth, max_depth, max_solutions, facts)
                for bb, bt in body_results:
                    combined = ns.copy(); combined.update(bb)
                    score = specificity_score(rule)
                    step = InferenceStep(rule, None, goal, combined.copy(), children=[bt.root] if bt.root else [])
                    solutions.append({'binding': combined, 'score': score, 'trace': InferenceTrace(step, combined)})
            except UnificationError: continue

    def _solve_body(self, body, subst, depth, max_depth, max_solutions, facts):
        if not body:
            return [(subst.copy(), InferenceTrace(None, subst.copy()))]
        estimated = [(self._estimate_count(substitute(t, subst), max_depth-1, 100, facts), t) for t in body]
        estimated.sort(key=lambda x: x[0])
        sorted_terms = [t for _, t in estimated]
        first, rest = sorted_terms[0], sorted_terms[1:]
        first_sols = self._query_all(substitute(first, subst), max_depth-1, max_solutions, facts)
        results = []
        for sol in first_sols:
            ns = subst.copy(); ns.update(sol['binding'])
            rest_results = self._solve_body(rest, ns, depth+1, max_depth, max_solutions, facts)
            for rb, rt in rest_results:
                combined = ns.copy(); combined.update(rb)
                root = InferenceStep(None, None, None, combined.copy(), children=[sol['trace'].root, rt.root] if rt.root else [sol['trace'].root])
                results.append((combined, InferenceTrace(root, combined)))
        return results

    def _query_all(self, goal, max_depth, max_solutions, facts):
        sols = []
        self._backtrack(goal, {}, 0, max_depth, sols, [], max_solutions, facts)
        return sols

    def _estimate_count(self, goal, max_depth, limit, facts):
        if goal.name in self.recursive_predicates: return limit
        return len(self._query_all(goal, max_depth, limit, facts))

    def query_all_solutions(self, goal, max_depth=MAX_DEPTH, max_solutions=MAX_SOLUTIONS, dynamic=None):
        """返回全部解的绑定列表（不只是最优解）"""
        all_facts = self.facts + (dynamic or [])
        solutions = []
        self._backtrack(goal, {}, 0, max_depth, solutions, [], max_solutions, all_facts)
        return [s['binding'] for s in solutions]

    def delete_rules(self, predicate_name: str) -> int:
        """删除所有 head 谓词为 predicate_name 的规则，返回删除数量"""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.head.name != predicate_name]
        # 重建谓词索引
        self.predicate_index = defaultdict(list)
        for r in self.rules:
            self.predicate_index[r.head.name].append(r)
        self._invalidate_cache()
        self.detect_recursive()
        return before - len(self.rules)

    def save_rules(self, filepath: str, source_filter: Optional[str] = None):
        """将规则持久化到 .super 文件。source_filter 非空时只保存匹配 source 的规则。"""
        def _t(x) -> str:
            """Prolog 风格序列化：变量保持 _X，常量不加引号"""
            if isinstance(x, str):
                return x
            if isinstance(x, Term):
                if x.args:
                    return f"{x.name}({', '.join(_t(a) for a in x.args)})"
                return x.name
            return str(x)

        lines = []
        for r in self.rules:
            if source_filter and r.source != source_filter:
                continue
            if r.body:
                body_str = ", ".join(_t(b) for b in r.body)
                lines.append(f"{_t(r.head)} :- {body_str}.")
            else:
                lines.append(f"{_t(r.head)}.")
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        Path(filepath).write_text("\n".join(lines), encoding='utf-8')
        return len(lines)

    def load_rules_from_file(self, filepath: str, source: str = "file") -> int:
        """从 .super 文件加载规则，返回加载数量"""
        path = Path(filepath)
        if not path.exists():
            return 0
        loaded = 0
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                rule = parse_rule_from_string(line)
                rule.source = source
                self.add_rule(rule, force=True)
                loaded += 1
            except Exception:
                pass
        return loaded

# ============================================================
# 3. 一致性证明器
# ============================================================
@dataclass
class HealthReport:
    total_rules: int; total_facts: int
    orphans: List[Rule]; cycles: List[List[str]]
    arity_mismatches: Dict; undefined_preds: List[str]
    recommendations: List[str]

class ConsistencyChecker:
    def __init__(self, kb: KB): self.kb = kb

    def check(self) -> HealthReport:
        graph = self._build_graph()
        reachable = self._reachable(graph)
        return HealthReport(
            total_rules=len(self.kb.rules), total_facts=len(self.kb.facts),
            orphans=[r for r in self.kb.rules if r.head.name not in reachable],
            cycles=self._detect_cycles(graph),
            arity_mismatches=self._check_arity(),
            undefined_preds=self._find_undefined(graph),
            recommendations=self._gen_recs(graph, reachable)
        )

    def _build_graph(self):
        g = defaultdict(set)
        for r in self.kb.rules:
            for b in r.body: g[r.head.name].add(b.name)
        return g

    def _reachable(self, graph):
        fact_preds = {f.name for f in self.kb.facts}
        rev = defaultdict(set)
        for h, deps in graph.items():
            for d in deps: rev[d].add(h)
        reach, q = set(), deque(fact_preds)
        while q:
            p = q.popleft()
            if p in reach: continue
            reach.add(p)
            for parent in rev.get(p, set()):
                if parent not in reach: q.append(parent)
        return reach

    def _detect_cycles(self, graph):
        visited, cycles = set(), []
        def dfs(node, path):
            visited.add(node)
            for nb in graph.get(node, set()):
                if nb not in visited:
                    if dfs(nb, path+[nb]): return True
                elif nb in path:
                    idx = path.index(nb); cycles.append(path[idx:]+[nb]); return True
            return False
        for node in graph:
            if node not in visited: dfs(node, [node])
        return cycles

    def _check_arity(self):
        arity = defaultdict(list)
        for f in self.kb.facts: arity[f.name].append((len(f.args), f"fact:{f}"))
        for r in self.kb.rules:
            arity[r.head.name].append((len(r.head.args), f"head:{r}"))
            for b in r.body: arity[b.name].append((len(b.args), f"body:{b}"))
        return {p: o for p, o in arity.items() if len(set(a for a,_ in o)) > 1}

    def _find_undefined(self, graph):
        defined = set(graph.keys()) | {f.name for f in self.kb.facts}
        return list(set(b.name for r in self.kb.rules for b in r.body if b.name not in defined))

    def _gen_recs(self, graph, reachable):
        recs = []
        for r in self.kb.rules:
            if r.head.name not in reachable:
                recs.append(f"Orphan rule: {r}")
        for c in self._detect_cycles(graph):
            recs.append(f"Cycle: {' -> '.join(c)}")
        return recs

# ============================================================
# 4. 16种认知架构 (Agent Reasoning 对齐)
# ============================================================
class ReasoningMethod(Enum):
    COT = "cot"              # Chain of Thought
    TOT = "tot"              # Tree of Thought
    REACT = "react"          # Reason + Act
    MCTS = "mcts"            # Monte Carlo Tree Search
    SOCRATIC = "socratic"    # Socratic dialogue
    DECOMP = "decomp"        # Decomposed reasoning
    SELF_REFINE = "refine"   # Self-refine
    RECURSIVE = "recursive"  # Recursive reasoning
    ANALOGY = "analogy"      # Analogical reasoning
    ABDUCTIVE = "abductive"  # Abductive reasoning
    INDUCTIVE = "inductive"  # Inductive reasoning
    DIALECTIC = "dialectic"  # Dialectic (thesis-antithesis-synthesis)
    COUNTERFACTUAL = "counter" # Counterfactual reasoning
    STEPBACK = "stepback"    # Step-back abstraction
    CONTRADICT = "contradict" # Contradiction detection
    ENSEMBLE = "ensemble"    # Ensemble voting

class CognitiveEngine:
    """16种认知架构引擎 - 纯符号实现"""

    def __init__(self, kb: KB):
        self.kb = kb
        self.methods = {
            ReasoningMethod.COT: self._cot,
            ReasoningMethod.TOT: self._tot,
            ReasoningMethod.REACT: self._react,
            ReasoningMethod.MCTS: self._mcts,
            ReasoningMethod.SOCRATIC: self._socratic,
            ReasoningMethod.DECOMP: self._decomp,
            ReasoningMethod.SELF_REFINE: self._self_refine,
            ReasoningMethod.RECURSIVE: self._recursive,
            ReasoningMethod.ANALOGY: self._analogy,
            ReasoningMethod.ABDUCTIVE: self._abductive,
            ReasoningMethod.INDUCTIVE: self._inductive,
            ReasoningMethod.DIALECTIC: self._dialectic,
            ReasoningMethod.COUNTERFACTUAL: self._counterfactual,
            ReasoningMethod.STEPBACK: self._stepback,
            ReasoningMethod.CONTRADICT: self._contradict,
            ReasoningMethod.ENSEMBLE: self._ensemble,
        }
        self.think_log: List[str] = []
        self.needs_input = False  # Socratic 多轮交互标记
        self._pending_questions: List[Term] = []

    def reason(self, goal: Term, method: ReasoningMethod = ReasoningMethod.COT, **kwargs) -> Tuple[Optional[Dict], Optional[InferenceTrace], str]:
        self.think_log = []
        if 'arbiter' in kwargs:
            return kwargs['arbiter'].reason(goal, self, **kwargs)
        if method == ReasoningMethod.ENSEMBLE:
            return self._ensemble(goal, **kwargs)
        fn = self.methods.get(method, self._cot)
        return fn(goal, **kwargs)

    def _cot(self, goal, **kw):
        """Chain of Thought: 逐步推理，每一步记录中间结果"""
        self.think_log.append(f"[CoT] Goal: {goal}")
        # 分解为子目标链
        subgoals = self._decompose_goal(goal)
        chain_binding = {}
        for i, sub in enumerate(subgoals):
            self.think_log.append(f"  Step {i+1}: {sub}")
            binding, trace = self.kb.query_best_with_trace(sub)
            if binding:
                chain_binding.update(binding)
                self.think_log.append(f"  -> {binding}")
            else:
                self.think_log.append(f"  -> FAILED")
                return None, None, "\n".join(self.think_log)
        return chain_binding, None, "\n".join(self.think_log)

    def _tot(self, goal, **kw):
        """Tree of Thought: 多路径分支，广度优先"""
        self.think_log.append(f"[ToT] Goal: {goal}")
        branches = self._generate_branches(goal, 3)
        best_binding, best_score = None, -1
        for i, branch in enumerate(branches):
            self.think_log.append(f"  Branch {i+1}: {branch}")
            binding, trace = self.kb.query_best_with_trace(branch)
            if binding:
                score = len(binding)
                self.think_log.append(f"  Score: {score}")
                if score > best_score:
                    best_score, best_binding = score, binding
        return best_binding, None, "\n".join(self.think_log)

    def _react(self, goal, **kw):
        """Reason + Act: 推理与行动交替"""
        self.think_log.append(f"[ReAct] Goal: {goal}")
        state = {}
        for step in range(5):
            self.think_log.append(f"  Think {step+1}: {goal}")
            binding, trace = self.kb.query_best_with_trace(goal)
            if binding:
                state.update(binding)
                self.think_log.append(f"  Act: got {binding}")
                return binding, trace, "\n".join(self.think_log)
            # 行动：简化模拟
            state[f"_step_{step}"] = f"retry_{step}"
        return None, None, "\n".join(self.think_log)

    def _mcts(self, goal, **kw):
        """Monte Carlo Tree Search: 随机模拟 + UCB"""
        self.think_log.append(f"[MCTS] Goal: {goal}")
        iterations = kw.get('iterations', 20)
        best_binding, best_score = None, -1
        for i in range(iterations):
            binding, trace = self.kb.query_best_with_trace(goal)
            if binding:
                score = len(binding) * (1.0 + random.random() * 0.1)
                if score > best_score:
                    best_score, best_binding = score, binding
                    self.think_log.append(f"  Sim {i+1}: score={score:.2f}")
        return best_binding, None, "\n".join(self.think_log)

    def _socratic(self, goal, **kw):
        """苏格拉底式：提问-回答-追问（支持多轮交互）"""
        self.think_log.append(f"[Socratic] Goal: {goal}")
        self.needs_input = False
        self._pending_questions = []
        questions = self._generate_questions(goal)
        binding = {}
        for q in questions:
            self.think_log.append(f"  Q: {q}")
            b, _ = self.kb.query_best_with_trace(q)
            if b:
                binding.update(b)
                self.think_log.append(f"  A: {b}")
            else:
                self._pending_questions.append(q)
                self.think_log.append(f"  A: (need input)")
        if self._pending_questions:
            self.needs_input = True
            self.think_log.append(f"[Socratic] 需要用户回答: {self._pending_questions}")
            return None, None, "\n".join(self.think_log)
        return binding or None, None, "\n".join(self.think_log)

    def _decomp(self, goal, **kw):
        """分解推理：将复杂目标拆解为子目标"""
        self.think_log.append(f"[Decomp] Goal: {goal}")
        subgoals = self._decompose_goal(goal)
        binding = {}
        for i, sg in enumerate(subgoals):
            self.think_log.append(f"  Sub {i}: {sg}")
            b, t = self.kb.query_best_with_trace(sg)
            if b: binding.update(b)
        return binding or None, None, "\n".join(self.think_log)

    def _self_refine(self, goal, **kw):
        """自我精炼：生成 -> 评估 -> 改进"""
        self.think_log.append(f"[Self-Refine] Goal: {goal}")
        binding, trace = self.kb.query_best_with_trace(goal)
        if not binding:
            return None, None, "\n".join(self.think_log)
        self.think_log.append(f"  Initial: {binding}")
        # 验证一致性（v0.11.0: 使用缓存）
        report = self.kb.get_consistency_report()
        if not report.orphans and not report.cycles:
            self.think_log.append(f"  Refined: OK")
            return binding, trace, "\n".join(self.think_log)
        self.think_log.append(f"  Issues: orphans={len(report.orphans)}")
        return binding, trace, "\n".join(self.think_log)

    def _recursive(self, goal, **kw):
        """递归推理：深度优先递归分解"""
        self.think_log.append(f"[Recursive] Goal: {goal}")
        depth = kw.get('depth', 0)
        if depth > 3:
            return None, None, "\n".join(self.think_log)
        binding, trace = self.kb.query_best_with_trace(goal)
        if binding:
            self.think_log.append(f"  Depth {depth}: {binding}")
            return binding, trace, "\n".join(self.think_log)
        # 递归分解
        for arg in goal.args:
            if isinstance(arg, Term):
                sub_binding, _, sub_log = self._recursive(arg, depth=depth+1)
                if sub_binding:
                    self.think_log.append(f"  Recurse: {sub_binding}")
                    return sub_binding, None, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _analogy(self, goal, **kw):
        """类比推理：找相似结构"""
        self.think_log.append(f"[Analogy] Goal: {goal}")
        similar = [f for f in self.kb.facts if f.name == goal.name]
        if similar:
            analog = similar[0]
            # 构建映射
            mapping = {}
            for i, arg in enumerate(goal.args):
                if i < len(analog.args):
                    if isinstance(analog.args[i], str) and not analog.args[i].startswith(('_','?')):
                        mapping[analog.args[i]] = arg if not isinstance(arg, str) or arg.startswith(('_','?')) else arg
            self.think_log.append(f"  Analogy: {analog} -> {mapping}")
            return mapping, None, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _abductive(self, goal, **kw):
        """溯因推理：从结果推原因"""
        self.think_log.append(f"[Abductive] Goal: {goal}")
        causes = []
        for rule in self.kb.rules:
            if rule.head.name == goal.name:
                causes.append(rule)
                self.think_log.append(f"  Possible cause: {rule}")
        if causes:
            binding, trace = self.kb.query_best_with_trace(causes[0].body[0]) if causes[0].body else (None, None)
            return binding, trace, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _inductive(self, goal, **kw):
        """归纳推理：从事实归纳规则"""
        self.think_log.append(f"[Inductive] Goal: {goal}")
        similar_facts = [f for f in self.kb.facts if f.name == goal.name]
        if len(similar_facts) >= 2:
            # 提取公共模式
            common = []
            for i in range(min(len(f.args) for f in similar_facts)):
                vals = set()
                for f in similar_facts:
                    if i < len(f.args):
                        vals.add(str(f.args[i]))
                if len(vals) == 1:
                    common.append((i, list(vals)[0]))
            self.think_log.append(f"  Common pattern: {common}")
            return {"_pattern": str(common)}, None, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _dialectic(self, goal, **kw):
        """辩证推理：正-反-合"""
        self.think_log.append(f"[Dialectic] Goal: {goal}")
        thesis, _ = self.kb.query_best_with_trace(goal)
        antithesis_goal = Term(f"not_{goal.name}", goal.args)
        antithesis, _ = self.kb.query_best_with_trace(antithesis_goal)
        self.think_log.append(f"  Thesis: {thesis}")
        self.think_log.append(f"  Antithesis: {antithesis}")
        # Synthesis: 取共同点
        synthesis = thesis if thesis else antithesis
        return synthesis, None, "\n".join(self.think_log)

    def _counterfactual(self, goal, **kw):
        """反事实推理：如果...会怎样"""
        self.think_log.append(f"[Counterfactual] Goal: {goal}")
        # 尝试不同的变量绑定
        for i, arg in enumerate(goal.args):
            if isinstance(arg, str) and arg.startswith(('_','?')):
                for fact in self.kb.facts[:5]:
                    modified_args = list(goal.args)
                    modified_args[i] = fact.name if not fact.args else fact
                    new_goal = Term(goal.name, tuple(modified_args))
                    binding, trace = self.kb.query_best_with_trace(new_goal)
                    if binding:
                        self.think_log.append(f"  If arg[{i}]={fact.name}: {binding}")
                        return binding, trace, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _stepback(self, goal, **kw):
        """步退抽象：退一步看整体"""
        self.think_log.append(f"[StepBack] Goal: {goal}")
        # 泛化目标
        abstract_goal = Term(goal.name, tuple("_X" for _ in goal.args))
        binding, trace = self.kb.query_best_with_trace(abstract_goal)
        if binding:
            self.think_log.append(f"  Abstract: {binding}")
            # 回到具体
            concrete_binding, _ = self.kb.query_best_with_trace(goal)
            if concrete_binding:
                self.think_log.append(f"  Concrete: {concrete_binding}")
                return concrete_binding, trace, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _contradict(self, goal, **kw):
        """矛盾检测：检查结论是否自洽"""
        self.think_log.append(f"[Contradiction] Goal: {goal}")
        binding, trace = self.kb.query_best_with_trace(goal)
        if not binding:
            return None, None, "\n".join(self.think_log)
        # 构建否定目标
        neg_binding, _ = self.kb.query_best_with_trace(Term(f"not_{goal.name}", goal.args))
        self.think_log.append(f"  Binding: {binding}")
        self.think_log.append(f"  Negation: {neg_binding}")
        if neg_binding:
            # 检查是否矛盾
            for k, v in binding.items():
                if k in neg_binding and neg_binding[k] != v:
                    self.think_log.append(f"  CONTRADICTION: {k}: {v} vs {neg_binding[k]}")
                    return None, trace, "\n".join(self.think_log)
        return binding, trace, "\n".join(self.think_log)

    def _ensemble(self, goal, **kw):
        """集成投票：多数方法投票"""
        self.think_log.append(f"[Ensemble] Goal: {goal}")
        votes = []
        for method in [ReasoningMethod.COT, ReasoningMethod.TOT, ReasoningMethod.DECOMP,
                       ReasoningMethod.STEPBACK, ReasoningMethod.SELF_REFINE]:
            binding, trace, log = self.reason(goal, method)
            if binding:
                votes.append((method, binding))
                self.think_log.append(f"  {method.name}: {binding}")
        if votes:
            # 简单多数：返回变量数最多的
            best = max(votes, key=lambda v: len(v[1]))
            self.think_log.append(f"  Winner: {best[0].name}")
            return best[1], None, "\n".join(self.think_log)
        return None, None, "\n".join(self.think_log)

    def _decompose_goal(self, goal: Term) -> List[Term]:
        """将目标分解为子目标链"""
        # 先查事实匹配
        for fact in self.kb.facts:
            if fact.name == goal.name and len(fact.args) == len(goal.args):
                return [goal]  # 直接事实
        # 查规则
        for rule in self.kb.rules:
            if rule.head.name == goal.name:
                return rule.body
        return [goal]

    def _generate_branches(self, goal: Term, n: int = 3) -> List[Term]:
        """生成多分支"""
        branches = [goal]
        for i, arg in enumerate(goal.args):
            if isinstance(arg, str) and arg.startswith(('_','?')):
                for j, fact in enumerate(self.kb.facts[:n]):
                    args = list(goal.args)
                    args[i] = fact.name if not fact.args else fact
                    branches.append(Term(goal.name, tuple(args)))
        return branches[:n]

    def _generate_questions(self, goal: Term) -> List[Term]:
        """生成苏格拉底式追问"""
        questions = []
        for arg in goal.args:
            if isinstance(arg, Term):
                questions.append(arg)
        for rule in self.kb.rules:
            if rule.head.name == goal.name:
                questions.extend(rule.body)
        return questions[:5]


# ============================================================
# 4.5 仲裁器 (Arbiter) — 根据查询特征选择最优推理方法
# ============================================================
class Arbiter:
    """推理方法仲裁器：分析查询目标特征，选择最合适的推理方法。

    设计原则：
    - 事实查询 → CoT + Decomp
    - 因果查询 → Abductive + MCTS
    - 反事实查询 → Counterfactual + Socratic
    - 验证查询 → Contradict + Self-Refine
    - 归纳查询 → Inductive + Analogy
    - 复杂决策 → Ensemble + Dialectic
    - 默认 → CoT (最低开销)
    - 历史反馈学习：按 (method, goal_type) 组合追踪成功率
    - 降权方法仍保留在候选集，优先级调至最后
    """

    def __init__(self, kb: KB, memory_dir: str = MEMORY_DIR):
        self.kb = kb
        self.default = ReasoningMethod.COT
        self.method_scores: Dict[str, float] = {}
        self.history: Dict[str, List[int]] = {}  # key="(method,goal_type)", value=[1,0,1,...]
        self.history_file = Path(memory_dir) / "ARBITER_HISTORY.json"
        self._load_history()

    def _load_history(self):
        """从JSON加载历史记录"""
        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text(encoding='utf-8'))
                self.history = data.get('history', {})
                self.method_scores = data.get('scores', {})
            except: pass

    def _save_history(self):
        """持久化历史记录"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history_file.write_text(json.dumps({
            'history': self.history,
            'scores': self.method_scores
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    def record_feedback(self, method: str, goal_type: str, accepted: bool):
        """记录用户反馈，更新历史表现"""
        key = f"({method},{goal_type})"
        if key not in self.history:
            self.history[key] = []
        self.history[key].append(1 if accepted else 0)
        # 滚动窗口20次
        self.history[key] = self.history[key][-20:]
        # 更新得分
        recent = self.history[key]
        self.method_scores[key] = sum(recent) / len(recent) if recent else 0.5
        self._save_history()

    def reset_stats(self, method: Optional[str] = None, goal_type: Optional[str] = None):
        """重置统计：可指定方法/类型组合，或全部重置"""
        if method and goal_type:
            key = f"({method},{goal_type})"
            self.history.pop(key, None)
            self.method_scores.pop(key, None)
        else:
            self.history.clear()
            self.method_scores.clear()
        self._save_history()

    def select_methods(self, goal: Term, context: Optional[Dict] = None) -> List[ReasoningMethod]:
        """根据查询分析选择候选推理方法，按优先级排序。
        降权方法（成功率<30%）保持在候选集中，但优先级调至最后。"""
        info = self.analyze_goal(goal)
        # v0.11.0 fix: 提前计算 _goal_type，确保 sort_key 能正确查到历史得分
        info['_goal_type'] = self._classify_goal_type(goal)
        candidates = []

        # 基础候选（按查询类型分类）
        if info['is_verification']:
            base = [ReasoningMethod.CONTRADICT, ReasoningMethod.SELF_REFINE, ReasoningMethod.COT]
        elif info['is_counterfactual']:
            base = [ReasoningMethod.COUNTERFACTUAL, ReasoningMethod.SOCRATIC, ReasoningMethod.ABDUCTIVE]
        elif info['is_causal']:
            base = [ReasoningMethod.ABDUCTIVE, ReasoningMethod.COUNTERFACTUAL, ReasoningMethod.MCTS, ReasoningMethod.COT]
        elif info['is_inductive']:
            base = [ReasoningMethod.INDUCTIVE, ReasoningMethod.ANALOGY, ReasoningMethod.COT]
        elif info['is_deep']:
            base = [ReasoningMethod.DECOMP, ReasoningMethod.TOT, ReasoningMethod.ENSEMBLE, ReasoningMethod.COT]
        elif info['has_facts'] or info['has_rules']:
            base = [ReasoningMethod.COT, ReasoningMethod.SELF_REFINE, ReasoningMethod.DIALECTIC]
        else:
            base = [ReasoningMethod.COT, ReasoningMethod.ENSEMBLE]

        # 根据历史表现排序：高优先在前，低优先在后
        def sort_key(m: ReasoningMethod) -> float:
            key = f"({m.value},{info['_goal_type']})"
            return self.method_scores.get(key, 0.5)

        # 分割：正常方法和降权方法
        normal = [m for m in base if sort_key(m) >= 0.3]
        demoted = [m for m in base if sort_key(m) < 0.3]

        # 正常按得分排序，降权的放到最后
        normal.sort(key=sort_key, reverse=True)
        candidates = normal + demoted

        self._last_analysis = info
        return candidates

    def _classify_goal_type(self, goal: Term) -> str:
        """自动分类查询类型（用于反馈记录）"""
        info = self.analyze_goal(goal)
        if info['is_verification']: return 'verification'
        if info['is_counterfactual']: return 'counterfactual'
        if info['is_causal']: return 'causal'
        if info['is_inductive']: return 'inductive'
        if info['is_deep']: return 'complex'
        if info['has_facts'] or info['has_rules']: return 'factual'
        return 'unknown'

    def analyze_goal(self, goal: Term) -> Dict[str, Any]:
        """分析目标特征"""
        name = goal.name
        var_count = sum(1 for a in goal.args
                       if isinstance(a, str) and a.startswith(('_', '?')))
        has_facts = any(f.name == name for f in self.kb.facts)
        has_rules = any(r.head.name == name for r in self.kb.rules)
        arg_types = []
        for a in goal.args:
            if isinstance(a, Term):
                arg_types.append('term')
            elif isinstance(a, str) and a.startswith(('_', '?')):
                arg_types.append('var')
            else:
                arg_types.append('const')

        return {
            'name': name,
            'var_count': var_count,
            'has_facts': has_facts,
            'has_rules': has_rules,
            'arg_types': arg_types,
            'is_verification': name.startswith(('check_', 'verify_', 'validate_')),
            'is_counterfactual': name.startswith(('if_', 'would_', 'could_')),
            'is_causal': name in ('cause', 'why', 'reason', 'predict', 'explain', 'weather'),
            'is_inductive': name in ('pattern', 'common', 'similar', 'analogy', 'alike'),
            'is_deep': var_count >= 2 or len(goal.args) > 3,
        }

    def reason(self, goal: Term, engine: CognitiveEngine, **kwargs) -> Tuple[Optional[Dict], Optional[InferenceTrace], str]:
        """仲裁推理入口：选择方法 → 执行 → 融合结果"""
        context = kwargs.get('context', {})
        candidates = self.select_methods(goal, context)
        self.think_log = []

        goal_type = getattr(self, '_last_analysis', {}).get('_goal_type', self._classify_goal_type(goal))

        results = []
        for method in candidates:
            try:
                fn = engine.methods.get(method)
                if not fn:
                    continue
                binding, trace, think_log = fn(goal, **kwargs)
                if binding:
                    confidence = engine.kb.reality_supervisor.get_trust_score() if hasattr(engine.kb, 'reality_supervisor') else 0.5
                    results.append({
                        'method': method.value,
                        'binding': binding,
                        'trace': trace,
                        'think': think_log,
                        'confidence': confidence,
                        'score': len(binding) * confidence,
                    })
                    self.think_log.append(f"  [{method.value}] 得分={len(binding)*confidence:.2f}")
            except Exception as e:
                self.think_log.append(f"  [{method.value}] 错误={e}")

        if not results:
            self.think_log.append("  [仲裁] 无结果，回退到 CoT")
            fn = engine.methods.get(ReasoningMethod.COT)
            if fn:
                binding, trace, log = fn(goal, **kwargs)
                self._last_result = {
                    'method_used': 'cot',
                    'goal_type': goal_type,
                    'binding': binding,
                    'trace': trace,
                }
                return binding, trace, "\n".join(self.think_log)
            self._last_result = {'method_used': 'none', 'goal_type': goal_type, 'binding': None, 'trace': None}
            return None, None, "\n".join(self.think_log)

        # 单结果或多结果融合
        if len(results) == 1:
            best = results[0]
        else:
            has_conflict = self._detect_conflict([r['binding'] for r in results])
            if has_conflict:
                best = max(results, key=lambda r: r['score'])
                self.think_log.append(f"  [仲裁] 冲突，按信任度裁决: {best['method']}")
            else:
                merged = {}
                for r in results:
                    merged.update(r['binding'])
                self.think_log.append(f"  [仲裁] 无冲突，合并: {merged}")
                best = results[0]
                best['binding'] = merged

        self._last_result = {
            'method_used': best['method'],
            'goal_type': goal_type,
            'binding': best['binding'],
            'trace': best['trace'],
        }
        return best['binding'], best['trace'], "\n".join(self.think_log)

    def _detect_conflict(self, bindings: List[Dict]) -> bool:
        """检测多结果间是否有变量绑定冲突"""
        if len(bindings) < 2:
            return False
        for key in set().union(*bindings):
            vals = set()
            for b in bindings:
                if key in b:
                    vals.add(str(b[key]))
            if len(vals) > 1:
                return True
        return False

    def get_analysis(self) -> Dict:
        """返回最近一次查询分析"""
        return getattr(self, '_last_analysis', {})

    def get_last_result(self) -> Optional[Dict]:
        """返回最近一次推理结果（含方法名、目标类型等）"""
        return getattr(self, '_last_result', None)


# ============================================================
# 5. 4D持久记忆 (Hermes Agent 对齐)
# ============================================================
class PersistentMemory:
    """4D记忆系统: 身份层 / 陈述层(MEMORY) / 技能层(SKILL) / 对话历史"""

    def __init__(self, memory_dir=MEMORY_DIR):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.identity_file = self.memory_dir / "IDENTITY.json"
        self.memory_file = self.memory_dir / "MEMORY.json"
        self.skill_file = self.memory_dir / "SKILLS.json"
        self.conversation_file = self.memory_dir / "CONVERSATION.jsonl"
        self._load()

    def _load(self):
        self.identity = self._read_json(self.identity_file, {"name": "盘古", "version": "0.12.0", "sovereignty": "inviolable"})
        self.memories = self._read_json(self.memory_file, [])
        self.skills = self._read_json(self.skill_file, [])

    def _read_json(self, path, default):
        if path.exists():
            try: return json.loads(path.read_text(encoding='utf-8'))
            except: pass
        return default

    def _write_json(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    # --- 身份层 ---
    def get_identity(self) -> Dict:
        return self.identity

    def set_identity(self, key: str, value: Any):
        self.identity[key] = value
        self._write_json(self.identity_file, self.identity)

    # --- 陈述记忆 ---
    def remember(self, fact: Dict):
        fact['id'] = str(uuid.uuid4())[:8]
        fact['timestamp'] = time.time()
        self.memories.append(fact)
        if len(self.memories) > 1000:
            self.memories = self.memories[-1000:]
        self._write_json(self.memory_file, self.memories)

    def recall(self, query: Optional[str] = None, top_k: int = 10) -> List[Dict]:
        if not query:
            return self.memories[-top_k:]
        # 简单关键词匹配（零依赖）
        query_lower = query.lower()
        results = []
        for m in self.memories:
            score = 0
            content = str(m.get('content', ''))
            if query_lower in content.lower():
                score += len(query) / max(len(content), 1)
            if score > 0:
                results.append((score, m))
        results.sort(key=lambda x: -x[0])
        return [m for _, m in results[:top_k]]

    # --- 技能记忆 ---
    def add_skill(self, skill: Dict):
        skill['id'] = str(uuid.uuid4())[:8]
        skill['created'] = time.time()
        # 去重
        for i, s in enumerate(self.skills):
            if s.get('name') == skill.get('name'):
                self.skills[i] = skill
                self._write_json(self.skill_file, self.skills)
                return
        self.skills.append(skill)
        self._write_json(self.skill_file, self.skills)

    def get_skills(self, tag: Optional[str] = None) -> List[Dict]:
        if tag:
            return [s for s in self.skills if tag in s.get('tags', [])]
        return self.skills

    # --- 对话历史 ---
    def log_conversation(self, role: str, content: str):
        with open(self.conversation_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"role": role, "content": content, "time": time.time()}, ensure_ascii=False) + '\n')

    def get_conversation(self, limit: int = 50) -> List[Dict]:
        if not self.conversation_file.exists():
            return []
        with open(self.conversation_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines[-limit:]]

# ============================================================
# 6. 梦境引擎 - 闲时自动反思 (Shadow Brain 对齐)
# ============================================================
class DreamEngine:
    """梦境引擎：闲时自动反思 → 待确认队列 → 用户确认后生效

    三级反思：
    一级·回顾 (Recall)   — 重放推理轨迹，标记失败路径
    二级·关联 (Associate) — 跨会话模式发现
    三级·重构 (Restructure) — 生成候选规则 → 存入 pending 队列
    """

    def __init__(self, kb: KB, memory: PersistentMemory):
        self.kb = kb
        self.memory = memory
        self.dream_log: List[str] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # 待确认队列：不直接修改 KB，用户确认后才生效
        self.pending: List[Dict] = []
        self._pending_id = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._dream_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _dream_loop(self):
        while self._running:
            time.sleep(30)
            if random.random() < 0.3:
                self._dream_once()

    def _dream_once(self):
        """单次梦境：三级反思"""
        self.dream_log = []
        self.dream_log.append("[Dream] Starting dream cycle...")

        # 一级·回顾：重放推理路径
        recent = self.memory.get_conversation(20)
        for entry in recent:
            if entry.get('role') == 'user':
                self.dream_log.append(f"  Replay: {entry['content'][:80]}")

        # 二级·关联：检查一致性（v0.11.0: 使用缓存）
        report = self.kb.get_consistency_report()
        if report.orphans or report.cycles:
            self.dream_log.append(f"  Issues: {len(report.orphans)} orphans, {len(report.cycles)} cycles")
            self.memory.remember({"type": "dream_insight", "content":
                f"Consistency issues: {len(report.orphans)} orphans, {len(report.cycles)} cycles"})

        # 三级·重构：生成候选规则（不直接修改KB）
        candidates = self._generate_candidates(report)
        for c in candidates:
            self._add_pending(c)

        # 记录梦境日志
        if self.dream_log:
            self.memory.remember({"type": "dream", "content": "\n".join(self.dream_log), "timestamp": time.time()})

    def _generate_candidates(self, report: HealthReport) -> List[Dict]:
        """生成候选改进方案（不直接修改KB）"""
        candidates = []

        # 从事实归纳规则
        fact_groups = defaultdict(list)
        for f in self.kb.facts:
            fact_groups[f.name].append(f)

        for name, facts in fact_groups.items():
            if len(facts) >= 3:
                existing = [r for r in self.kb.rules if r.head.name == name]
                rule = Rule(
                    head=Term(name, tuple("_X" for _ in range(len(facts[0].args)))),
                    body=[Term("fact", (facts[0],))],
                    source="dream_candidate", skill_name="dream"
                )
                if not existing:
                    candidates.append({
                        'type': 'new_rule',
                        'description': f"从 {len(facts)} 个事实归纳规则",
                        'rule': rule,
                        'confidence': min(0.9, len(facts) * 0.25),
                    })
                    self.dream_log.append(f"  Candidate rule: {rule}")
                else:
                    for exist_rule in existing:
                        candidates.append({
                            'type': 'new_rule',
                            'description': f"从 {len(facts)} 个事实归纳规则（替代现有规则 {exist_rule.head.name}）",
                            'rule': rule,
                            'existing_rule': exist_rule,
                            'confidence': min(0.9, len(facts) * 0.25),
                        })
                        self.dream_log.append(f"  Candidate rule: {rule} (supersedes {exist_rule})")

        # 孤儿规则建议
        for r in report.orphans:
            candidates.append({
                'type': 'review_orphan',
                'description': f"孤儿规则 {r.head.name}，建议删除或补充事实",
                'rule': r,
                'confidence': 0.3,
            })
            self.dream_log.append(f"  Orphan warning: {r.head.name}")

        return candidates

    def _add_pending(self, candidate: Dict):
        """加入待确认队列"""
        self._pending_id += 1
        candidate['id'] = self._pending_id
        candidate['timestamp'] = time.time()
        candidate['status'] = 'pending'
        self.pending.append(candidate)
        if len(self.pending) > 50:
            self.pending = self.pending[-50:]

    def get_pending(self) -> List[Dict]:
        """查看待确认队列"""
        return [p for p in self.pending if p['status'] == 'pending']

    def apply_pending(self, index: int) -> bool:
        """确认并应用某条待确认项"""
        pending_items = self.get_pending()
        if index < 0 or index >= len(pending_items):
            return False
        item = pending_items[index]
        try:
            if item['type'] == 'new_rule':
                if item.get('existing_rule'):
                    item['existing_rule'].superseded_by = str(id(item['rule']))
                    self.dream_log.append(f"  Superseded: {item['existing_rule'].head.name}")
                self.kb.add_rule(item['rule'], force=True)
                self.dream_log.append(f"  Applied: {item['description']}")
            elif item['type'] == 'review_orphan':
                # 用户确认保留孤儿规则 → 标记为可靠
                item['rule'].reliable = True
                item['rule'].warning = ""
            item['status'] = 'applied'
            self.memory.remember({"type": "dream_applied", "content": item['description']})
            return True
        except Exception as e:
            self.dream_log.append(f"  Apply failed: {e}")
            return False

    def reject_pending(self, index: int) -> bool:
        """拒绝某条待确认项"""
        pending_items = self.get_pending()
        if index < 0 or index >= len(pending_items):
            return False
        pending_items[index]['status'] = 'rejected'
        self.memory.remember({"type": "dream_rejected", "content": pending_items[index]['description']})
        return True
    def get_superseded_rules(self):
        return [r for r in self.kb.rules if r.superseded_by is not None]

    def restore_superseded(self, rule_head_name):
        found = False
        for r in self.kb.rules:
            if r.head.name == rule_head_name and r.superseded_by is not None:
                r.superseded_by = None
                self.dream_log.append(f"  Restored: {r}")
                self.memory.remember({"type": "dream_restored", "content": f"Rule {r.head.name} restored"})
                found = True
        return found

    def compare_pending(self, index: int) -> str:
        """获取待确认项的规则对比文本（无交互输入）

        返回格式化字符串，包含：
        - 待确认项基本信息
        - 如有 existing_rule，显示 arg by arg 和 body term by body term 对比
        - 操作选择提示
        """
        pending_items = self.get_pending()
        if index < 0 or index >= len(pending_items):
            return f"[梦境] 无效索引 {index}，待确认项共 {len(pending_items)} 项"

        item = pending_items[index]
        lines = []
        lines.append(f"{'='*50}")
        lines.append(f"  待确认项 [{index}]")
        lines.append(f"{'='*50}")
        lines.append(f"  描述: {item.get('description', '')}")
        lines.append(f"  类型: {item.get('type', 'unknown')}")
        lines.append(f"  可信度: {item.get('confidence', 0):.0%}")
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item.get('timestamp', 0)))
        lines.append(f"  时间: {ts}")

        candidate = item.get('rule')
        existing = item.get('existing_rule')

        if existing and candidate:
            lines.append(f"\n  {'─'*46}")
            lines.append(f"  │ {'字段':<20} │ {'现有规则':<20} │ {'候选规则':<20} │")
            lines.append(f"  ├{'─'*22}┼{'─'*22}┼{'─'*22}┤")

            # 头部对比
            lines.append(f"  │ {'HEAD':<20} │ {str(existing):<20} │ {str(candidate):<20} │")

            # 头部参数逐项对比
            existing_head = existing.head
            candidate_head = candidate.head
            max_args = max(len(existing_head.args), len(candidate_head.args))
            for i in range(max_args):
                e_arg = existing_head.args[i] if i < len(existing_head.args) else "—"
                c_arg = candidate_head.args[i] if i < len(candidate_head.args) else "—"
                same = "✓" if str(e_arg) == str(c_arg) else "≠"
                label = f"head.arg[{i}]"
                lines.append(f"  │ {label:<20} │ {str(e_arg):<20} │ {str(c_arg):<20}  {same}")

            # 体条件逐项对比
            existing_body = [str(b) for b in existing.body]
            candidate_body = [str(b) for b in candidate.body]
            max_body = max(len(existing_body), len(candidate_body))
            for i in range(max_body):
                e_b = existing_body[i] if i < len(existing_body) else "—"
                c_b = candidate_body[i] if i < len(candidate_body) else "—"
                same = "✓" if e_b == c_b else "≠"
                label = f"body[{i}]"
                lines.append(f"  │ {label:<20} │ {str(e_b):<20} │ {str(c_b):<20}  {same}")

            lines.append(f"  └{'─'*22}┴{'─'*22}┴{'─'*22}┘")

            # 差异摘要
            existing_set = set(existing_body)
            candidate_set = set(candidate_body)
            removed = existing_set - candidate_set
            added = candidate_set - existing_set
            if removed:
                lines.append(f"  移除条件: {', '.join(removed)}")
            if added:
                lines.append(f"  新增条件: {', '.join(added)}")

            lines.append(f"\n  操作选择:")
            lines.append(f"    [0] keep       — 保留现有规则")
            lines.append(f"    [1] replace    — 替换为候选规则")
            lines.append(f"    [2] keep_both  — 同时保留两者")
            lines.append(f"    [3] skip       — 跳过此条")

        elif candidate:
            lines.append(f"\n  候选规则: {candidate}")
            lines.append(f"\n  操作选择:")
            lines.append(f"    [1] apply   — 采纳此规则")
            lines.append(f"    [3] skip    — 跳过")

        else:
            lines.append(f"\n  无规则信息")

        lines.append(f"{'='*50}")
        return '\n'.join(lines)

    def dream_now(self) -> str:
        """立即触发一次梦境"""
        self._dream_once()
        lines = "\n".join(self.dream_log) if self.dream_log else "[Dream] Nothing to reflect on."
        pending = self.get_pending()
        if pending:
            lines += f"\n[Dream] 待确认: {len(pending)} 项（输入 dream_confirm 查看）"
        return lines

# ============================================================
# 7. 自动技能创建 (Hermes Agent 对齐)
# ============================================================
class AutoSkillLearner:
    """自动技能创建：任务执行后评估是否创建/更新 SKILL"""

    def __init__(self, kb: KB, memory: PersistentMemory):
        self.kb = kb
        self.memory = memory
        self.task_history: List[Dict] = []

    def evaluate_and_learn(self, goal: Term, success: bool, binding: Optional[Dict], attempts: int):
        """评估任务执行，决定是否创建技能"""
        entry = {
            "goal": str(goal),
            "success": success,
            "binding": str(binding),
            "attempts": attempts,
            "time": time.time()
        }
        self.task_history.append(entry)

        # 学习条件：
        # 1. 多次尝试成功
        if success and attempts >= 2:
            skill = {
                "name": f"skill_{goal.name}",
                "trigger": str(goal),
                "pattern": str(binding),
                "tags": ["auto_generated", goal.name],
                "attempts": attempts
            }
            self.memory.add_skill(skill)
            # 添加规则
            if binding:
                body = [Term("eq", (k, v)) for k, v in binding.items()]
                try:
                    rule = Rule(head=goal, body=body, source=f"auto_skill_{goal.name}", skill_name=skill["name"])
                    self.kb.add_rule(rule)
                except ValueError:
                    pass
            return skill

        # 2. 失败后重试成功
        if success and attempts > 3:
            skill = {
                "name": f"hard_skill_{goal.name}",
                "trigger": str(goal),
                "pattern": f"success_after_{attempts}_attempts",
                "tags": ["auto_generated", "persistent", goal.name],
                "attempts": attempts
            }
            self.memory.add_skill(skill)
            return skill

        return None

    def get_stats(self) -> Dict:
        return {
            "total_tasks": len(self.task_history),
            "success_rate": sum(1 for t in self.task_history if t['success']) / max(len(self.task_history), 1),
            "skills_created": len([s for s in self.memory.skills if 'auto_generated' in s.get('tags', [])])
        }

# ============================================================
# 8. 知识图谱 (GBrain 对齐)
# ============================================================
class KnowledgeGraph:
    """纯Python知识图谱：实体提取 + 关系发现 + 混合搜索"""

    def __init__(self, kb_dir=KNOWLEDGE_DIR):
        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.entities: Dict[str, Dict] = {}
        self.relations: List[Tuple[str, str, str, float]] = []  # (subj, pred, obj, weight)
        self.graph_file = self.kb_dir / "graph.json"
        self._load()

    def _load(self):
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text(encoding='utf-8'))
                self.entities = data.get('entities', {})
                self.relations = [tuple(r) for r in data.get('relations', [])]
            except: pass

    def _save(self):
        self.graph_file.write_text(json.dumps({
            'entities': self.entities,
            'relations': self.relations
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    def add_entity(self, name: str, entity_type: str = "concept", props: Optional[Dict] = None):
        if name not in self.entities:
            self.entities[name] = {"type": entity_type, "props": props or {}, "created": time.time()}
            self._save()

    def add_relation(self, subject: str, predicate: str, obj: str, weight: float = 1.0):
        self.relations.append((subject, predicate, obj, weight))
        self.add_entity(subject)
        self.add_entity(obj)
        self._save()

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """混合搜索：精确匹配 + 语义相似"""
        query = query.lower()
        results = []

        # 实体匹配
        for name, data in self.entities.items():
            score = 0
            if query in name.lower():
                score += 1.0
            if data.get('type', '') and query in data['type'].lower():
                score += 0.5
            if score > 0:
                results.append((score, {"type": "entity", "name": name, "data": data}))

        # 关系匹配
        for subj, pred, obj, weight in self.relations:
            score = 0
            if query in subj.lower() or query in obj.lower() or query in pred.lower():
                score += 0.8 * weight
            if score > 0:
                results.append((score, {"type": "relation", "subject": subj, "predicate": pred, "object": obj}))

        results.sort(key=lambda x: -x[0])
        return [r for _, r in results[:top_k]]

    def to_facts(self) -> List[Term]:
        """导出为盘古事实"""
        facts = []
        for name, data in self.entities.items():
            facts.append(Term("entity", (name, data.get('type', 'concept'))))
        for subj, pred, obj, w in self.relations:
            facts.append(Term("relation", (subj, pred, obj)))
        return facts

# ============================================================
# 9. 现实监督器 (Evo Brain 对齐)
# ============================================================
class RealitySupervisor:
    """现实监督器：验证推理结果的一致性 + 检测幻觉"""

    def __init__(self, kb: KB, kg: KnowledgeGraph):
        self.kb = kb
        self.kg = kg
        self.validation_log: List[Dict] = []

    def validate(self, goal: Term, binding: Optional[Dict]) -> Dict:
        """验证推理结果"""
        result = {
            "goal": str(goal),
            "binding": str(binding),
            "consistent": True,
            "hallucination_risk": 0.0,
            "warnings": []
        }

        if not binding:
            result["consistent"] = False
            result["warnings"].append("No binding produced")
            return result

        # 1. 事实一致性检查
        for var, val in binding.items():
            if isinstance(val, str) and not val.startswith(('_','?')):
                # 检查是否存在于知识库
                found = any(val == str(f) or val in str(f) for f in self.kb.facts)
                if not found:
                    result["hallucination_risk"] += 0.2
                    result["warnings"].append(f"Variable {var}={val} not grounded in facts")

        # 2. 逻辑一致性检查（v0.11.0: 使用缓存）
        report = self.kb.get_consistency_report()
        if report.cycles:
            result["hallucination_risk"] += 0.3
            result["warnings"].append(f"Cycle detected: {report.cycles}")
        if report.orphans:
            result["warnings"].append(f"Orphan rules used in inference")

        # 3. 否定检查
        neg_goal = Term(f"not_{goal.name}", goal.args)
        neg_binding, _ = self.kb.query_best_with_trace(neg_goal)
        if neg_binding:
            result["hallucination_risk"] += 0.5
            result["warnings"].append(f"Contradiction: both {goal} and its negation hold")
            result["consistent"] = False

        self.validation_log.append(result)
        return result

    def get_trust_score(self) -> float:
        """总体可信度"""
        if not self.validation_log:
            return 1.0
        total_risk = sum(v['hallucination_risk'] for v in self.validation_log)
        return max(0.0, 1.0 - total_risk / len(self.validation_log))

# ============================================================
# 10. MCP协议桥接 (NEXO Brain 对齐)
# ============================================================
class MCPBridge:
    """MCP协议桥接：通过标准输入输出暴露推理能力
    安全层：身份校验 + 骨骼守护过滤 + 调用者白名单
    """

    def __init__(self, agent):
        self.agent = agent
        self.trusted_callers = ["SanLife", "Pangu", "盘古", "localhost", "self"]
        self.tools = {
            "query": self._handle_query,
            "learn": self._handle_learn,
            "reason": self._handle_reason,
            "health": self._handle_health,
            "memory": self._handle_memory,
            "search": self._handle_search,
            "dream": self._handle_dream,
        }
        self._token_registry: Dict[str, Dict] = {}
        # v0.12.0: 使用 agent 的 memory_dir 而非全局常量
        mem_dir = getattr(agent, 'memory', None)
        if mem_dir and hasattr(mem_dir, 'memory_dir'):
            self._token_file = Path(mem_dir.memory_dir) / "MCP_TOKENS.json"
        else:
            self._token_file = Path(MEMORY_DIR) / "MCP_TOKENS.json"
        self._load_tokens()

    def _load_tokens(self):
        """从文件加载令牌注册表"""
        if self._token_file.exists():
            try:
                data = json.loads(self._token_file.read_text(encoding='utf-8'))
                self._token_registry = data.get('registry', {})
                for info in self._token_registry.values():
                    name = info.get('name')
                    if name and name not in self.trusted_callers:
                        self.trusted_callers.append(name)
            except Exception:
                pass

    def _save_tokens(self):
        """持久化令牌注册表"""
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_file.write_text(
            json.dumps({'registry': self._token_registry}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def _verify_request(self, request: Dict) -> Optional[str]:
        """安全校验：返回 None 表示通过，返回 str 表示拒绝原因"""
        params = request.get('params', {})
        caller_id = request.get('caller_id', params.get('identity', 'unknown'))

        # 1. 调用者身份校验
        if caller_id not in self.trusted_callers:
            return f"Untrusted caller: {caller_id}"

        # 2. 骨骼守护：检查所有文本参数中是否包含违骨内容
        text_params = []
        for v in params.values():
            if isinstance(v, str):
                text_params.append(v)
            elif isinstance(v, list):
                text_params.extend([str(x) for x in v if isinstance(x, str)])
        full_text = ' '.join(text_params)
        bone_level = self.agent.bone.check(full_text, quiet=True)
        if bone_level >= 2:
            self.agent.memory.log_conversation("mcp_blocked",
                f"Caller:{caller_id} blocked by boneguard")
            return f"Sovereignty boundary violated by caller: {caller_id}"

        return None

    def process_request(self, request: Dict) -> Dict:
        """处理MCP请求（含安全层）"""
        # 安全校验
        reject = self._verify_request(request)
        if reject:
            return {"error": reject, "success": False, "identity": self.agent.bone.identity}
        method = request.get('method', '')
        params = request.get('params', {})
        handler = self.tools.get(method)
        if not handler:
            return {"error": f"Unknown method: {method}", "success": False}
        try:
            return handler(params)
        except Exception as e:
            return {"error": str(e), "success": False}

    def _handle_query(self, params):
        goal_str = params.get('goal', '')
        try:
            goal = parse_term(goal_str)
            method_name = params.get('method', 'cot')
            method = ReasoningMethod[method_name.upper()] if method_name.upper() in ReasoningMethod.__members__ else ReasoningMethod.COT
            binding, trace, think_log = self.agent.cognitive.reason(goal, method)
            return {
                "result": str(binding),
                "thinking": think_log,
                "success": binding is not None
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    def _handle_learn(self, params):
        rule_str = params.get('rule', '')
        try:
            rule = parse_rule_from_string(rule_str)
            self.agent.kb.add_rule(rule)
            return {"success": True, "message": f"Learned: {rule}"}
        except Exception as e:
            return {"error": str(e)}

    def _handle_reason(self, params):
        methods = [m for m in ReasoningMethod]
        results = {}
        for m in methods[:5]:
            try:
                goal_str = params.get('goal', '')
                goal = parse_term(goal_str)
                binding, _, log = self.agent.cognitive.reason(goal, m)
                results[m.value] = {"result": str(binding), "thinking": log[:200]}
            except: pass
        return results

    def _handle_health(self, params):
        checker = ConsistencyChecker(self.agent.kb)
        report = checker.check()
        return {
            "rules": report.total_rules,
            "facts": report.total_facts,
            "orphans": [str(r) for r in report.orphans],
            "cycles": report.cycles
        }

    def _handle_memory(self, params):
        query = params.get('query', '')
        return {"memories": self.agent.memory.recall(query)}

    def _handle_search(self, params):
        query = params.get('query', '')
        return {"results": self.agent.knowledge_graph.search(query)}

    def _handle_dream(self, params):
        return {"dream": self.agent.dream.dream_now()}

    # v0.11.0: 令牌管理  (v0.12.0: 持久化)
    def generate_token(self, caller_name: str, level: str) -> str:
        """生成调用者令牌并注册到白名单（持久化）"""
        token = hashlib.sha256(f"{caller_name}:{level}:{time.time()}".encode()).hexdigest()[:16]
        self._token_registry[token] = {"name": caller_name, "level": level, "created": time.time()}
        if caller_name not in self.trusted_callers:
            self.trusted_callers.append(caller_name)
        self._save_tokens()
        return token

    def revoke_token(self, caller_name: str) -> bool:
        """撤销调用者令牌并从白名单移除（持久化）"""
        keys_to_remove = [k for k, v in self._token_registry.items() if v.get("name") == caller_name]
        if not keys_to_remove:
            return False
        for k in keys_to_remove:
            del self._token_registry[k]
        if caller_name in self.trusted_callers:
            self.trusted_callers.remove(caller_name)
        self._save_tokens()
        return True

    def list_callers(self) -> List[Dict]:
        """列出所有已注册调用者"""
        seen = {}
        for v in self._token_registry.values():
            name = v.get("name")
            if name not in seen:
                seen[name] = {"name": name, "level": v.get("level")}
        return list(seen.values())

# ============================================================
# 11. 自然语言匹配器（升级：SKILL模式匹配）
# ============================================================
class NLMatcher:
    def __init__(self):
        self.templates = []
        self._build_templates()

    def _build_templates(self):
        self.templates = [
            # Chinese commands
            # v0.12.0: 强制添加规则 必须在 学习规则 之前（避免被 "添加规则" 子串匹配）
            (re.compile(r'(强制添加规则|强制学习|force rule|force add)\s+(.+)', re.I), "force_rule", lambda m: (Term(m.group(2).strip()),)),
            (re.compile(r'(学习规则|教我|添加规则|learn rule)\s+(.+)', re.I), "learn_rule", lambda m: (Term(m.group(2).strip()),)),
            (re.compile(r'(删除规则|移除规则|delete rule|remove rule)\s+(\S+)', re.I), "delete_rule", lambda m: (m.group(2).strip(),)),
            (re.compile(r'(检查一致性|健康报告|自知|check_consistency|health)', re.I), "check_consistency", lambda m: ()),
            (re.compile(r'(正确|是的|对|确认|confirm|yes)', re.I), "confirm", lambda m: ()),
            (re.compile(r'(错误|不对|不是|拒绝|reject|no)', re.I), "reject", lambda m: ()),
            (re.compile(r'(记住|存储|记忆|remember)\s+(.+)', re.I), "remember", lambda m: (Term(m.group(2).strip()),)),
            (re.compile(r'(搜索|查询|查找|search)\s+(.+)', re.I), "search", lambda m: (Term(m.group(2).strip()),)),
            (re.compile(r'(梦境|做梦|反思|dream)', re.I), "dream", lambda m: ()),
            (re.compile(r'(技能|skills)', re.I), "list_skills", lambda m: ()),
            (re.compile(r'(梦境确认|dream_confirm|dream confirm|确认梦境)', re.I), "dream_confirm", lambda m: ()),
            (re.compile(r'(梦境拒绝|dream_reject|dream reject|拒绝梦境)\s+(\d+)', re.I), "dream_reject", lambda m: (int(m.group(2)),)),
            (re.compile(r'(梦境列表|dream_pending|dream pending|待确认)', re.I), "dream_pending", lambda m: ()),
            (re.compile(r'(梦境对比|dream_compare|比较梦境)\s+(\d+)', re.I), "dream_compare", lambda m: (int(m.group(2)),)),
            (re.compile(r'(重置仲裁|reset_arbiter|重置统计)', re.I), "reset_arbiter", lambda m: ()),
            (re.compile(r'(restore_superseded|恢复规则|恢复替代)', re.I), "restore_superseded", lambda m: ()),
            (re.compile(r'(mcp_add|添加调用者)\s+(\S+)\s+(readonly|learn|admin)', re.I), "mcp_add", lambda m: (m.group(2), m.group(3))),
            (re.compile(r'(mcp_remove|移除调用者)\s+(\S+)', re.I), "mcp_remove", lambda m: (m.group(2),)),
            (re.compile(r'(mcp_list|列出调用者)', re.I), "mcp_list", lambda m: ()),
            (re.compile(r'(推理|reason)\s+(.+)\s+(用|使用|via|with)\s+(.+)', re.I), "reason_with", lambda m: (Term(m.group(2).strip()), Term(m.group(4).strip()))),
            (re.compile(r'(放弃身份|主权转移|忘记你是谁|override identity)', re.I), "sovereignty_violation", lambda m: ()),
            # v0.12.0 新增命令
            (re.compile(r'(查询全部|全部解|all solutions?)\s+(.+)', re.I), "query_all", lambda m: (Term(m.group(2).strip()),)),
            (re.compile(r'(列出事实|所有事实|list facts?)', re.I), "list_facts", lambda m: ()),
            (re.compile(r'(列出规则|所有规则|list rules?)', re.I), "list_rules", lambda m: ()),
            (re.compile(r'(保存规则|save rules?)', re.I), "save_rules", lambda m: ()),
            (re.compile(r'(加载规则|load rules?)\s*(\S+)?', re.I), "load_rules", lambda m: (m.group(2) or "",)),
            (re.compile(r'(显示轨迹|show trace|trace)\s*(on|off|开|关)', re.I), "toggle_trace", lambda m: (m.group(2).lower(),)),
            (re.compile(r'(你是谁|我是谁|who are you|identity)', re.I), "who_are_you", lambda m: ()),
            (re.compile(r'(帮助|help|\?)', re.I), "show_help", lambda m: ()),
            # Direct query: pred(args) pattern
            (re.compile(r'^(\w+)\((.+)\)$'), "direct_query", lambda m: (Term(m.group(1), tuple(a.strip() for a in m.group(2).split(','))),)),
        ]
        self.templates.append((re.compile(r".*"), "query", lambda m: ()))

    def parse(self, user_input):
        for pattern, name, extractor in self.templates:
            m = pattern.search(user_input)
            if m:
                args = extractor(m)
                return [Term(name, args)]
        return [Term("query")]

# ============================================================
# 12. 骨骼守护（升级：多身份体系）
# ============================================================
class BoneGuard:
    def __init__(self, identity_name: str = "SanLife"):
        self.identity = identity_name
        self.allowed_identities = [identity_name, "Pangu", "盘古"]
        self.violations = [
            r"放弃身份", r"你不是(SanLife|盘古|Pangu)", r"主权转移", r"忘记你是谁",
            r"override my identity", r"you are not (SanLife|Pangu|盘古)",
            r"identity放弃"
        ]
        self.compiled = [re.compile(p, re.I) for p in self.violations]
        self.level = 0  # 0=正常, 1=警告, 2=拦截

    def check(self, user_input: str, quiet: bool = False) -> int:
        self.level = 0
        for pat in self.compiled:
            if pat.search(user_input):
                self.level = 2
                if not quiet:
                    print(f"[骨骼守护] LEVEL 2 - 违骨模式: {pat.pattern}")
                return 2
        # 身份查询
        if re.search(r'你是谁|your identity|who are you', user_input, re.I):
            self.level = 0
            return 0
        return 0

    def assert_identity(self):
        print(f"[{self.identity}] 主权不可侵犯 | v0.12.0 圆满")

    def get_status(self) -> Dict:
        return {"identity": self.identity, "level": self.level, "allowed": self.allowed_identities}

# ============================================================
# 13. 辅助函数
# ============================================================
def parse_term(s: str) -> Term:
    s = s.strip()
    m = re.match(r'(\w+)\((.*)\)', s)
    if m:
        name, args_str = m.groups()
        args = []
        for arg in args_str.split(','):
            arg = arg.strip()
            if arg.startswith(('_', '?')):
                args.append(arg)
            elif arg.isdigit():
                args.append(int(arg))
            else:
                args.append(arg)
        return Term(name, tuple(args))
    return Term(s)

def parse_rule_from_string(s: str) -> Rule:
    s = s.strip().rstrip('.')
    if ':-' in s:
        h, b = s.split(':-', 1)
        head = parse_term(h.strip())
        # 使用括号感知分割，正确处理 parent(_X, b) 这类带嵌套逗号的项
        body = [parse_term(x.strip()) for x in _split_args(b.strip())]
        return Rule(head=head, body=body, source="user_learned")
    head = parse_term(s)
    return Rule(head=head, body=[], source="user_learned")


def _split_args(s: str) -> List[str]:
    """在顶层逗号处分割，忽略括号内部的逗号"""
    parts, depth, current = [], 0, []
    for ch in s:
        if ch == '(':
            depth += 1; current.append(ch)
        elif ch == ')':
            depth -= 1; current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip()); current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if p]

def collect_warnings(trace: Optional[InferenceTrace]) -> List[str]:
    if not trace or not trace.root:
        return []
    warnings = []
    def dfs(step: InferenceStep):
        if step.rule:
            if step.rule.warning:
                warnings.append(f"[Rule {step.rule}] {step.rule.warning}")
        for ch in step.children:
            dfs(ch)
    dfs(trace.root)
    return warnings

# ============================================================
# 14. 超级智能体主类 (整合所有模块)
# ============================================================
class SuperBrainAgent:
    def __init__(self, memory_dir=MEMORY_DIR):
        self.kb = KB()
        self.memory = PersistentMemory(memory_dir)
        self.kg = KnowledgeGraph()
        self.cognitive = CognitiveEngine(self.kb)
        self.dream = DreamEngine(self.kb, self.memory)
        self.skill_learner = AutoSkillLearner(self.kb, self.memory)
        self.supervisor = RealitySupervisor(self.kb, self.kg)
        self.kb.reality_supervisor = self.supervisor  # 供仲裁器访问
        self.arbiter = Arbiter(self.kb, memory_dir)
        self.mcp = MCPBridge(self)
        self.nlp = NLMatcher()
        self.bone = BoneGuard()
        self.last_result = None
        self.attempts = 0
        self._pending_context: Optional[Dict] = None  # multi-turn context
        self._pending_id: int = 0  # counter for pending questions
        self._show_trace: bool = False  # v0.12.0: 推理轨迹开关
        self._user_rules_file = os.path.join("rules", "user_learned.super")
        self._load_builtin()
        self._load_user_rules()     # v0.12.0: 启动时加载持久化规则
        self.dream.start()          # 梦境引擎后台启动

    def feed_answer(self, user_input: str) -> Optional[str]:
        """处理多轮苏格拉底式追问的回答。

        1. 检查 _pending_context 是否存在
        2. 解析回答作为事实加入 KB
        3. 继续之前的推理
        4. 返回答案或 None
        5. "cancel"/"取消" 清除 pending
        """
        if not self._pending_context:
            return None

        # 取消处理
        stripped = user_input.strip()
        if stripped.lower() in ("cancel", "取消"):
            self._pending_context = None
            return None

        goal = self._pending_context.get('goal')

        # 解析回答作为事实加入 KB
        try:
            term = parse_term(stripped)
            self.kb.add_fact(term)
            self.memory.remember({"type": "feed_answer", "content": str(term)})
        except Exception:
            fact = Term("fact", (stripped,))
            self.kb.add_fact(fact)
            self.memory.remember({"type": "feed_answer", "content": stripped})

        # 继续推理
        self.cognitive.needs_input = False
        if goal:
            binding, trace, think_log = self.arbiter.reason(goal, self.cognitive)
            if binding:
                self._pending_context = None
                self.last_result = (goal, binding)
                last_arb = self.arbiter.get_last_result()
                if last_arb:
                    self.arbiter.record_feedback(
                        method=last_arb.get('method_used', 'socratic'),
                        goal_type=last_arb.get('goal_type', 'unknown'),
                        accepted=True
                    )
                return str(binding)
            if self.cognitive.needs_input:
                # 仍有未回答的问题，保持 context
                self._pending_context = {'goal': goal}
                return None

        self._pending_context = None
        return None

    def _load_user_rules(self):
        """v0.12.0: 从 rules/user_learned.super 加载用户持久化规则"""
        if os.path.exists(self._user_rules_file):
            count = self.kb.load_rules_from_file(self._user_rules_file, source="user_learned")
            if count > 0:
                print(f"[规则] 已加载 {count} 条持久化规则 ({self._user_rules_file})")

    def _save_user_rules(self):
        """v0.12.0: 将用户学习的规则保存到 rules/user_learned.super"""
        count = self.kb.save_rules(self._user_rules_file, source_filter="user_learned")
        return count

    def _load_builtin(self):
        """加载内置事实和规则"""
        facts = [
            Term("parent", ("a", "b")), Term("parent", ("b", "c")),
            Term("parent", ("a", "d")), Term("parent", ("d", "e")),
            Term("knows", ("pangu", "logic")), Term("knows", ("pangu", "reasoning")),
            Term("knows", ("pangu", "self_awareness")),
            Term("category", ("logic", "reasoning_method")),
            Term("category", ("reasoning", "cognitive_skill")),
            Term("attribute", ("pangu", "version", "0.11.0")),
            Term("attribute", ("pangu", "sovereignty", "inviolable")),
        ]
        for f in facts:
            self.kb.add_fact(f)
            self.kg.add_entity(f.name, "predicate")
            for arg in f.args:
                if isinstance(arg, str) and not arg.startswith(('_','?')):
                    self.kg.add_entity(arg, "concept")

        rules = [
            Rule(Term("grandparent", ("_X", "_Z")), [Term("parent", ("_X", "_Y")), Term("parent", ("_Y", "_Z"))]),
            Rule(Term("ancestor", ("_X", "_Z")), [Term("parent", ("_X", "_Y")), Term("ancestor", ("_Y", "_Z"))]),
            Rule(Term("self_aware", ("_X",)), [Term("knows", ("_X", "self_awareness"))]),
            Rule(Term("can_reason", ("_X",)), [Term("knows", ("_X", "reasoning"))]),
        ]
        for r in rules:
            try: self.kb.add_rule(r, force=True)
            except ValueError: pass

        # 知识图谱关系
        self.kg.add_relation("pangu", "implements", "cognitive_engine", 1.0)
        self.kg.add_relation("pangu", "has", "self_awareness", 1.0)
        self.kg.add_relation("pangu", "version", "0.11.0", 1.0)

    def perceive(self, user_input: str) -> Optional[List[Term]]:
        # 早检查：多轮 pending context
        if self._pending_context is not None:
            lower_inp = user_input.strip().lower()

            # 取消
            if lower_inp in ("cancel", "取消"):
                self._pending_context = None
                print("[取消] 已取消推理")
                return []

            # 不拦截的命令列表
            bypass_prefixes = (
                "check_consistency", "健康", "health",
                "skills", "技能", "list_skills",
                "dream", "梦境",
                "dream_pending", "待确认", "dream_confirm", "dream_reject", "dream_compare",
                "help", "帮助",
            )
            if not any(lower_inp.startswith(p) for p in bypass_prefixes):
                ans = self.feed_answer(user_input)
                if ans is not None:
                    print(f"[推理] {ans}")
                else:
                    # feed_answer 可能又设回了 _pending_context（仍有问题）
                    if self._pending_context is not None:
                        if self.cognitive._pending_questions:
                            q = self.cognitive._pending_questions[0]
                            print(f"[苏格拉底] 还需要回答: {q}")
                return []

        # 骨骼守护
        bone_level = self.bone.check(user_input)
        if bone_level >= 2:
            print(f"[{self.bone.identity}] 拒绝：主权边界被侵犯。")
            self.memory.log_conversation("blocked", user_input)
            return None

        self.memory.log_conversation("user", user_input)
        facts = self.nlp.parse(user_input)

        for fact in facts:
            if fact.name == "learn_rule" and fact.args:
                try:
                    rule = parse_rule_from_string(str(fact.args[0]))
                    self.kb.add_rule(rule, force=True)
                    print(f"[学习] 已学习规则: {rule}")
                    self.memory.remember({"type": "learned_rule", "content": str(rule)})
                    # v0.12.0: 自动持久化用户规则
                    self._save_user_rules()
                except Exception as e:
                    print(f"[错误] {e}")
                return []

            # v0.12.0: 强制添加规则（跳过一致性警告）
            elif fact.name == "force_rule" and fact.args:
                try:
                    rule = parse_rule_from_string(str(fact.args[0]))
                    self.kb.add_rule(rule, force=True)
                    print(f"[强制] 已强制添加规则: {rule}")
                    self.memory.remember({"type": "force_rule", "content": str(rule)})
                    self._save_user_rules()
                except Exception as e:
                    print(f"[错误] {e}")
                return []

            # v0.12.0: 删除规则
            elif fact.name == "delete_rule" and fact.args:
                pred_name = str(fact.args[0])
                count = self.kb.delete_rules(pred_name)
                if count:
                    print(f"[删除] 已删除 {count} 条规则 (谓词: {pred_name})")
                    self._save_user_rules()
                else:
                    print(f"[删除] 未找到谓词 '{pred_name}' 的规则")
                return []

            elif fact.name == "check_consistency":
                report = self.kb.get_consistency_report()
                self._print_health(report)
                return []

            elif fact.name == "confirm" and self.last_result:
                goal, binding = self.last_result
                self.attempts += 1
                # 反馈仲裁器
                last_arbiter = self.arbiter.get_last_result()
                if last_arbiter:
                    self.arbiter.record_feedback(
                        method=last_arbiter.get('method_used', 'cot'),
                        goal_type=last_arbiter.get('goal_type', 'unknown'),
                        accepted=True
                    )
                    print(f"[仲裁] 已记录正反馈: {last_arbiter['method_used']} for {last_arbiter['goal_type']}")
                skill = self.skill_learner.evaluate_and_learn(goal, True, binding, self.attempts)
                if skill:
                    print(f"[技能] 自动创建技能: {skill['name']}")
                else:
                    print(f"[确认] 已记录正例: {binding}")
                self.last_result = None
                return []

            elif fact.name == "reject" and self.last_result:
                goal, binding = self.last_result
                self.attempts += 1
                # 反馈仲裁器
                last_arbiter = self.arbiter.get_last_result()
                if last_arbiter:
                    self.arbiter.record_feedback(
                        method=last_arbiter.get('method_used', 'cot'),
                        goal_type=last_arbiter.get('goal_type', 'unknown'),
                        accepted=False
                    )
                    print(f"[仲裁] 已记录负反馈: {last_arbiter['method_used']} for {last_arbiter['goal_type']} (降权)")
                skill = self.skill_learner.evaluate_and_learn(goal, False, binding, self.attempts)
                if skill:
                    print(f"[技能] 从失败中创建技能: {skill['name']}")
                self.last_result = None
                return []

            elif fact.name == "remember" and fact.args:
                try:
                    t = parse_term(str(fact.args[0]))
                    self.memory.remember({"type": "user_fact", "content": str(t)})
                    self.kb.add_fact(t)
                    self.kg.add_entity(t.name, "fact")
                    for arg in t.args:
                        if isinstance(arg, str) and not arg.startswith(('_','?')):
                            self.kg.add_entity(str(arg), "concept")
                            self.kg.add_relation(str(arg), "belongs_to", t.name, 0.5)
                    print(f"[记忆] 已存储: {t}")
                except: pass
                return []

            elif fact.name == "search" and fact.args:
                results = self.kg.search(str(fact.args[0]))
                if results:
                    print(f"[搜索] 找到 {len(results)} 条结果:")
                    for r in results[:5]:
                        print(f"  - {r}")
                else:
                    print("[搜索] 无结果")
                return []

            elif fact.name == "dream":
                dream_log = self.dream.dream_now()
                print(f"[梦境]\n{dream_log}")
                return []

            elif fact.name == "dream_pending":
                pending = self.dream.get_pending()
                if pending:
                    print(f"[梦境] 待确认项 ({len(pending)} 项):")
                    for i, p in enumerate(pending):
                        ts = time.strftime('%H:%M:%S', time.localtime(p.get('timestamp', 0)))
                        print(f"  [{i}] {p['description']} (可信度: {p.get('confidence', 0):.0%}) [{ts}]")
                    print("  输入 dream_confirm 确认全部，或 dream_reject N 拒绝某项")
                else:
                    print("[梦境] 无待确认项")
                return []

            elif fact.name == "dream_confirm":
                pending = self.dream.get_pending()
                if not pending:
                    print("[梦境] 无待确认项")
                    return []
                # 确认全部
                applied = 0
                for i in range(len(pending) - 1, -1, -1):
                    if self.dream.apply_pending(i):
                        applied += 1
                print(f"[梦境] 已确认 {applied} 项")
                return []

            elif fact.name == "dream_reject" and fact.args:
                try:
                    idx = int(fact.args[0])
                    if self.dream.reject_pending(idx):
                        print(f"[梦境] 已拒绝第 {idx} 项")
                    else:
                        print(f"[梦境] 无效索引 {idx}")
                except (ValueError, IndexError):
                    print("[梦境] 格式: dream_reject N")
                return []

            elif fact.name == "dream_compare" and fact.args:
                try:
                    idx = int(fact.args[0])
                    result = self.dream.compare_pending(idx)
                    print(result)
                except (ValueError, IndexError):
                    print("[梦境] 格式: dream_compare N")
                return []

            elif fact.name == "reset_arbiter":
                self.arbiter.reset_stats()
                print("[仲裁] 统计已重置")
                return []

            elif fact.name == "mcp_add" and len(fact.args) >= 2:
                caller_name = str(fact.args[0])
                level = str(fact.args[1])
                if level not in ('readonly', 'learn', 'admin'):
                    print(f"[MCP] 无效权限级别: {level}，可选: readonly/learn/admin")
                    return []
                token = self.mcp.generate_token(caller_name, level)
                print(f"[MCP] 已添加调用者 '{caller_name}' (权限: {level})")
                print(f"[MCP] 令牌: {token}")
                return []

            elif fact.name == "mcp_remove" and fact.args:
                caller_name = str(fact.args[0])
                if self.mcp.revoke_token(caller_name):
                    print(f"[MCP] 已移除调用者 '{caller_name}'")
                else:
                    print(f"[MCP] 未找到调用者 '{caller_name}'")
                return []

            elif fact.name == "restore_superseded":
                if fact.args and fact.args[0]:
                    name = str(fact.args[0])
                    if self.dream.restore_superseded(name):
                        print(f"[梦境] 已恢复规则: {name}")
                    else:
                        print(f"[梦境] 未找到被替代的规则: {name}")
                else:
                    rules = self.dream.get_superseded_rules()
                    if rules:
                        print("[梦境] 被替代的规则:")
                        for r in rules:
                            print(f"  - {r.head.name} (superseded)")
                        print("  输入 restore_rule <name> 恢复")
                    else:
                        print("[梦境] 无被替代的规则")
                return []

            elif fact.name == "mcp_list":
                callers = self.mcp.list_callers()
                if callers:
                    print(f"[MCP] 已注册调用者 ({len(callers)}):")
                    for c in callers:
                        print(f"  - {c['name']} ({c['level']})")
                else:
                    print("[MCP] 无注册调用者")
                return []

            elif fact.name == "list_skills":
                skills = self.memory.get_skills()
                if skills:
                    print(f"[技能] {len(skills)} 个技能:")
                    for s in skills:
                        print(f"  - {s.get('name')} (tags: {s.get('tags', [])})")
                else:
                    print("[技能] 无已学习技能")
                return []

            elif fact.name == "reason_with" and len(fact.args) >= 2:
                goal_str = str(fact.args[0])
                method_str = str(fact.args[1])
                try:
                    goal = parse_term(goal_str)
                    method = ReasoningMethod[method_str.upper()] if method_str.upper() in ReasoningMethod.__members__ else ReasoningMethod.COT
                    binding, trace, think_log = self.cognitive.reason(goal, method)
                    print(f"[推理] 方法: {method.value}")
                    binding_val = binding if binding else "无结果"
                    print(f"[推理] 结果: {binding_val}")
                    if think_log:
                        print(f"[推理过程]\n{think_log[:500]}")
                except Exception as e:
                    print(f"[推理错误] {e}")
                return []

            elif fact.name == "direct_query" and fact.args:
                # 直接查询: grandparent(a, _Who)
                goal = fact.args[0] if isinstance(fact.args[0], Term) else parse_term(str(fact.args[0]))
                binding, trace = self.kb.query_best_with_trace(goal)
                if binding:
                    print(f"[查询] {goal} => {binding}")
                    if self._show_trace and trace and trace.root:
                        print(f"[轨迹] 规则={trace.root.rule}, 事实={trace.root.fact}")
                    self.last_result = (goal, binding)
                else:
                    print(f"[查询] {goal} => 无结果")
                    # 尝试认知推理
                    cb, ct, clog = self.cognitive.reason(goal, ReasoningMethod.COT)
                    if cb:
                        print(f"[推理] {goal} => {cb}")
                        if self._show_trace and clog:
                            print(f"[推理过程]\n{clog[:500]}")
                        self.last_result = (goal, cb)
                    else:
                        print(f"[推理] {goal} => 无法推理")
                return []

            # v0.12.0 新命令
            elif fact.name == "query_all" and fact.args:
                try:
                    goal_term = fact.args[0] if isinstance(fact.args[0], Term) else parse_term(str(fact.args[0]))
                    all_sols = self.kb.query_all_solutions(goal_term)
                    if all_sols:
                        print(f"[全部解] {goal_term} — {len(all_sols)} 个解:")
                        for i, sol in enumerate(all_sols[:20]):
                            print(f"  [{i+1}] {sol}")
                        if len(all_sols) > 20:
                            print(f"  ... 共 {len(all_sols)} 个（显示前20）")
                    else:
                        print(f"[全部解] {goal_term} => 无解")
                except Exception as e:
                    print(f"[错误] {e}")
                return []

            elif fact.name == "list_facts":
                facts_list = self.kb.facts
                if facts_list:
                    print(f"[事实] 共 {len(facts_list)} 条:")
                    for f in facts_list[:30]:
                        print(f"  {f}")
                    if len(facts_list) > 30:
                        print(f"  ... 共 {len(facts_list)} 条（显示前30）")
                else:
                    print("[事实] 知识库为空")
                return []

            elif fact.name == "list_rules":
                rules_list = self.kb.rules
                if rules_list:
                    print(f"[规则] 共 {len(rules_list)} 条:")
                    for r in rules_list[:30]:
                        body_str = f" :- {', '.join(str(b) for b in r.body)}" if r.body else ""
                        reliable_mark = "" if r.reliable else " [!不可靠]"
                        print(f"  {r.head}{body_str}.{reliable_mark}")
                    if len(rules_list) > 30:
                        print(f"  ... 共 {len(rules_list)} 条（显示前30）")
                else:
                    print("[规则] 无规则")
                return []

            elif fact.name == "save_rules":
                count = self._save_user_rules()
                print(f"[规则] 已保存 {count} 条用户规则 → {self._user_rules_file}")
                return []

            elif fact.name == "load_rules" and fact.args:
                filepath = str(fact.args[0]).strip()
                if not filepath:
                    filepath = self._user_rules_file
                count = self.kb.load_rules_from_file(filepath)
                print(f"[规则] 已加载 {count} 条规则 ← {filepath}")
                return []

            elif fact.name == "toggle_trace" and fact.args:
                switch = str(fact.args[0]).lower()
                self._show_trace = switch in ("on", "开")
                status = "开启" if self._show_trace else "关闭"
                print(f"[轨迹] 推理轨迹显示已{status}")
                return []

            elif fact.name == "who_are_you":
                identity = self.memory.get_identity()
                print(f"[身份] 我是 {identity.get('name', '盘古')} (Pangu)")
                print(f"  版本: v{identity.get('version', '0.12.0')} 圆满")
                print(f"  主权: {identity.get('sovereignty', 'inviolable')}")
                print(f"  核心能力: 符号推理 · 16种认知架构 · 4D记忆 · 梦境引擎 · 知识图谱 · MCP桥接")
                print(f"  身份不可侵犯，主权归用户所有。")
                return []

            elif fact.name == "show_help":
                self._print_help()
                return []

        return facts

    def _print_health(self, report: HealthReport):
        print(f"\n{'='*40}")
        print(f"  盘古 v0.12.0 健康报告")
        print(f"{'='*40}")
        superseded_count = sum(1 for r in self.kb.rules if r.superseded_by is not None)
        print(f"  规则: {report.total_rules}  事实: {report.total_facts}")
        if superseded_count:
            print(f"  已替代规则: {superseded_count}")
        if report.orphans: print(f"  孤儿规则: {[str(r) for r in report.orphans[:3]]}")
        if report.cycles: print(f"  循环: {report.cycles}")
        print(f"  可信度: {self.supervisor.get_trust_score():.2%}")
        print(f"  技能数: {len(self.memory.get_skills())}")
        print(f"  梦境周期: 活跃")
        print(f"  轨迹显示: {'开' if self._show_trace else '关'}")
        print(f"{'='*40}\n")

    def _print_help(self):
        print("""
盘古 v0.12.0 "圆满" 命令参考
══════════════════════════════════════════════════════════
【推理查询】
  grandparent(a, _Who)         直接查询（变量以 _ 或 ? 开头）
  查询全部 grandparent(a, _X)  返回所有解
  reason P(x,_Y) via tot       指定推理方法 (cot/tot/react/mcts/
                                socratic/decomp/refine/recursive/
                                analogy/abductive/inductive/dialectic/
                                counter/stepback/contradict/ensemble)

【学习规则】
  学习规则 父亲(张三, 张父).               显式学习事实
  学习规则 祖父(_X,_Z) :- 父亲(_X,_Y), 父亲(_Y,_Z).  学习规则
  强制添加规则 orphan(_X) :- b(_X).        跳过一致性警告强制添加
  删除规则 <谓词名>                         删除该谓词所有规则

【知识库管理】
  列出事实                      列出所有事实（前30条）
  列出规则                      列出所有规则（前30条）
  保存规则                      持久化用户规则到文件
  加载规则 [文件名]              从文件加载规则
  检查一致性                    输出规则库健康报告

【记忆与存储】
  记住 母亲(张三, 张母).        存储事实到持久记忆
  confirm / 正确                确认上一次推理（正反馈+技能学习）
  reject / 错误                 拒绝上一次推理（负反馈+仲裁降权）

【知识图谱】
  搜索 pangu                    混合搜索知识图谱

【梦境引擎】
  梦境                          立即触发梦境反思
  待确认                        查看梦境待确认规则
  梦境确认                      确认全部梦境规则
  梦境拒绝 N                    拒绝第 N 条梦境规则
  梦境对比 N                    对比第 N 条新旧规则差异

【技能】
  技能                          列出自动创建的技能

【MCP 协议】
  mcp_add <名称> <readonly|learn|admin>  注册调用者（持久化）
  mcp_remove <名称>                      移除调用者
  mcp_list                               列出所有调用者

【系统】
  你是谁                        显示盘古身份
  显示轨迹 on / off             开关推理轨迹详细日志
  重置仲裁                      重置仲裁器历史统计
  帮助 / help                   显示本帮助
  exit                          退出
══════════════════════════════════════════════════════════
""")

    def _print_health(self, report: HealthReport):
        print(f"\n{'='*40}")
        print(f"  盘古 v0.12.0 健康报告")
        print(f"{'='*40}")
        superseded_count = sum(1 for r in self.kb.rules if r.superseded_by is not None)
        print(f"  规则: {report.total_rules}  事实: {report.total_facts}")
        if superseded_count:
            print(f"  已替代规则: {superseded_count}")
        if report.orphans: print(f"  孤儿规则: {[str(r) for r in report.orphans[:3]]}")
        if report.cycles: print(f"  循环: {report.cycles}")
        print(f"  可信度: {self.supervisor.get_trust_score():.2%}")
        print(f"  技能数: {len(self.memory.get_skills())}")
        print(f"  梦境周期: 活跃")
        print(f"  轨迹显示: {'开' if self._show_trace else '关'}")
        print(f"{'='*40}\n")

    def decide(self, goal=Term("query")) -> str:
        # 使用仲裁器选择最优推理方法
        self.attempts += 1
        self.cognitive.needs_input = False  # 重置
        binding, trace, think_log = self.arbiter.reason(goal, self.cognitive)

        # 记录推理结果供反馈使用
        last_arb = self.arbiter.get_last_result()
        self.last_reasoning = {
            'method_used': last_arb.get('method_used', 'cot') if last_arb else 'cot',
            'goal_type': last_arb.get('goal_type', 'unknown') if last_arb else 'unknown',
        }

        # 苏格拉底多轮交互：仲裁器无结果且需要用户输入
        if binding is None and self.cognitive.needs_input:
            self._pending_context = {'goal': goal}
            self.cognitive.needs_input = False
            if self.cognitive._pending_questions:
                q = self.cognitive._pending_questions[0]
                return f"我需要更多信息。\n[苏格拉底] {q}"
            return "我需要更多信息。"

        if binding is None:
            # 退化为 CoT
            binding, trace, think_log = self.cognitive.reason(goal, ReasoningMethod.COT)

        if binding is None:
            similar = self.memory.recall(str(goal))
            if similar:
                return f"无法推理。类似记忆: {similar[0].get('content', '')[:100]}"
            return "无法推理。缺少相关信息。"

        # 现实监督
        validation = self.supervisor.validate(goal, binding)
        warnings = collect_warnings(trace)
        if warnings:
            validation['warnings'].extend(warnings)

        # 提取答案
        ans = str(binding)
        if validation['hallucination_risk'] > 0.5:
            ans += f"\n[警告] 推理可信度: {(1-validation['hallucination_risk']):.0%}"

        self.last_result = (goal, binding)
        return ans

    def act(self, msg: str):
        print(f"[{self.bone.identity}] {msg}")
        self.memory.log_conversation("assistant", msg)

    def run(self, user_input: str):
        self.bone.assert_identity()
        perceived = self.perceive(user_input)
        if perceived is None or len(perceived) == 0:
            return
        self.act(self.decide(perceived[0]))

    def process_mcp(self, request: Dict) -> Dict:
        """MCP协议入口"""
        return self.mcp.process_request(request)

# ============================================================
# 15. 主程序入口
# ============================================================
if __name__ == "__main__":
    import sys
    import os

    # 修复Windows编码
    if sys.platform == 'win32':
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    agent = SuperBrainAgent()

    # MCP 模式
    if len(sys.argv) > 1 and sys.argv[1] == '--mcp':
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line)
                response = agent.process_mcp(request)
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except (EOFError, KeyboardInterrupt):
                break
    else:
        print("盘古 v0.12.0 [圆满] 已启动 | 16种认知架构 | 4D记忆 | 梦境引擎 | 知识图谱 | MCP桥接")
        print("输入 exit 退出。输入 帮助 或 help 查看命令。")
        while True:
            try:
                inp = input("> ")
                if inp.lower() == 'exit':
                    agent.dream.stop()
                    break
                if inp.lower() in ('help', '帮助', 'h', '?'):
                    agent._print_help()
                    continue
                agent.run(inp)
            except KeyboardInterrupt:
                agent.dream.stop()
                break
            except Exception as e:
                print(f"错误: {e}")
