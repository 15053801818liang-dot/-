# 燧人 Suiren — 状态

## 决策落盘

```text
SUIREN_REBUILD_DECISION_V0
CRAWLER: REMOVE_FROM_CORE
SEARCH/FETCH: TOOL_LAYER_ONLY
CORE: 对话路由 + 输出裁剪 + 任务状态机 + 证据门
REBUILD_DIRECTION: 从“抓网页系统”改成“可控输入智能体”
```

## 当前版本

```text
SUIREN_REBUILD_V0.1
SCOPE: 输入标准化 + 意图路由 + 输出裁剪
STATUS: CODE_PRESENT
TEST_EVIDENCE: run suire/run_tests.py
```

## 目录

```text
suire/
├── core/          # 第一层核心（无爬虫）
├── tools/         # 受控工具层（搜索 API / 文件 / LLM / 记忆）
├── memory/        # JSON 占位，无数据库
├── tests/
└── run_tests.py
```

## V0.1 意图覆盖

| 输入 | 意图 | 输出策略 |
|------|------|----------|
| `？` | follow_up | 短答，不补搜，不长篇 |
| `继续` | continue | 有上下文继续；无则追问 |
| `搜索: xxx` | search_intent | 走 tools/search_api，核心不爬虫 |
| `看内容` | content_display | 展示已有内容 |
| `帮我改代码` | code_task | 任务型输出 |
| `审一下` | audit_task | 任务型输出 |
| `记住/忘掉` | memory_task | 短确认 |
| 普通句 | chat | 短问短答 |

## 封口标准（V0.1）

```text
✗ 爬虫
✗ 数据库
✗ 多 Agent
✗ 复杂记忆
✗ 自动执行
✓ 听懂话、分对路、少废话
```

## 已知裂缝（后续）

```text
1. search_api / llm_client 仅占位，未接真实 API
2. memory 仅 JSON 文件读写框架
3. 输出裁剪为规则型，未接 LLM 生成链
```

## 测试

```bash
cd suire && python3 run_tests.py
```

期望：

```text
Result: 24/24 tests passed
```
