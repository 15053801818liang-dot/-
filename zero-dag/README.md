# ZERO-DAG — 神话项目2 盘古调度引擎

Go DAG 调度器 + 缠论引擎 + 盘古符号推理 + 记忆层七刀封口

## 架构

```
cmd/go-scheduler         ← 调度器入口
pkg/scheduler/           ← Go 核心 (8状态矩阵 · Kahn拓扑 · 并发执行 · 持久化)
tasks/                   ← Python 任务节点
internal/chanlun/        ← 缠论引擎
pangu/                   ← 盘古推理 (Reasoner + Arbiter)
memory/                  ← 记忆层 V0 (七刀封口: inbox/recall/review/event/core_recall/integrity/trace)
tests/                   ← 45 个测试
```

## 运行

```bash
# 调度器 dry-run
WORKSPACE_DIR=workspace go run ./cmd/go-scheduler/ --mode=dry-run

# 完整测试
pytest tests/ -v
```

## 封口状态

- MEMORY_INBOX_V0_FIRST_WRITE_SEALED
- MEMORY_RECALL_V0_SEALED
- MEMORY_REVIEW_GATE_V0_SEALED
- MEMORY_EVENT_LOG_V0_SEALED
- MEMORY_CORE_RECALL_V0_SEALED
- MEMORY_INTEGRITY_V0_SEALED
- MEMORY_TRACE_V0_SEALED
