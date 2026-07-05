"""SuperBrainAgent 轻量桥接 — Fact 注入 KB + Arbiter 多规则冲突裁决。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from symbolic import (
    load_symbolic_kb,
    structure_to_facts,
    _format_deduction,
    _collect_matching_rules,
    _rule_priority,
)

_PANGU_PATH = Path(__file__).resolve().parent / "pangu_v0.11.0.py"
_pangu_module = None


def _load_pangu():
    global _pangu_module
    if _pangu_module is not None:
        return _pangu_module
    spec = importlib.util.spec_from_file_location("pangu_core", _PANGU_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pangu core from {_PANGU_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pangu_core"] = mod
    spec.loader.exec_module(mod)
    _pangu_module = mod
    return mod


def _tags_to_terms(tags: Set[str]):
    pangu = _load_pangu()
    return [pangu.Term(tag, ()) for tag in sorted(tags)]


def _inject_structure_terms(kb, structure: Dict[str, Any], logic_kb: Dict[str, Any]) -> None:
    """注入缠论结构 Term 事实。"""
    pangu = _load_pangu()
    last_stroke = logic_kb.get("last_stroke")
    if last_stroke:
        kb.add_fact(
            pangu.Term(
                "stroke_at",
                (
                    str(last_stroke.get("index", "")),
                    str(last_stroke.get("direction", "")),
                    str(last_stroke.get("end_price", "")),
                ),
            )
        )
    pivot = logic_kb.get("active_pivot")
    if pivot:
        kb.add_fact(
            pangu.Term(
                "pivot_zone",
                (str(pivot.get("zg", "")), str(pivot.get("zd", ""))),
            )
        )
    div = logic_kb.get("divergence")
    if div:
        kb.add_fact(
            pangu.Term(
                "divergence_at",
                (str(div.get("kind", "")), str(div.get("bar_index", "")), str(div.get("reason", ""))),
            )
        )
    sig = logic_kb.get("last_signal")
    if sig:
        kb.add_fact(
            pangu.Term(
                "signal_at",
                (str(sig.get("kind", "")), str(sig.get("bar_index", "")), str(sig.get("reason", ""))),
            )
        )


def _load_inference_rules(kb, rules: List[dict]) -> None:
    """将 symbolic_kb 规则转为 KB Rule（head=market_state/2）。"""
    pangu = _load_pangu()
    for rule in rules:
        state = rule["state_code"]
        conf = str(rule.get("confidence", 0.7))
        body = []
        for tag in rule.get("requires_all") or []:
            body.append(pangu.Term(tag, ()))
        if rule.get("requires_any"):
            for tag in rule["requires_any"]:
                r = pangu.Rule(
                    head=pangu.Term("market_state", (state, conf)),
                    body=[pangu.Term(tag, ()), pangu.Term("eq", (conf, conf))],
                    source=f"chanlun:{rule['id']}",
                    reliable=True,
                )
                try:
                    kb.add_rule(r, force=True)
                except ValueError:
                    kb.add_fact(pangu.Term("market_state", (state, conf)))
            continue
        if not body:
            kb.add_fact(pangu.Term("market_state", (state, conf)))
            continue
        r = pangu.Rule(
            head=pangu.Term("market_state", (state, conf)),
            body=body,
            source=f"chanlun:{rule['id']}",
            reliable=True,
        )
        try:
            kb.add_rule(r, force=True)
        except ValueError:
            kb.add_fact(pangu.Term("market_state", (state, conf)))


class SuperBrainBridge:
    """缠论结构 → SuperBrain KB + Arbiter 演绎。"""

    def __init__(self, kb_path: Optional[Path] = None) -> None:
        self.symbolic_kb = load_symbolic_kb(kb_path)
        self.rules = self.symbolic_kb.get("rules", [])

    def deduce(
        self,
        structure: Dict[str, Any],
        symbolic_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pangu = _load_pangu()
        _, logic_kb = structure_to_facts(structure)
        tags = set(logic_kb.get("tags") or [])
        candidates = _collect_matching_rules(tags, self.rules)

        deduction_path: List[str] = list((symbolic_result or {}).get("deduction_path") or [])
        for fact in logic_kb.get("facts") or []:
            deduction_path.append(f"FACT {fact['predicate']}({json.dumps(fact['args'], ensure_ascii=False)})")

        if not candidates:
            return {
                "state_code": "STRUCT_UNCERTAIN",
                "confidence": 0.5,
                "interpretation": "SuperBrain: 无匹配规则。",
                "deduction_path": deduction_path,
                "logic_kb": logic_kb,
                "matched_rule": None,
                "arbiter_used": False,
                "candidate_rules": [],
            }

        if len(candidates) == 1:
            rule = candidates[0]
            deduction_path.append(f"SINGLE_MATCH rule={rule['id']} (no arbiter needed)")
            return self._pack_rule(rule, logic_kb, deduction_path, arbiter_used=False, candidates=candidates)

        top = candidates[0]
        second = candidates[1]
        if _rule_priority(top) > _rule_priority(second):
            deduction_path.append(
                f"PRIORITY resolved {len(candidates)} candidates → {top['id']} over {second['id']}"
            )
            return self._pack_rule(top, logic_kb, deduction_path, arbiter_used=False, candidates=candidates)

        # 优先级相同 → SuperBrain KB + Arbiter
        kb = pangu.KB()
        for t in _tags_to_terms(tags):
            kb.add_fact(t)
        _inject_structure_terms(kb, structure, logic_kb)
        _load_inference_rules(kb, self.rules)

        for c in candidates:
            deduction_path.append(
                f"CANDIDATE rule={c['id']} state={c['state_code']} conf={c.get('confidence')}"
            )

        cognitive = pangu.CognitiveEngine(kb)
        with tempfile.TemporaryDirectory() as tmp:
            arbiter = pangu.Arbiter(kb, memory_dir=tmp)
            goal = pangu.Term("market_state", ("_State", "_Conf"))
            binding, trace, think_log = arbiter.reason(goal, cognitive)

        deduction_path.append("ARBITER SuperBrainAgent.reason(market_state/2)")
        if think_log:
            for line in think_log.splitlines()[:8]:
                if line.strip():
                    deduction_path.append(f"ARBITER {line.strip()}")

        if not binding:
            rule = candidates[0]
            deduction_path.append("ARBITER fallback=highest_confidence_rule")
            return self._pack_rule(rule, logic_kb, deduction_path, arbiter_used=True, candidates=candidates)

        state = binding.get("_State") or binding.get("_state")
        conf_raw = binding.get("_Conf") or binding.get("_conf")
        try:
            confidence = float(conf_raw)
        except (TypeError, ValueError):
            confidence = float(candidates[0].get("confidence", 0.7))

        matched = next((c for c in candidates if c["state_code"] == state), candidates[0])
        if len(candidates) > 1:
            deduction_path.append(
                f"ARBITER resolved {len(candidates)} candidates → {matched['id']} ({state})"
            )

        out = self._pack_rule(matched, logic_kb, deduction_path, arbiter_used=True, candidates=candidates)
        out["confidence"] = round(confidence, 2)
        out["arbiter_binding"] = {k: str(v) for k, v in binding.items()}
        return out

    def _pack_rule(
        self,
        rule: dict,
        logic_kb: Dict[str, Any],
        deduction_path: List[str],
        *,
        arbiter_used: bool,
        candidates: List[dict],
    ) -> Dict[str, Any]:
        interpretation = rule.get("interpretation", "")
        div = logic_kb.get("divergence")
        sig = logic_kb.get("last_signal")
        if sig and div:
            interpretation += (
                f" 因为 bar#{sig.get('bar_index')} 出现 {sig.get('kind')}（{sig.get('reason')}），"
                f"且 bar#{div.get('bar_index')} 形成{div.get('reason')}，"
                f"符合{rule['id']}定义。"
            )
        deduction_path.append(_format_deduction(rule.get("deduction_template", ""), logic_kb))
        return {
            "state_code": rule["state_code"],
            "confidence": rule.get("confidence", 0.7),
            "interpretation": interpretation,
            "deduction_path": deduction_path,
            "logic_kb": logic_kb,
            "matched_rule": rule["id"],
            "arbiter_used": arbiter_used,
            "candidate_rules": [c["id"] for c in candidates],
        }
