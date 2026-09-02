# Claude API 最小示例

一个能直接跑的 Claude API 起步工程：单轮问答、流式输出、多轮对话。

## 1. 拿 API Key

1. 打开 https://console.anthropic.com → **API Keys** → **Create Key**。
2. 复制 `sk-ant-...`。
3. 新账号通常有一笔小额试用额度（金额以控制台 **Billing** 页为准，Anthropic 无永久免费套餐）。

> ⚠️ 只认官方域名 `anthropic.com` / `claude.com`。别在山寨"免费 Claude API"站点输 key 或付款。

## 2. 安装 & 配置

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # Windows: set ANTHROPIC_API_KEY=sk-ant-...
```

## 3. 运行

```bash
# 单轮问答
python chat.py "用一句话解释分布式调度器"

# 流式输出（边生成边打印，适合长回答）
python chat.py --stream "写一个 Python 快排"

# 换最便宜的模型练手（$1/$5 每百万 token）
python chat.py --model claude-haiku-4-5 "你好"

# 多轮对话（输入 exit 退出）
python chat.py --chat
```

## 进阶示例

```bash
# 结构化输出：抽取成校验过的 JSON 对象（Pydantic + output_format）
python structured_output.py

# 工具调用 / function calling：手写 agentic 循环，含天气 + 安全计算器
python tools.py "北京天气怎么样，顺便算一下 (23+19)/2"

# Prompt caching 省钱：同一大段上下文，第 2 次请求命中缓存按 ~0.1x 计价
python caching.py

# Batch API：批量任务打 5 折，提交->轮询->按 custom_id 取乱序结果
python batch.py
```

进阶示例需要较新 SDK——先 `pip install -U anthropic`（结构化输出/工具需要）。
`tools.py` 的计算器用 AST 求值而非 `eval`，注入表达式会被安全拒绝。

## 模型 ID

用**精确字符串**，不要加日期后缀：

| 模型 | ID | 价格（输入/输出，每百万 token） | 适合 |
|---|---|---|---|
| Opus 4.8 | `claude-opus-4-8` | $5 / $25 | 最强，复杂推理/agent |
| Sonnet 5 | `claude-sonnet-5` | $3 / $15 | 均衡，生产高并发 |
| Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 最便宜，练习/分类 |

## 省钱提示

- 练习用 **Haiku 4.5**。
- 非实时批量任务用 **Batch API** 打 5 折。
- 重复的长上下文用 **Prompt Caching** 最多省 ~90%。

## 要点

- **API 无状态**：多轮对话每次要把完整 `messages` 历史传回去（`chat.py --chat` 已处理）。
- **key 放环境变量**，别硬编码进代码或提交到 git。
- `content` 是内容块列表，按 `block.type == "text"` 取文本。

## 官方材料

- 文档：https://docs.claude.com
- 示例集：github.com/anthropics/anthropic-cookbook
- 控制台：https://console.anthropic.com
