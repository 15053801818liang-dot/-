# LLM × 分布式调度器 集成

把仓库两条线焊在一起：**C++ 分布式调度器**（`../distributed-scheduler`）负责
WAL 崩溃恢复、O(1) 调度、崩溃安全的任务派发；**Python LLM worker** 接到任务后
调用 **Claude API** 做真推理。调度器的 `PendingTask.code` 字段被当作 LLM prompt。

```
                  SUBMIT_TASK(prompt)          RUN_TASK(prompt)
  submit_tasks.py ──────────────▶  C++ Hub  ──────────────▶  llm_worker.py ──▶ Claude API
   (DEALER)                      (ROUTER +               (DEALER,          (haiku/opus…)
                                  WAL + O(1)              每个 worker            │
                                  调度)      ◀────────────  一个 identity)  ◀────┘
                                          TASK_DONE(result)
```

Hub 不感知"这是 LLM 任务"——它只做通用的崩溃安全派发；worker 端才把 prompt 交给 Claude。
所以调度器的所有保证（任务不丢、僵尸重派、O(1) 空闲索引）**免费**用在了 LLM 负载上。

## 快速跑（推荐先跑 mock）

```bash
pip install -r requirements.txt      # anthropic + pyzmq

# ① 协议连通性演示：不花钱、不用 key，返回假答案，验证全链路
./run_demo.sh --mock

# ② 真实推理：需要 key
export ANTHROPIC_API_KEY=sk-ant-...
./run_demo.sh
```

`run_demo.sh` 会：需要时编译 Hub → 启动 Hub → 起 2 个 worker → 提交 5 个 prompt →
打印每个 worker 的 Q/A → 收尾时打印 Hub 的 `submitted/assigned/completed` 指标。

## 手动分步跑

```bash
# 终端 1：启动调度器 Hub
../distributed-scheduler/build/hub --port 5555

# 终端 2、3：起 worker（--mock 免 key；去掉则真调 Claude）
python llm_worker.py --id w1 --mock
python llm_worker.py --id w2 --mock

# 终端 4：提交一批 prompt
python submit_tasks.py
```

## 实测（本机，mock 模式）

真实 C++ Hub + 2 个 Python worker + 5 个 prompt：

```
[w1] ▸ Q: 把这句话翻译成英文：...   [w2] ▸ Q: 用一句话解释什么是 WAL：...
METRICS: submitted=5 assigned=5 completed=5 wakes=7
```

5 个任务被 Hub 负载均衡到两个 worker、全部完成——证明 Python worker 正确说了
C++ Hub 的线协议。唯一没在沙箱里验证的是真实 Claude 调用（需要 key），那部分的
SDK 用法已在 `../claude-api-example` 里验证过。

## 线协议（与 Hub 对齐）

worker 是 ZMQ DEALER，发 `[空分隔帧, JSON]`；Hub 的 ROUTER 自动前置 identity。

| op | 方向 | 字段 |
|---|---|---|
| `WORKER_READY` | worker→hub | 注册 |
| `SUBMIT_TASK` | client→hub | `task_id`, `manifest`(system), `code`(prompt) |
| `RUN_TASK` | hub→worker | `task_id`, `manifest`, `code` |
| `TASK_DONE` | worker→hub | `task_id`, `result` |
| `TASK_FAILED` | worker→hub | `task_id`, `error`（Hub 会重新入队） |

## 生产化方向

- **结果回传**：当前 Hub 不转发结果给提交方（它是纯派发器）。要收集答案，可让 worker
  把 `result` 写入外部存储（DB/对象存储/结果队列），提交方按 `task_id` 取。
- **省钱**：worker 默认用 `claude-haiku-4-5`；批量离线任务可改走 `../claude-api-example/batch.py`
  的 Batch API 打 5 折。
- **规模**：调度器实测单进程 ~2000 worker 上限（fd 限制），LLM 场景每 worker 是一条
  慢任务，通常远用不到这个量级。
