# pangu/arbiter.py
"""市场状态裁决器 (Market-State Arbiter)。

将 chanlun 产出的“规则候选列表”从“简单取第一个”升级为
**权重裁决 + 冲突防御协议**：

    无候选                         → NONE
    有候选                         → 按 state_code 权重排序
    第一名明显领先                 → 返回 winner
    第一名与第二名差距 <= 阈值     → 防御协议 OSC_NEUTRAL

设计约束：
    - 纯标准库，零外部依赖（与盘古 pure-stdlib 风格一致）。
    - ``reason()`` 始终返回**统一结构**，避免下游字段漂移：
        {
            "interpretation": str,
            "state_code": str,
            "confidence": float,   # 0.0 - 1.0
            "selected_rule": Optional[str],
            "conflict_sources": List[str],
            "unknown_rules": List[str],
        }
    - 未知 state_code 不静默吞掉：保留在 ``unknown_rules`` 中暴露上游污染。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# 缺省权重：数字越大优先级越高。
DEFAULT_WEIGHTS: Dict[str, int] = {
    "HIGH_RISK_EXIT": 100,
    "TREND_BULL_LEAVE_PIVOT": 80,
    "BUY_DIVERGENCE_CONFIRM": 60,
    "OSC_NEUTRAL": 10,
}


class Arbiter:
    """市场状态裁决器。"""

    def __init__(
        self,
        weights: Optional[Dict[str, int]] = None,
        defense_threshold: int = 10,
    ) -> None:
        # 复制一份，避免外部字典被就地修改导致的隐蔽耦合。
        self.weights: Dict[str, int] = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        self.defense_threshold = defense_threshold

    # ---- 内部工具 -------------------------------------------------

    def _weight(self, rule: Dict[str, Any]) -> int:
        return self.weights.get(rule.get("state_code"), 0)

    @staticmethod
    def _harden(activated_rules: Any) -> List[Dict[str, Any]]:
        """输入 schema 加固。

        - None / 非序列        → 空列表
        - 非 dict 候选项       → 丢弃（不让脏输入炸掉裁决层）
        """
        if not activated_rules:
            return []
        if isinstance(activated_rules, dict):
            # 单个 dict 视为单候选，宽容处理。
            return [activated_rules]
        try:
            iterator = list(activated_rules)
        except TypeError:
            return []
        return [r for r in iterator if isinstance(r, dict)]

    # ---- 主裁决入口 -----------------------------------------------

    def reason(self, activated_rules: Any) -> Dict[str, Any]:
        rules = self._harden(activated_rules)

        if not rules:
            return {
                "interpretation": "无明确信号",
                "state_code": "NONE",
                "confidence": 0.0,
                "selected_rule": None,
                "conflict_sources": [],
                "unknown_rules": [],
            }

        # 未知规则：暴露上游拼写/污染，绝不静默降权吞掉。
        unknown_rules = [
            r.get("state_code")
            for r in rules
            if r.get("state_code") not in self.weights
        ]

        sorted_rules = sorted(rules, key=self._weight, reverse=True)
        winner = sorted_rules[0]

        if len(sorted_rules) > 1:
            first = self._weight(sorted_rules[0])
            second = self._weight(sorted_rules[1])
            # 语义：差距“在阈值以内（含阈值）”即视为接近 → 触发防御。
            if first - second <= self.defense_threshold:
                result = self._trigger_defense_protocol(sorted_rules)
                result["unknown_rules"] = unknown_rules
                return result

        return {
            "interpretation": winner.get("interpretation", "规则裁决完成"),
            "state_code": winner.get("state_code"),
            "confidence": winner.get("confidence", 1.0),
            "selected_rule": winner.get("state_code"),
            "conflict_sources": [],
            "unknown_rules": unknown_rules,
        }

    def _trigger_defense_protocol(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "interpretation": "多重信号冲突，触发防御协议—观望",
            "state_code": "OSC_NEUTRAL",
            "confidence": 0.5,
            "selected_rule": None,
            "conflict_sources": [r.get("state_code") for r in rules[:3]],
        }

    # ---- Fact 注入桥 (→ KB / SuperBrainAgent) ----------------------

    @staticmethod
    def to_market_fact(decision: Dict[str, Any]) -> Tuple[str, Tuple[Any, ...]]:
        """把裁决结果转成 ``(predicate, args)`` 形式的事实描述。

        产出 ``market_state(state_code, confidence)``，供上层用任意
        Term 工厂构造后注入 KB。此处保持零依赖，不 import 盘古主模块。
        """
        return (
            "market_state",
            (decision.get("state_code"), decision.get("confidence")),
        )

    def inject(
        self,
        decision: Dict[str, Any],
        kb: Any,
        term_factory: Callable[[str, Tuple[Any, ...]], Any],
    ) -> Any:
        """将裁决结果注入 KB（鸭子类型: ``kb.add_fact`` + ``term_factory``）。

        与盘古 ``KB.add_fact(Term(name, args))`` 接口对齐，但不硬依赖它——
        调用方传入 ``term_factory=Term`` 即可对接 SuperBrainAgent。
        """
        name, args = self.to_market_fact(decision)
        fact = term_factory(name, tuple(args))
        kb.add_fact(fact)
        return fact

    def arbitrate_and_inject(
        self,
        activated_rules: Any,
        kb: Any,
        term_factory: Callable[[str, Tuple[Any, ...]], Any],
    ) -> Tuple[Dict[str, Any], Any]:
        """一步到位：裁决 + 注入。返回 (decision, injected_fact)。"""
        decision = self.reason(activated_rules)
        fact = self.inject(decision, kb, term_factory)
        return decision, fact
