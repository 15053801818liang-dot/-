# 燧人 Suiren — 状态

## 决策落盘

```text
SUIREN_REBUILD_DECISION_V0
CRAWLER: REMOVE_FROM_CORE
SEARCH/FETCH: TOOL_LAYER_ONLY
CORE: 对话路由 + 输出裁剪 + 任务状态机 + 证据门
REBUILD_DIRECTION: 从“抓网页系统”改成“可控输入智能体”
```

## 版本门禁

### V0.1 — CORE_SEALED ✅

```text
SUIREN_REBUILD_V0.1
SCOPE: 输入标准化 + 意图路由 + 输出裁剪
SEAL_SCOPE: suire/core only
TEST_EVIDENCE: 24/24 PASSED (V0.1 baseline, retained)
```

V0.1 只证明：输入标准化、意图分类、输出约束、爬虫不进 core、自动执行不放行。  
V0.1 不证明：搜索 API 可用、LLM 接通、记忆读写、多轮稳定、工具链可靠、证据可审计。

### V0.2 — TOOL_CALL_CONTRACT ✅

```text
SUIREN_REBUILD_V0.2
NAME: TOOL_CALL_CONTRACT_V0
SCOPE: core → tools 调用契约 + 证据门（工具可假，契约必须真）
TEST_EVIDENCE: 37/37 PASSED
```

新增：

```text
suire/core/tool_contract.py   # ToolRequest / ToolResult / process_contract_turn
suire/core/evidence_gate.py   # EvidenceFrame / filter_evidence_items
suire/tools/mock_backends.py  # 假 search 后端（测试专用，不接外网）
```

## 目录

```text
suire/
├── core/
│   ├── input_packet.py
│   ├── intent_router.py
│   ├── task_state.py
│   ├── output_policy.py
│   ├── safety_gate.py
│   ├── tool_contract.py      # V0.2
│   └── evidence_gate.py      # V0.2
├── tools/
├── memory/
├── tests/
└── run_tests.py
```

## V0.2 契约产物

```text
ToolRequest
  tool_name / query / reason / allow_network / max_results / source_policy
ToolResult
  status / items / error / citations / raw_allowed=False
EvidenceFrame
  needs_evidence / evidence_required_for_answer / confidence_ceiling / answer_allowed
```

## V0.2 必测场景（已覆盖）

| # | 场景 | 期望 |
|---|------|------|
| 1 | `搜索: GPT 最新价格` | ToolRequest(search_api), allow_network=True |
| 2 | `爬一下这个网站` | safety_gate → crawler_not_in_core |
| 3 | `你知道今天新闻吗` | needs_evidence=True, answer_allowed=False |
| 4 | `看内容` | 无 ToolRequest |
| 5 | `继续` | 有上下文不搜；无上下文 clarify |
| 6 | search 空结果 | insufficient_evidence |
| 7 | 广告源 | evidence_gate 拒绝 |
| 8 | 工具报错 | tool_failed，不崩不幻觉 |

## 禁止范围（V0.2 仍未引入）

```text
✗ 真实爬虫
✗ 真实外网 search API
✗ 真实 LLM
✗ 真实记忆读写
✗ 自动执行
✗ 多 Agent
✗ 数据库
```

## 测试

```bash
cd suire && python3 run_tests.py
```

期望：

```text
Result: 37/37 tests passed
```

## 下一门禁（未开）

```text
SUIREN_REBUILD_V0.3  # 待定：单工具真实接入（search 或 llm 二选一，不同时做）
```
