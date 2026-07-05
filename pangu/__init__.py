"""pangu — 市场状态裁决层 (纯标准库, 零外部依赖)。

链路:
    chanlun signals
    → rule_candidates
    → Arbiter.reason()
    → market_state_code (可注入 KB / SuperBrainAgent)
"""

from .arbiter import Arbiter, DEFAULT_WEIGHTS

__all__ = ["Arbiter", "DEFAULT_WEIGHTS"]
