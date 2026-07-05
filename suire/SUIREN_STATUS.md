# 燧人 Suiren — 状态

## 决策落盘

```text
SUIREN_REBUILD_DECISION_V0
CRAWLER: REMOVE_FROM_CORE
SEARCH/FETCH: TOOL_LAYER_ONLY
CORE: 对话路由 + 输出裁剪 + 任务状态机 + 证据门
REBUILD_DIRECTION: 可控输入智能体
```

## 版本门禁

### V0.1 — CORE_SEALED ✅

输入标准化 + 意图路由 + 输出裁剪（24 项基线保留）

### V0.2 — TOOL_CALL_CONTRACT_SEALED ✅

`ToolRequest` / `ToolResult` / `EvidenceFrame` + mock 契约测试

### V0.3 — SEARCH_ADAPTER ✅

```text
SUIREN_REBUILD_V0.3_SEARCH_ADAPTER
SCOPE: 真实 search adapter（stdlib urllib，可注入 HTTP）
TEST_EVIDENCE: 52/52 PASSED
REAL_NETWORK: tools/search_api.py only（测试用 FakeFetcher）
REAL_LLM: NOT_INTRODUCED
REAL_MEMORY: NOT_INTRODUCED
CRAWLER_CORE_REMOVED: STILL_PASS
```

新增/修改：

```text
suire/tools/search_config.py          # SUIREN_SEARCH_API_KEY / TIMEOUT / PROVIDER
suire/tools/search_api.py             # SearchAPIAdapter.invoke(ToolRequest)
suire/tests/test_search_adapter.py
suire/tests/test_search_contract_integration.py
```

配置：

```bash
export SUIREN_SEARCH_API_KEY=your_brave_key   # 未设置 → not_configured
export SUIREN_SEARCH_PROVIDER=brave           # 默认
export SUIREN_SEARCH_TIMEOUT=10
```

## V0.3 必测门禁（已覆盖）

| # | 场景 | 结果 |
|---|------|------|
| 1 | 无 API_KEY | `tool_failed:not_configured` |
| 2 | API 超时 | `tool_failed:timeout` |
| 3 | 空结果 | `insufficient_evidence` |
| 4 | 无 url/citation | `rejected_missing_citation` |
| 5 | 广告/推广源 | evidence_gate 拒绝 |
| 6 | 官方/文档源 | `accepted_source` |
| 7 | `搜索: xxx` 端到端 | ToolRequest → ToolResult.ok + citations |
| 8 | core 不 import requests/httpx | AST 扫描 PASS |

## 封口边界

```text
V0.3 证明：
- search adapter 实现 ToolBackend 契约
- 搜不到不乱答（empty/失败/拒绝 → 不编答案）
- 搜到了过 evidence_gate（url + 来源策略）
- 外网仅在 tools/search_api.py（stdlib urllib）

V0.3 不证明：
- 生产环境 API 配额/稳定性
- LLM 接通
- memory_store 真实读写
- 多轮任务链
- 证据质量已充分
```

## 禁止范围（仍未引入）

```text
✗ 爬虫  ✗ LLM  ✗ memory_store  ✗ 数据库  ✗ 多 Agent  ✗ 自动执行
```

## 测试

```bash
cd suire && python3 run_tests.py
```

```text
Result: 52/52 tests passed
```

## 下一门禁

### V0.3.1 — LIVE_SEARCH_SMOKE（脚本已就绪，live 日志待本地）

```text
SUIREN_REBUILD_V0.3.1_LIVE_SEARCH_SMOKE
SCRIPT: suire/tools/live_search_smoke.py
CI: 仅测报告格式/验收逻辑（Mock），不含 live 结果
LIVE_SEARCH_REGRESSION: WAITING（需本地 API_KEY + 真实日志）
```

本地运行：

```bash
export SUIREN_SEARCH_API_KEY=your_brave_key
cd suire && python3 tools/live_search_smoke.py --query "GPT price"
# 报告: suire/reports/live_search_smoke_report.txt
```

最小验收字段：

```text
provider=brave
api_key_present=True
query="GPT price"
status=ok | tool_failed
item_count=N
citations_count=N
missing_url_count=0
ads_rejected_count=N
elapsed_ms=N
smoke_pass=True|False
```

```text
SUIREN_REBUILD_V0.1_CORE_SEALED ✅
SUIREN_REBUILD_V0.2_TOOL_CALL_CONTRACT_SEALED ✅
SUIREN_REBUILD_V0.3_SEARCH_ADAPTER_CODE_SEALED ✅
WAITING: LIVE_SEARCH_REGRESSION log from local environment
```

## 下一门禁（未开）

```text
SUIREN_REBUILD_V0.4  # 待定：LLM adapter（与 live search 验证完成后才议）
```
