# DAG Scheduler v0 — 交付摘要

## 核心能力

- DAG 定义与校验（无环、无自环、边引用完整）
- 拓扑排序（Kahn 算法，`topo.go`）
- 状态机驱动（8 种节点状态，转换矩阵见 `transitions.go`）
- 并发执行（所有 Ready 节点并行，`step.go` 信号量限流）
- 超时控制（每个节点独立超时，默认 30s）
- 自动下游推进（Completed → 检查依赖 → Blocked → Ready）
- 持久化（JSON 文件存储，`store.go`，启动自动恢复）
- 事件驱动（`NodeEventEmitter` 接口）
- 完整单元测试 + 集成测试

## 文件结构

| 文件 | 职责 |
|------|------|
| `types_v0.go` | 核心类型定义 |
| `instance.go` | `NewDAGInstance`、实例状态计算 |
| `transitions.go` | 状态转换矩阵 |
| `graph.go` | 邻接表 + 入度表 |
| `topo.go` | 拓扑排序 + 环检测 |
| `submit.go` | `SubmitDAG` + `validateDAGSpec` |
| `scheduler_v0.go` | `DAGSchedulerV0` + 7 个 `SetNode*` + `RunAll` |
| `step.go` | `Step`（并发执行 + 超时 + 限流） |
| `api.go` | `GetDAG` / `ListDAGs` / 查询方法 |
| `executor.go` | `Executor` 接口 |
| `json_executor.go` | Python JSON 执行器（兼容 demo） |
| `store.go` | JSON 持久化 |
| `clock.go` | `Clock` / `RealClock` / `MockClock` |
| `event.go` | 事件类型定义 |
| `events_v0.go` | `NodeEventEmitter` + Noop |

## 使用示例

```go
s := scheduler.NewDAGSchedulerV0(
    scheduler.WithExecutor(myExec),
    scheduler.WithMaxConcurrency(5),
    scheduler.WithDataDir("./data"),
)
inst, err := s.SubmitDAG(ctx, spec)
err = s.RunAll(ctx, inst.ID)
```

## HTTP API

```bash
go run ./cmd/scheduler-api/
# POST /submit  {"dag": {...}}
# GET  /status?id=<dag_id>
# GET  /health
```

## 测试

```bash
go test ./pkg/scheduler/...
go build ./cmd/go-scheduler/...
go build ./cmd/scheduler-api/
```

## 初始化规则

- 入度 0：`pending → ready`
- 入度 > 0：`pending → blocked`（reason: `waiting for dependencies`）

## 性能说明

- 单节点执行：取决于 `Executor` 实现（HTTP 占位约 50ms）
- 并发吞吐：受 `WithMaxConcurrency` 限制
- 持久化：每次状态变更自动写入 JSON
