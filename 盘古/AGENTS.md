# AGENTS — 模块配置 (Module Configuration)

盘古启用的功能模块。将值改为 `false` 可禁用对应模块。
`reasoning_methods` 控制仲裁器候选方法列表（逗号分隔）。

---

## Modules

- dream_engine: true
- knowledge_graph: true
- reality_supervisor: true
- mcp_bridge: true
- auto_skill_learner: true
- arbiter: true

## ReasoningMethods

- enabled: cot, tot, react, mcts, socratic, decomp, refine, recursive, analogy, abductive, inductive, dialectic, counter, stepback, contradict, ensemble
