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
LIVE_SEARCH_REGRESSION: FAILED_WITH_ERROR
ERROR: HTTP_422
SUIREN_REBUILD_V0.3.2_BRAVE_ADAPTER_DIAGNOSTIC_PATCH ✅
NEXT: WAITING_VALID_BRAVE_TOKEN + LIVE_SEARCH_PASSED report
```

## V0.3.2 — BRAVE_ADAPTER_DIAGNOSTIC_PATCH

```text
SCOPE: tools/search_diagnostic.py + search_api.py HTTP body capture
CORE: UNCHANGED
CI: mock tests only
```

诊断字段（live smoke 报告追加）：

```text
diag_provider=brave
diag_endpoint=https://api.search.brave.com/res/v1/web/search
diag_method=GET
diag_header_token_present=True
diag_header_token_prefix_redacted=sk-7...
diag_query_present=True
diag_count=N
diag_http_status=422
diag_adapter_error_kind=auth_invalid | provider_422 | ...
diag_error_body_redacted=<first_500_chars_no_key>
```

422 优先排查：

```text
1. Header: X-Subscription-Token: <Brave subscription token>
2. Endpoint: https://api.search.brave.com/res/v1/web/search
3. Params: q=...&count=3
4. sk-... 形态 key → PROVIDER_TOKEN_MISMATCH（非 Brave Search token）
```

## LIVE_SEARCH 门禁（不变）

**PASSED** 只认：

```text
api_key_present=True
status=ok
citations_count>=1
missing_url_count=0
smoke_pass=True
```

**FAILED_WITH_ERROR**：

```text
api_key_present=True
status=tool_failed
error=<含 http_status + adapter_error_kind + body 摘要>
```

**WAITING**：

```text
api_key_present=False → not_configured
```

## 禁止范围

```text
✗ 爬虫  ✗ LLM  ✗ memory  ✗ 数据库  ✗ 多 Agent  ✗ 自动执行
```

## CI 测试

```bash
cd suire && python3 run_tests.py
```

```text
Result: 63/63 tests passed
```

## 本地 live smoke

```bash
export SUIREN_SEARCH_API_KEY=<Brave_Search_subscription_token>
cd suire && python3 tools/live_search_smoke.py --query "GPT price"
cat reports/live_search_smoke_report.txt
```

**只贴报告，不贴 key。**
