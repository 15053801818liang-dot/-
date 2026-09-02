package scheduler

import (
	"context"
)

// Executor 节点执行器接口。
type Executor interface {
	Execute(ctx context.Context, inst *DAGInstance, nodeID string) (output string, err error)
}

// NoopExecutor 空实现，用于测试。
type NoopExecutor struct{}

func (NoopExecutor) Execute(_ context.Context, _ *DAGInstance, nodeID string) (string, error) {
	return "ok:" + nodeID, nil
}

// FuncExecutor 函数式执行器。
type FuncExecutor func(ctx context.Context, inst *DAGInstance, nodeID string) (string, error)

func (f FuncExecutor) Execute(ctx context.Context, inst *DAGInstance, nodeID string) (string, error) {
	return f(ctx, inst, nodeID)
}
