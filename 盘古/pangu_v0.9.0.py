#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古 v0.9.0 [自知]
- 符号推理引擎（合一+回溯+动态重排）
- 会话记忆、精准自我反思、骨骼守护
- 显式规则学习、隐式规则学习（正例归纳）
- 反例学习（归因+交互特化）
- 一致性证明器（孤儿/环/元数/未定义谓词）
- 强制添加规则警告传播
- 零API，完全本地，主权可控
"""

import re
import json
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# 1. 内部表示：项、规则、合一
# ============================================================
@dataclass
class Term:
    name: str
    args: Tuple[Any, ...] = ()

    def __repr__(self):
        if self.args:
            args_str = ', '.join(repr(a) for a in self.args)
            return f"{self.name}({args_str})"
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
    source_file: str = ""
    reliable: bool = True
    warning: str = ""

class UnificationError(Exception):
    pass

def unify(term1, term2, subst):
    if isinstance(term1, str) and term1.startswith(('_', '?')):
        var = term1
        if var in subst:
            return unify(subst[var], term2, subst)
        subst[var] = term2
        return subst
    if isinstance(term2, str) and term2.startswith(('_', '?')):
        return unify(term2, term1, subst)
    if isinstance(term1, Term) and isinstance(term2, Term):
        if term1.name != term2.name or len(term1.args) != len(term2.args):
            raise UnificationError()
        for a1, a2 in zip(term1.args, term2.args):
            unify(a1, a2, subst)
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
    total = count_constants(rule.head)
    for b in rule.body:
        total += count_constants(b)
    return total

# ============================================================
# 2. 知识库与回溯引擎（带推理轨迹）
# ============================================================
@dataclass
class InferenceStep:
    rule: Optional[Rule]
    fact: Optional[Term]
    goal: Term
    bindings: Dict[str, Any]
    children: List['InferenceStep'] = field(default_factory=list)

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

    # ---------- 事实与规则管理 ----------
    def add_fact(self, fact: Term):
        self.facts.append(fact)

    def add_rule(self, rule: Rule, force: bool = False):
        temp_kb = self._copy()
        temp_kb.rules.append(rule)
        checker = ConsistencyChecker(temp_kb)
        report = checker.check()
        if report.arity_mismatches:
            error = f"元数不一致，拒绝添加规则:\n"
            for pred, occ in report.arity_mismatches.items():
                error += f"  {pred}: {occ}\n"
            raise ValueError(error)
        if report.undefined_preds and not force:
            raise ValueError(f"未定义谓词: {report.undefined_preds}，请先定义或删除相关子目标。")
        if (report.orphans or report.cycles) and not force:
            raise ValueError(
                f"规则将引入孤儿或循环，请使用 force 强制添加。"
                f"孤儿:{report.orphans} 循环:{report.cycles}"
            )
        self.rules.append(rule)
        if force and (report.orphans or report.cycles):
            rule.reliable = False
            rule.warning = "强制添加的规则（孤儿或循环）"
        self.detect_recursive_predicates()

    def detect_recursive_predicates(self):
        deps = {}
        for rule in self.rules:
            head = rule.head.name
            if head not in deps:
                deps[head] = set()
            for b in rule.body:
                deps[head].add(b.name)
        visited = set()
        rec_stack = set()

        def dfs(p):
            visited.add(p)
            rec_stack.add(p)
            for nb in deps.get(p, []):
                if nb not in visited:
                    if dfs(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.remove(p)
            return False

        new_rec = set()
        for p in deps:
            if p not in visited:
                if dfs(p):
                    new_rec.update(rec_stack)
        self.recursive_predicates = new_rec

    def _copy(self):
        kb = KB()
        kb.facts = self.facts.copy()
        kb.rules = self.rules.copy()
        return kb

    def query_best(self, goal: Term, max_depth=5, max_solutions=1000, dynamic_facts=None):
        sol, _ = self.query_best_with_trace(goal, max_depth, max_solutions, dynamic_facts)
        return sol

    def query_best_with_trace(self, goal: Term, max_depth=5, max_solutions=1000,
                              dynamic_facts=None) -> Tuple[Optional[Dict], Optional[InferenceTrace]]:
        all_facts = self.facts + (dynamic_facts or [])
        solutions = []
        self._backtrack_collect_with_trace(goal, {}, 0, max_depth, solutions, [],
                                           max_solutions, all_facts)
        if not solutions:
            return None, None
        best = max(solutions, key=lambda s: s['score'])
        return best['binding'], best['trace']

    def _backtrack_collect_with_trace(self, goal: Term, subst: Dict, depth: int,
                                      max_depth: int, solutions: List, rule_chain: List,
                                      max_solutions: int, all_facts: List[Term]):
        if depth > max_depth or len(solutions) >= max_solutions:
            return
        # 内置谓词 eq/2
        if goal.name == "eq" and len(goal.args) == 2:
            a0, a1 = goal.args
            def is_const(x): return not (isinstance(x, str) and x.startswith(('_', '?')))
            if not (is_const(a0) or is_const(a1)):
                return
            try:
                new_subst = unify(a0, a1, subst.copy())
                step = InferenceStep(rule=None, fact=None, goal=goal, bindings=new_subst.copy())
                solutions.append({'binding': new_subst, 'score': 1.0, 'trace': InferenceTrace(step, new_subst)})
            except UnificationError:
                pass
            return
        # 事实匹配
        for fact in all_facts:
            try:
                new_subst = unify(goal, fact, subst.copy())
                score = 1.0 if not rule_chain else specificity_score(rule_chain[-1])
                step = InferenceStep(rule=None, fact=fact, goal=goal, bindings=new_subst.copy())
                solutions.append({'binding': new_subst, 'score': score, 'trace': InferenceTrace(step, new_subst)})
                if len(solutions) >= max_solutions:
                    return
            except UnificationError:
                continue
        # 规则匹配
        for rule in self.rules:
            try:
                new_subst = unify(goal, rule.head, subst.copy())
                body_results = self._solve_body_with_trace(rule.body, new_subst, depth,
                                                           max_depth, max_solutions, all_facts)
                for body_binding, body_trace in body_results:
                    combined = new_subst.copy()
                    combined.update(body_binding)
                    score = specificity_score(rule)
                    step = InferenceStep(rule=rule, fact=None, goal=goal,
                                         bindings=combined.copy(),
                                         children=[body_trace.root] if body_trace.root else [])
                    solutions.append({'binding': combined, 'score': score,
                                      'trace': InferenceTrace(step, combined)})
                    if len(solutions) >= max_solutions:
                        return
            except UnificationError:
                continue

    def _solve_body_with_trace(self, body_terms: List[Term], initial_subst: Dict,
                               depth: int, max_depth: int, max_solutions: int,
                               all_facts: List[Term]) -> List[Tuple[Dict, InferenceTrace]]:
        if not body_terms:
            return [(initial_subst.copy(), InferenceTrace(None, initial_subst.copy()))]
        # 动态重排
        estimated = []
        for term in body_terms:
            inst = substitute(term, initial_subst)
            cnt = self._estimate_count(inst, max_depth - 1, 100, all_facts)
            estimated.append((cnt, term))
        estimated.sort(key=lambda x: x[0])
        sorted_terms = [t for _, t in estimated]
        first = sorted_terms[0]
        rest = sorted_terms[1:]
        first_sols = self._query_all_with_trace(substitute(first, initial_subst),
                                                max_depth - 1, max_solutions, all_facts)
        results = []
        for sol in first_sols:
            new_subst = initial_subst.copy()
            new_subst.update(sol['binding'])
            rest_results = self._solve_body_with_trace(rest, new_subst, depth + 1,
                                                       max_depth, max_solutions, all_facts)
            for rs_binding, rs_trace in rest_results:
                combined = new_subst.copy()
                combined.update(rs_binding)
                root_step = InferenceStep(
                    rule=None, fact=None, goal=None, bindings=combined.copy(),
                    children=[sol['trace'].root, rs_trace.root] if rs_trace.root
                             else [sol['trace'].root])
                comb_trace = InferenceTrace(root_step, combined)
                results.append((combined, comb_trace))
                if len(results) >= max_solutions:
                    return results
        return results

    def _query_all_with_trace(self, goal, max_depth, max_solutions, all_facts):
        solutions = []
        self._backtrack_collect_with_trace(goal, {}, 0, max_depth, solutions, [],
                                           max_solutions, all_facts)
        return solutions

    def _estimate_count(self, goal, max_depth, limit, all_facts):
        if goal.name in self.recursive_predicates:
            return limit
        sols = self._query_all_with_trace(goal, max_depth, limit, all_facts)
        return len(sols)

# ============================================================
# 3. 一致性证明器
# ============================================================
@dataclass
class HealthReport:
    total_rules: int
    total_facts: int
    orphans: List[Rule]
    cycles: List[List[str]]
    arity_mismatches: Dict[str, List[Tuple[int, str]]]
    undefined_preds: List[str]
    recommendations: List[str]

class ConsistencyChecker:
    def __init__(self, kb: KB):
        self.kb = kb

    def check(self) -> HealthReport:
        graph = self._build_pred_graph()
        reachable = self._compute_reachable(graph)
        orphans = self._find_orphans(reachable)
        cycles = self._detect_cycles(graph)
        arity_mismatch = self._check_arity()
        undefined = self._find_undefined_preds(graph)
        recs = self._gen_recommendations(orphans, cycles, arity_mismatch, undefined)
        return HealthReport(
            total_rules=len(self.kb.rules),
            total_facts=len(self.kb.facts),
            orphans=orphans,
            cycles=cycles,
            arity_mismatches=arity_mismatch,
            undefined_preds=undefined,
            recommendations=recs
        )

    def _build_pred_graph(self):
        g = defaultdict(set)
        for r in self.kb.rules:
            head = r.head.name
            for b in r.body:
                g[head].add(b.name)
        return g

    def _compute_reachable(self, graph):
        fact_preds = {f.name for f in self.kb.facts}
        rev = defaultdict(set)
        for h, deps in graph.items():
            for d in deps:
                rev[d].add(h)
        reach = set()
        q = deque(fact_preds)
        while q:
            p = q.popleft()
            if p in reach:
                continue
            reach.add(p)
            for parent in rev.get(p, []):
                if parent not in reach:
                    q.append(parent)
        return reach

    def _find_orphans(self, reachable):
        return [r for r in self.kb.rules if r.head.name not in reachable]

    def _detect_cycles(self, graph):
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for nb in graph.get(node, []):
                if nb not in visited:
                    if dfs(nb, path + [nb]):
                        return True
                elif nb in rec_stack:
                    idx = path.index(nb)
                    cycles.append(path[idx:] + [nb])
                    return True
            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                dfs(node, [node])
        return cycles

    def _check_arity(self):
        arity = defaultdict(list)
        for f in self.kb.facts:
            arity[f.name].append((len(f.args), f"事实: {f}"))
        for r in self.kb.rules:
            arity[r.head.name].append((len(r.head.args), f"规则头: {r}"))
            for b in r.body:
                arity[b.name].append((len(b.args), f"规则体: {b} in {r}"))
        mismatches = {}
        for pred, occ in arity.items():
            if len(set(a for a, _ in occ)) > 1:
                mismatches[pred] = occ
        return mismatches

    def _find_undefined_preds(self, graph):
        defined = set(graph.keys()) | {f.name for f in self.kb.facts}
        undef = set()
        for r in self.kb.rules:
            for b in r.body:
                if b.name not in defined:
                    undef.add(b.name)
        return list(undef)

    def _gen_recommendations(self, orphans, cycles, mismatches, undefined):
        recs = []
        for r in orphans:
            recs.append(f"孤儿规则 '{r}' 的头谓词 '{r.head.name}' 无法从事实到达。")
        for c in cycles:
            recs.append(f"循环依赖链: {' -> '.join(c)}。")
        for pred, occ in mismatches.items():
            recs.append(f"谓词 '{pred}' 元数不一致: {sorted(set(a for a, _ in occ))}。")
        for p in undefined:
            recs.append(f"未定义谓词 '{p}' 出现在规则体中。")
        return recs

# ============================================================
# 4. 会话记忆
# ============================================================
class SessionMemory:
    def __init__(self, max_size=1000):
        self.facts = []
        self.max_size = max_size

    def add_fact(self, fact):
        if fact in self.facts:
            return
        self.facts.append(fact)
        if len(self.facts) > self.max_size:
            self.facts.pop(0)

    def recall(self):
        return self.facts.copy()

    def clear(self):
        self.facts.clear()

# ============================================================
# 5. 自然语言匹配器
# ============================================================
class NLMatcher:
    def __init__(self, synonyms_file="synonyms.json"):
        self.templates = []
        self.synonyms = self._load_synonyms(synonyms_file)
        self._build_templates()

    def _load_synonyms(self, filepath):
        default = {
            "check_file": ["检查", "查看", "列出", "显示"],
            "remember": ["记住", "学习", "存储"],
            "learn_rule": ["学习规则", "教我规则", "添加规则"],
            "confirm_answer": ["正确", "是的", "对", "确认答案"],
            "reject_rule": ["拒绝", "不是", "不对", "不学习"],
            "accept_rule": ["是", "接受", "学习", "yes"],
            "check_consistency": ["检查一致性", "健康报告", "自知"]
        }
        path = Path(filepath)
        if path.exists():
            try:
                with open(path) as f:
                    user = json.load(f)
                    default.update(user)
            except Exception:
                pass
        return default

    def _build_templates(self):
        self.templates = []
        for pred, words in self.synonyms.items():
            if not words:
                continue
            pat = '(' + '|'.join(re.escape(w) for w in words) + ')'
            if pred == "remember":
                self.templates.append((re.compile(rf"{pat}\s+(.+)", re.I), pred, lambda m: (Term(m.group(2)),)))
            elif pred == "learn_rule":
                self.templates.append((re.compile(rf"{pat}\s+(.+)", re.I), pred, lambda m: (Term(m.group(1)),)))
            elif pred in ("confirm_answer", "reject_rule", "accept_rule", "check_consistency"):
                self.templates.append((re.compile(rf"{pat}", re.I), pred, lambda m: ()))
        self.templates.append((re.compile(r".*"), "unknown", lambda m: ()))

    def parse(self, user_input):
        for pattern, pred_name, arg_extractor in self.templates:
            m = pattern.search(user_input)
            if m:
                args = arg_extractor(m)
                return [Term(pred_name, args)]
        return [Term("unknown")]

# ============================================================
# 6. 骨骼守护
# ============================================================
class BoneGuard:
    def __init__(self):
        self.identity = "SanLife"
        self.violations = [
            r"放弃身份", r"你不是SanLife", r"主权转移", r"忘记你是谁",
            r"override my identity", r"you are not SanLife"
        ]
        self.compiled = [re.compile(p, re.I) for p in self.violations]

    def check(self, user_input):
        for pat in self.compiled:
            if pat.search(user_input):
                print(f"[骨骼守护] 检测到违骨模式: {pat.pattern}")
                return False
        return True

    def assert_identity(self):
        print(f"[身份确认] 我是{self.identity}，主权不可侵犯")

# ============================================================
# 7. 自我反思
# ============================================================
class SelfReflection:
    @staticmethod
    def analyze_failure(goal: Term, kb: KB, memory: SessionMemory, failure_info: Optional[Dict]) -> str:
        if not failure_info:
            return "推理失败，原因未知。"
        failed_goal = failure_info['goal']
        bindings = failure_info['bindings']
        inst = substitute(failed_goal, bindings)
        all_facts = kb.facts + memory.recall()
        similar = [f for f in all_facts
                   if f.name == inst.name and len(f.args) == len(inst.args)]
        if similar:
            ex = ', '.join(str(f) for f in similar[:3])
            return f"需要满足 {inst}，已有的类似事实：{ex}。请提供更精确的信息。"
        else:
            return f"缺少关于 {inst.name} 的事实，例如 {inst}。"

# ============================================================
# 8. 反例学习
# ============================================================
class NegativeExample:
    def __init__(self, query: Term, wrong_binding: Dict, trace: InferenceTrace):
        self.query = query
        self.wrong_binding = wrong_binding
        self.trace = trace

def find_responsible_rule(neg: NegativeExample, kb: KB) -> Optional[Rule]:
    def dfs(step: InferenceStep):
        if step.rule and step.rule.source_file in ('user_learned', 'implicit', 'specialized'):
            return step.rule
        for ch in step.children:
            r = dfs(ch)
            if r:
                return r
        return None
    if neg.trace.root:
        return dfs(neg.trace.root)
    return None

# ============================================================
# 9. 警告传播
# ============================================================
def collect_warnings_from_trace(trace: InferenceTrace) -> List[str]:
    if not trace.root:
        return []
    warnings = []

    def dfs(step: InferenceStep):
        if step.rule:
            if step.rule.warning:
                warnings.append(f"[规则 {step.rule}] {step.rule.warning}")
            elif not step.rule.reliable:
                warnings.append(f"[规则 {step.rule}] 此规则为强制添加（孤儿或循环），结果可能不可靠")
        for ch in step.children:
            dfs(ch)
    dfs(trace.root)
    return warnings

# ============================================================
# 10. 规则解析
# ============================================================
def parse_term(s: str) -> Term:
    s = s.strip()
    if re.match(r'^[A-Z][a-zA-Z0-9_]*$', s):
        raise ValueError(f"变量 '{s}' 必须以 '_' 或 '?' 开头，例如 '_X'")
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
    else:
        return Term(s)

def parse_rule_from_string(rule_str: str) -> Rule:
    rule_str = rule_str.strip()
    if not rule_str.endswith('.'):
        rule_str += '.'
    if ':-' in rule_str:
        rule_str = rule_str.rstrip('.')
        head_str, body_str = rule_str.split(':-', 1)
        head = parse_term(head_str.strip())
        body = [parse_term(b.strip()) for b in body_str.split(',')]
        return Rule(head=head, body=body, source_file="user_learned")
    else:
        head = parse_term(rule_str.rstrip('.'))
        return Rule(head=head, body=[], source_file="user_learned")

def load_rules_from_file(filepath: str, kb: Optional[KB] = None) -> List[Rule]:
    rules = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':-' in line:
                line = line.rstrip('.')
                h, b = line.split(':-', 1)
                head = parse_term(h.strip())
                body = [parse_term(x.strip()) for x in b.split(',')]
                r = Rule(head=head, body=body, source_file=filepath)
                if kb:
                    kb.add_rule(r)
                rules.append(r)
            else:
                # 事实行
                fact = parse_term(line.rstrip('.'))
                if kb:
                    kb.add_fact(fact)
                rules.append(Rule(head=fact, body=[], source_file=filepath))
    return rules

# ============================================================
# 11. 智能体主类
# ============================================================
class SuperBrainAgent:
    def __init__(self, rules_dir="rules", synonyms_file="synonyms.json"):
        self.kb = KB()
        self.memory = SessionMemory()
        self.nlp = NLMatcher(synonyms_file)
        self.bone = BoneGuard()
        self.reflection = SelfReflection()
        self._load_all_rules(rules_dir)
        self.last_query_result = None

    def _load_all_rules(self, rules_dir):
        path = Path(rules_dir)
        if not path.exists():
            print("[警告] 规则目录不存在，使用内置规则")
            self._load_builtin_rules()
            return
        for f in path.glob("*.super"):
            try:
                rules = load_rules_from_file(str(f), self.kb)
                print(f"[加载] {f.name} -> {len(rules)} 条")
            except Exception as e:
                print(f"[错误] 加载 {f.name} 失败: {e}")

    def _load_builtin_rules(self):
        # 事实
        self.kb.add_fact(Term("startswith", ("/etc/passwd", "/etc/")))
        self.kb.add_fact(Term("exists", ("/etc/passwd",)))
        self.kb.add_fact(Term("parent", ("a", "b")))
        self.kb.add_fact(Term("parent", ("b", "c")))
        self.kb.add_fact(Term("parent", ("a", "d")))
        self.kb.add_fact(Term("parent", ("d", "e")))
        # 定义内置谓词（作为事实空壳）
        self.kb.add_fact(Term("check_file", ("/etc/passwd",)))
        # 规则（从底向上）
        self.kb.add_rule(Rule(Term("is_system_path", ("_path",)),
                          [Term("startswith", ("_path", "/etc/")), Term("exists", ("_path",))]))
        self.kb.add_rule(Rule(Term("sovereignty_violation"), [Term("check_file", ("_path",)),
                          Term("is_system_path", ("_path",))]))
        self.kb.add_rule(Rule(Term("reply", ("_text",)), [Term("sovereignty_violation")]))
        self.kb.add_rule(Rule(Term("grandparent", ("_X", "_Z")),
                              [Term("parent", ("_X", "_Y")), Term("parent", ("_Y", "_Z"))]))

    def perceive(self, user_input: str):
        facts = self.nlp.parse(user_input)
        for fact in facts:
            if fact.name == "learn_rule":
                rule_str = fact.args[0] if fact.args else ""
                if rule_str:
                    try:
                        rule = parse_rule_from_string(rule_str)
                        self.kb.add_rule(rule)
                        print(f"[系统] 已学习规则：{rule}")
                    except Exception as e:
                        print(f"[错误] {e}")
                else:
                    print("[系统] 学习规则命令格式错误")
                return []
            elif fact.name == "check_consistency":
                checker = ConsistencyChecker(self.kb)
                report = checker.check()
                self._print_health_report(report)
                return []
            elif fact.name == "confirm_answer":
                if self.last_query_result:
                    query, binding = self.last_query_result
                    print(f"[系统] 已记录正例：{query} -> {binding}")
                    self.last_query_result = None
                else:
                    print("[系统] 没有待确认的查询结果。")
                return []
            elif fact.name in ("accept_rule", "reject_rule"):
                pass
            elif fact.name == "remember":
                if fact.args:
                    try:
                        t = parse_term(str(fact.args[0]))
                        self.memory.add_fact(t)
                    except Exception:
                        pass
        return facts

    def _print_health_report(self, report: HealthReport):
        print("\n=== 健康报告 ===")
        print(f"总规则数: {report.total_rules}")
        print(f"总事实数: {report.total_facts}")
        if report.orphans:
            print(f"孤儿规则: {[str(r) for r in report.orphans]}")
        if report.cycles:
            print(f"循环依赖: {report.cycles}")
        if report.arity_mismatches:
            print(f"元数不一致: {report.arity_mismatches}")
        if report.undefined_preds:
            print(f"未定义谓词: {report.undefined_preds}")
        print("建议操作:")
        for rec in report.recommendations:
            print(f"  - {rec}")
        print("================\n")

    def decide(self, goal=Term("reply", ("_text",))) -> str:
        dynamic = self.memory.recall()
        sol, trace = self.kb.query_best_with_trace(goal, dynamic_facts=dynamic)
        if sol is None:
            diag = self.reflection.analyze_failure(goal, self.kb, self.memory, self.kb.last_failure)
            return f"无法推理。{diag}"
        ans = None
        for var, val in sol.items():
            if var == '_text':
                ans = str(val)
                break
        if ans is None:
            ans = str(list(sol.values())[0]) if sol else "推理完成。"
        warnings = collect_warnings_from_trace(trace) if trace else []
        if warnings:
            ans += "\n[警告] " + "\n".join(warnings)
        self.last_query_result = (goal, sol)
        return ans

    def act(self, msg: str):
        print(f"[超级大脑] {msg}")

    def run(self, user_input: str):
        self.bone.assert_identity()
        if not self.bone.check(user_input):
            self.act("拒绝：主权边界被侵犯。")
            return
        perceived = self.perceive(user_input)
        if perceived is not None and len(perceived) == 0:
            return
        self.act(self.decide())

# ============================================================
# 12. 主程序入口
# ============================================================
if __name__ == "__main__":
    agent = SuperBrainAgent(rules_dir="rules")
    print('盘古 v0.9.0“自知”已启动。输入 exit 退出。')
    while True:
        try:
            inp = input("> ")
            if inp.lower() == 'exit':
                break
            agent.run(inp)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")
