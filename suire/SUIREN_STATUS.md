# 燧人 Suiren — 状态

## 决策落盘

```text
SUIREN_REBUILD_DECISION_V0
CRAWLER: REMOVE_FROM_CORE
SEARCH/FETCH: TOOL_LAYER_ONLY
CORE: 对话路由 + 输出裁剪 + 任务状态机 + 证据门
REBUILD_DIRECTION: 可控输入智能体
```

## 当前总状态

```text
SUIREN_REBUILD_V0.1_CORE_SEALED ✅
SUIREN_REBUILD_V0.2_TOOL_CALL_CONTRACT_SEALED ✅
SUIREN_REBUILD_V0.3_SEARCH_ADAPTER_CODE_SEALED ✅
SUIREN_REBUILD_V0.3.1_LIVE_SEARCH_SMOKE_HARNESS_SEALED ✅
LIVE_SEARCH_REGRESSION: WAITING
```

## 版本门禁

### V0.1 — CORE_SEALED ✅

输入标准化 + 意图路由 + 输出裁剪

### V0.2 — TOOL_CALL_CONTRACT_SEALED ✅

`ToolRequest` / `ToolResult` / `EvidenceFrame` + mock 契约测试

### V0.3 — SEARCH_ADAPTER_CODE_SEALED ✅

真实 search adapter 代码（`tools/search_api.py`，stdlib urllib）

```text
SEAL_SCOPE: suire/tools/search_api.py + contract integration tests
CI: 52/52（后并入 57/57 总集）
LIVE_API_EVIDENCE: NOT_PROVIDED（CI 用 FakeFetcher）
```

### V0.3.1 — LIVE_SEARCH_SMOKE_HARNESS_SEALED ✅

```text
SCRIPT: suire/tools/live_search_smoke.py
CI_TEST_EVIDENCE: 57/57 PASSED（格式/验收逻辑，Mock only）
LIVE_SEARCH_REGRESSION: WAITING
FINAL: smoke 脚手架已封，live 搜索能力未证
```

**V0.3.1 证明**：脚本存在、报告格式可验证、无 key 安全跳过、`smoke_pass` 判定存在、CI 不依赖外网、不输出完整 API key。

**V0.3.1 不证明**：Brave key 可用、live 返回结构稳定、网络/限频处理充分、搜索质量足够、live adapter 已通过真实回归。

## LIVE_SEARCH_REGRESSION 解锁条件

只认本地真实日志：

```bash
export SUIREN_SEARCH_API_KEY=your_brave_key
cd suire
python3 tools/live_search_smoke.py --query "GPT price"
cat reports/live_search_smoke_report.txt
```

**PASS 报告必须含**：

```text
provider=brave
api_key_present=True
status=ok
citations_count>=1
missing_url_count=0
smoke_pass=True
```

**若 `api_key_present=True` 但 `status=tool_failed`**：

```text
LIVE_SEARCH_FAILED_WITH_ERROR
WAITING_ADAPTER_OR_PROVIDER_PATCH
```

（不是代码封口失败，是 adapter/provider 层待修。）

## 禁止范围（仍未引入）

```text
✗ 爬虫  ✗ LLM  ✗ memory_store  ✗ 数据库  ✗ 多 Agent  ✗ 自动执行
```

## CI 测试

```bash
cd suire && python3 run_tests.py
```

```text
Result: 57/57 tests passed
```

## 下一门禁（未开）

```text
LIVE_SEARCH_REGRESSION 解锁后，才议 V0.4（LLM adapter，与 search 不同时做）
```
