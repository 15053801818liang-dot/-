"""符号演绎层 — 将 chanlun 结构转为 Fact 并匹配 symbolic_kb.json 规则。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_KB_PATH = Path(__file__).resolve().parents[1] / "configs" / "pangu_symbolic_kb.json"


@dataclass
class Fact:
    """符号事实（SuperBrain 兼容轻量表示）。"""

    predicate: str
    args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"predicate": self.predicate, "args": self.args}


def load_symbolic_kb(path: Optional[Path] = None) -> dict:
    p = path or _KB_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _pivot_position(price: float, pivot: Dict[str, Any]) -> str:
    zg, zd = float(pivot["zg"]), float(pivot["zd"])
    if price > zg:
        return "above"
    if price < zd:
        return "below"
    return "inside"


def structure_to_facts(structure: Dict[str, Any]) -> tuple[List[Fact], Dict[str, Any]]:
    """chanlun structure_detail → 符号 Fact 列表 + logic_kb 上下文。"""
    strokes: List[Dict[str, Any]] = structure.get("recent_strokes") or []
    pivots: List[Dict[str, Any]] = structure.get("active_pivots") or []
    divergence = structure.get("last_divergence")
    trade_points: List[Dict[str, Any]] = structure.get("trade_points") or []
    last_stroke = structure.get("last_stroke") or (strokes[-1] if strokes else None)
    last_close = structure.get("last_close")
    last_signal = trade_points[-1] if trade_points else None
    active_pivot = pivots[-1] if pivots else None

    facts: List[Fact] = []
    tags: Set[str] = set()

    if last_stroke:
        facts.append(
            Fact(
                "stroke_at",
                {
                    "index": last_stroke.get("index"),
                    "direction": last_stroke.get("direction"),
                    "end_price": last_stroke.get("end_price"),
                    "amplitude": last_stroke.get("amplitude"),
                },
            )
        )

    if active_pivot:
        facts.append(
            Fact(
                "pivot_active",
                {
                    "zg": active_pivot.get("zg"),
                    "zd": active_pivot.get("zd"),
                    "mid": active_pivot.get("mid"),
                    "start_index": active_pivot.get("start_index"),
                    "end_index": active_pivot.get("end_index"),
                },
            )
        )

    if divergence:
        kind = divergence.get("kind")
        facts.append(Fact("divergence", divergence))
        if kind == "top":
            tags.add("divergence_top")
        elif kind == "bottom":
            tags.add("divergence_bottom")

    if last_signal:
        kind = last_signal.get("kind", "")
        facts.append(Fact("trade_signal", last_signal))
        tags.add(f"signal_{kind}")

    if active_pivot and last_close is not None:
        pos = _pivot_position(float(last_close), active_pivot)
        facts.append(Fact("price_position", {"position": pos, "last_close": last_close}))
        tags.add(f"position_{pos}")

    # 笔序列衰竭：最近 3 笔幅度递减
    stroke_exhaustion = False
    if len(strokes) >= 3:
        amps = [float(s.get("amplitude") or 0) for s in strokes[-3:]]
        if amps[0] > amps[1] > amps[2] > 0:
            stroke_exhaustion = True
            tags.add("stroke_exhaustion")
            facts.append(Fact("stroke_exhaustion", {"amplitudes": amps}))

    logic_kb = {
        "facts": [f.to_dict() for f in facts],
        "tags": sorted(tags),
        "last_stroke": last_stroke,
        "active_pivot": active_pivot,
        "divergence": divergence,
        "last_signal": last_signal,
        "stroke_exhaustion": stroke_exhaustion,
        "recent_stroke_count": len(strokes),
    }
    return facts, logic_kb


def _rule_matches(rule: dict, tags: Set[str]) -> bool:
    req_all = rule.get("requires_all") or []
    req_any = rule.get("requires_any") or []
    if req_all and not all(t in tags for t in req_all):
        return False
    if req_any and not any(t in tags for t in req_any):
        return False
    return bool(req_all or req_any)


def _format_deduction(template: str, logic_kb: Dict[str, Any]) -> str:
    div = logic_kb.get("divergence") or {}
    sig = logic_kb.get("last_signal") or {}
    pivot = logic_kb.get("active_pivot") or {}
    return template.format(
        signal_reason=sig.get("reason", "N/A"),
        signal_kind=sig.get("kind", "N/A"),
        div_bar=div.get("bar_index", "?"),
        zg=pivot.get("zg", "?"),
        zd=pivot.get("zd", "?"),
    )


class SymbolicReasoningPipeline:
    """符号演绎管道：Fact 注入 → 规则匹配 → 演绎路径。"""

    def __init__(self, kb_path: Optional[Path] = None) -> None:
        self.kb = load_symbolic_kb(kb_path)
        self.rules = self.kb.get("rules", [])

    def deduce(self, structure: Dict[str, Any]) -> Dict[str, Any]:
        facts, logic_kb = structure_to_facts(structure)
        tags = set(logic_kb.get("tags") or [])
        deduction_path: List[str] = []

        for fact in facts:
            deduction_path.append(f"FACT {fact.predicate}({json.dumps(fact.args, ensure_ascii=False)})")

        matched = None
        for rule in self.rules:
            if _rule_matches(rule, tags):
                matched = rule
                deduction_path.append(f"MATCH rule={rule['id']} tags={sorted(tags)}")
                break

        if not matched:
            return {
                "state_code": "STRUCT_UNCERTAIN",
                "confidence": 0.5,
                "interpretation": "结构事实已注入，但未匹配任何符号规则，建议人工复核。",
                "deduction_path": deduction_path,
                "logic_kb": logic_kb,
                "matched_rule": None,
            }

        div = logic_kb.get("divergence")
        sig = logic_kb.get("last_signal")
        extra: List[str] = []
        if logic_kb.get("stroke_exhaustion"):
            extra.append(
                f"最近 {logic_kb.get('recent_stroke_count', 3)} 笔中末 3 笔幅度递减，"
                f"笔序列动力衰竭。"
            )
        if sig and div:
            extra.append(
                f"因为 bar#{sig.get('bar_index')} 出现 {sig.get('kind')}（{sig.get('reason')}），"
                f"且 bar#{div.get('bar_index')} 形成{div.get('reason')}，"
                f"符合{matched['id']}定义。"
            )

        interpretation = matched.get("interpretation", "")
        if extra:
            interpretation = interpretation + " " + "".join(extra)

        deduction_path.append(_format_deduction(matched.get("deduction_template", ""), logic_kb))

        return {
            "state_code": matched["state_code"],
            "confidence": matched.get("confidence", 0.7),
            "interpretation": interpretation,
            "deduction_path": deduction_path,
            "logic_kb": logic_kb,
            "matched_rule": matched["id"],
        }
