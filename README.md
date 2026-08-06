# Monorepo 总览

> 本仓库包含 **6 个独立项目**，涵盖符号推理、技术分析、分布式调度、LLM 集成等方向。

---

## 仓库架构（目录 → 项目映射）

```
.
├── 盘古/                      ─ ❶ Pangu 符号推理智能体 (Python, 零依赖)
├── chanlun/                   ─ ❷ 缠论技术分析内核 (Python, 零依赖)
├── scheduler/                 ─ ❸ 分布式调度器 (Python, etcd + shared-memory)
├── cmd/go-scheduler/          ─ ❹ Go DAG 调度器 (Go, 驱动 Python 任务)
│   pkg/scheduler/                 调度器核心库
│   tasks/                         Python 任务脚本
│   configs/                       DAG 配置 JSON
│   scripts/                       数据生成 & 导入脚本
│   data/                          市场数据 CSV
│   internal/                      Go 内部包
├── distributed-scheduler/     ─ ❺ C++ 分布式调度 Hub (ZMQ + WAL)
├── claude-api-example/        ─ ❻ Claude API 示例集 (Python)
├── llm-scheduler-integration/ ─   LLM × C++ 调度器集成桥 (Python + ZMQ)
├── YBLLMStreamSystem/         ─   iOS LLM 流式骨架 (Swift/ObjC)
├── docs/                      ─   OpenAPI 等文档
└── README.md                  ─   本文件
```

---

## ❶ 盘古 Pangu — 符号推理智能体

| 项 | 说明 |
|---|---|
| **路径** | `盘古/` |
| **语言** | Python 3.8+（纯标准库，零外部依赖） |
| **版本** | v0.11.0 |
| **核心能力** | 合一回溯推理 · 16 种认知引擎（CoT/ToT/MCTS/ReAct/苏格拉底…） · 4D 持久记忆 · 梦境引擎 · 知识图谱 · 骨骼守护 · MCP 协议桥接 · 显式/隐式/反例规则学习 · 一致性证明 |

**架构**：`SuperBrainAgent` → `BoneGuard`（安全）+ `NLMatcher`（NLP 解析）+ `SessionMemory` + `SelfReflect` → `KB`（Facts/Rules/ConsistencyChecker）→ `LearningSubsystem`（Explicit/Implicit/Negative）

```bash
# 运行 REPL
cd 盘古 && python3 pangu_v0.11.0.py

# MCP 模式（JSON stdin/stdout）
python3 pangu_v0.11.0.py --mcp

# 测试
python3 test_pangu_v0.10.0.py && python3 test_comprehensive.py && python3 test_pangu_v011.py
```

**文档**：[README](盘古/README.md) · [ARCHITECTURE](盘古/ARCHITECTURE.md) · [MCP API](盘古/MCP_API.md) · [CHANGELOG](盘古/CHANGELOG.md)

---

## ❷ 缠论 chanlun — 技术分析内核

| 项 | 说明 |
|---|---|
| **路径** | `chanlun/` |
| **语言** | Python（纯标准库，零外部依赖） |
| **核心流程** | `K线 → 包含处理 → 分型 → 笔 → 中枢 → MACD背驰 → 一/二/三类买卖点` |

**模块**：

| 文件 | 职责 |
|---|---|
| `models.py` | 数据结构（Bar/MergedBar/Fractal/Stroke/Pivot/TradePoint） |
| `kline.py` | K 线包含处理 |
| `fractal.py` | 顶/底分型识别 |
| `stroke.py` + `stroke_rules.py` | 笔构建（新笔/老笔） |
| `pivot.py` | 中枢识别 |
| `macd.py` | EMA/MACD/柱面积 |
| `signals.py` | 背驰判定 + 买卖点 |
| `analyzer.py` | 门面：串起整条流水线 |
| `backtest.py` | 回测引擎 |

```bash
python3 -m chanlun.demo              # 演示
python3 chanlun/test_chanlun.py      # 测试
```

**文档**：[README](chanlun/README.md)

---

## ❸ 分布式调度器 (Python)

| 项 | 说明 |
|---|---|
| **路径** | `scheduler/` |
| **语言** | Python |
| **依赖** | `etcd3`, `prometheus-client`, `psutil`（见 `requirements.txt`） |
| **核心能力** | lock-free shared-memory MPMC 任务队列 · etcd leader election · Prometheus 监控 |

**模块**：`core.py`（调度核心）· `atomic.py`（原子操作）· `storage.py`（共享内存）· `lease.py`（etcd 租约）· `monitor.py`（监控）· `client.py`（客户端）· `cli.py`（CLI）

```bash
pip install --break-system-packages -r requirements.txt
python3 -m pytest tests/test_distributed_scheduler.py    # 测试（无需 etcd）
```

---

## ❹ Go DAG 调度器

| 项 | 说明 |
|---|---|
| **路径** | `cmd/go-scheduler/` + `pkg/scheduler/` |
| **语言** | Go 1.22+ |
| **核心能力** | DAG 任务编排 · 驱动 Python 任务 · JSON stdin/stdout 协议 · 缠论回测 pipeline |

```bash
python3 scripts/generate_btc_csv.py                     # 生成数据
WORKSPACE_DIR=workspace go run ./cmd/go-scheduler/       # 运行
# 报告 → workspace/reports/chanlun_btc_demo.md
```

**相关路径**：`tasks/`（Python 任务）· `configs/`（DAG JSON）· `scripts/`（数据工具）· `data/`（CSV 数据）

---

## ❺ C++ 分布式调度 Hub (NeuralHub)

| 项 | 说明 |
|---|---|
| **路径** | `distributed-scheduler/` |
| **语言** | C++ |
| **依赖** | libzmq · cppzmq · nlohmann-json · cmake |
| **核心能力** | ZMQ ROUTER/DEALER 多线程调度 · WAL 崩溃恢复 · O(1) 空闲索引 · ~48k tasks/s 吞吐 |

```bash
cd distributed-scheduler
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
./build/test_wal_replay            # WAL 单测
./bench.sh 200 20000               # 压测
```

**文档**：[README](distributed-scheduler/README.md)

---

## ❻ Claude API 示例集

| 项 | 说明 |
|---|---|
| **路径** | `claude-api-example/` |
| **语言** | Python |
| **内容** | 单轮问答 · 流式输出 · 多轮对话 · 结构化输出 · 工具调用 · Prompt Caching · Batch API |

```bash
pip install -r claude-api-example/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python claude-api-example/chat.py "你好"
```

**文档**：[README](claude-api-example/README.md)

---

## 附属项目

| 路径 | 说明 |
|---|---|
| `llm-scheduler-integration/` | Python LLM worker 对接 C++ Hub，Claude API 做推理 ([README](llm-scheduler-integration/README.md)) |
| `YBLLMStreamSystem/` | iOS LLM 流式骨架，Swift/ObjC，UIKit ([README](YBLLMStreamSystem/README.md)) |

---

## 许可证

MIT License
