package scheduler

import (
	"context"
	"fmt"
	"log"
	"sync"
)

// DAGSchedulerV0 v0.1 调度器核心 — 状态机 + 状态转换 + 事件预留。
type DAGSchedulerV0 struct {
	mu         sync.Mutex
	clock      Clock
	nodeEvents NodeEventEmitter
	logger     *log.Logger
}

// DAGSchedulerOption 可选配置。
type DAGSchedulerOption func(*DAGSchedulerV0)

// WithClock 注入时钟（测试用）。
func WithClock(c Clock) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.clock = c }
}

// WithNodeEvents 注入事件发射器。
func WithNodeEvents(e NodeEventEmitter) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.nodeEvents = e }
}

// WithLogger 注入日志器。
func WithLogger(l *log.Logger) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.logger = l }
}

// NewDAGSchedulerV0 创建调度器。
func NewDAGSchedulerV0(opts ...DAGSchedulerOption) *DAGSchedulerV0 {
	s := &DAGSchedulerV0{
		clock:      RealClock{},
		nodeEvents: NoopNodeEventEmitter{},
		logger:     log.Default(),
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

func (s *DAGSchedulerV0) transitionNodeStatus(
	ctx context.Context,
	instance *DAGInstance,
	nodeID string,
	target NodeStatus,
	reason string,
	output string,
) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	state, ok := instance.NodeStates[nodeID]
	if !ok {
		return fmt.Errorf("scheduler: node %s not found", nodeID)
	}
	if err := validateTransition(state.Status, target); err != nil {
		return err
	}

	prev := state.Status
	state.Status = target
	if reason != "" {
		state.Error = reason
	}
	if output != "" {
		state.Output = output
	} else if target == StatusCompleted || target == StatusSkipped || target == StatusCancelled {
		// 非 completed 终态清空 output；completed 保留传入值
		if target != StatusCompleted {
			state.Output = ""
		}
	}
	instance.UpdatedAt = s.clock.Now()

	dagID := instance.Spec.ID
	s.emitEvent(dagID, nodeID, prev, target, reason, output)
	s.logger.Printf("node -> %s dag=%s node=%s reason=%s", target, dagID, nodeID, reason)
	return nil
}

func (s *DAGSchedulerV0) emitEvent(dagID, nodeID string, _, target NodeStatus, reason, output string) {
	switch target {
	case StatusReady:
		s.nodeEvents.EmitReady(dagID, nodeID)
	case StatusRunning:
		s.nodeEvents.EmitRunning(dagID, nodeID)
	case StatusCompleted:
		s.nodeEvents.EmitCompleted(dagID, nodeID, output)
	case StatusFailed:
		s.nodeEvents.EmitFailed(dagID, nodeID, reason)
	case StatusBlocked:
		s.nodeEvents.EmitBlocked(dagID, nodeID, reason)
	case StatusSkipped:
		s.nodeEvents.EmitSkipped(dagID, nodeID, reason)
	case StatusCancelled:
		s.nodeEvents.EmitCancelled(dagID, nodeID, reason)
	}
}

// SetNodeReady 将节点变更为 ready（来源: pending, failed, blocked）。
func (s *DAGSchedulerV0) SetNodeReady(ctx context.Context, instance *DAGInstance, nodeID string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusReady, "", "")
}

// SetNodeRunning 将节点变更为 running（来源: ready）。
func (s *DAGSchedulerV0) SetNodeRunning(ctx context.Context, instance *DAGInstance, nodeID string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusRunning, "", "")
}

// SetNodeCompleted 将节点变更为 completed（来源: running）。
func (s *DAGSchedulerV0) SetNodeCompleted(ctx context.Context, instance *DAGInstance, nodeID, output string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusCompleted, "", output)
}

// SetNodeFailed 将节点变更为 failed（来源: running）。
func (s *DAGSchedulerV0) SetNodeFailed(ctx context.Context, instance *DAGInstance, nodeID, errMsg string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusFailed, errMsg, "")
}

// SetNodeBlocked 将节点变更为 blocked（来源: pending, ready, failed）。
func (s *DAGSchedulerV0) SetNodeBlocked(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusBlocked, reason, "")
}

// SetNodeSkipped 将节点变更为 skipped（来源: pending, ready, failed, blocked）。
func (s *DAGSchedulerV0) SetNodeSkipped(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusSkipped, reason, "")
}

// SetNodeCancelled 将节点变更为 cancelled（来源: 任意非终态）。
func (s *DAGSchedulerV0) SetNodeCancelled(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusCancelled, reason, "")
}

// topoSort 对 DAG 进行拓扑排序（Kahn 算法 + 判环）。
func (s *DAGSchedulerV0) topoSort(spec *DAGSpec) ([]string, error) {
	nodeCount := len(spec.Nodes)
	inDegree := make(map[string]int, nodeCount)
	children := make(map[string][]string, nodeCount)

	for id := range spec.Nodes {
		inDegree[id] = 0
	}
	for _, edge := range spec.Edges {
		from, to := edge.From, edge.To
		if _, ok := spec.Nodes[from]; !ok {
			return nil, fmt.Errorf("scheduler: edge references unknown node %s", from)
		}
		if _, ok := spec.Nodes[to]; !ok {
			return nil, fmt.Errorf("scheduler: edge references unknown node %s", to)
		}
		children[from] = append(children[from], to)
		inDegree[to]++
	}

	queue := make([]string, 0)
	for id, degree := range inDegree {
		if degree == 0 {
			queue = append(queue, id)
		}
	}

	order := make([]string, 0, nodeCount)
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		order = append(order, current)
		for _, child := range children[current] {
			inDegree[child]--
			if inDegree[child] == 0 {
				queue = append(queue, child)
			}
		}
	}

	if len(order) != nodeCount {
		return nil, fmt.Errorf("scheduler: dag contains cycle: sorted %d/%d nodes", len(order), nodeCount)
	}
	return order, nil
}
