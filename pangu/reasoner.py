"""盘古符号推理引擎 — Reasoner"""
import json
import os
from pathlib import Path


class PanguReasoner:
    """Symbolic KB reasoning engine. Loads rules from configs/pangu_symbolic_kb.json."""

    def __init__(self, kb_path: str = None):
        if kb_path is None:
            kb_path = Path(__file__).parent.parent / "configs" / "pangu_symbolic_kb.json"
        self.kb = self._load_kb(kb_path)

    def _load_kb(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "BUY": {"threshold": 0.7, "patterns": ["divergence_confirm", "trend_reversal"]},
                "SELL": {"threshold": 0.7, "patterns": ["overbought", "bearish_divergence"]},
            }

    def infer(self, alignment_score: float, biome_features: dict = None) -> dict:
        """Run symbolic inference against KB rules."""
        signals = []
        for direction, rules in self.kb.items():
            if alignment_score >= rules["threshold"]:
                matched = [p for p in rules["patterns"] if self._match_pattern(p, biome_features)]
                if matched:
                    signals.append({
                        "direction": direction,
                        "strength": round(alignment_score, 2),
                        "matched_patterns": matched,
                    })

        if signals:
            best = max(signals, key=lambda s: s["strength"])
            return {
                "state_code": f"OSC_{best['direction']}_DIVERGENCE",
                "confidence": round(0.8 + best["strength"] * 0.15, 2),
                "explanation": f"{best['direction']} divergence confirmed: {', '.join(best['matched_patterns'])}",
                "signals": signals,
            }
        return {
            "state_code": "OSC_NEUTRAL",
            "confidence": 0.5,
            "explanation": "No strong symbolic pattern matched.",
            "signals": [],
        }

    @staticmethod
    def _match_pattern(pattern: str, features: dict) -> bool:
        if features is None:
            return True
        if pattern == "divergence_confirm":
            return features.get("cd8_mem_ratio", 0) > 0.3
        if pattern == "trend_reversal":
            return features.get("auc_delta", 0) > 0.05
        if pattern == "overbought":
            return features.get("rscore", 0) < -5
        if pattern == "bearish_divergence":
            return features.get("nr_score", 0) < -5
        return False
