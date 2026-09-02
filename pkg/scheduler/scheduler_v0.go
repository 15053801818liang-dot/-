package scheduler

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"
)

// DAGSchedulerV0 v0.1 调度器核心。
type DAGSchedulerV0 struct {
	mu             sync.Mutex
	instances      map[string]*DAGInstance
	clock          Clock
	nodeEvents     NodeEventEmitter
	logger         *log.Logger
	executor       Executor
	store          Store
	maxConcurrency int
	nodeTimeout    time.Duration
}

// DAGSchedulerOption 可选配置。
type DAGSchedulerOption func(*DAGSchedulerV0)

func WithClock(c Clock) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.clock = c }
}

func WithNodeEvents(e NodeEventEmitter) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.nodeEvents = e }
}

func WithLogger(l *log.Logger) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.logger = l }
}

func WithExecutor(e Executor) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.executor = e }
}

func WithMaxConcurrency(n int) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) {
		if n > 0 {
			s.maxConcurrency = n
		}
	}
}

func WithNodeTimeout(d time.Duration) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) {
		if d > 0 {
			s.nodeTimeout = d
		}
	}
}

func WithStore(st Store) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) { s.store = st }
}

func WithDataDir(dir string) DAGSchedulerOption {
	return func(s *DAGSchedulerV0) {
		st, err := NewJSONStore(dir)
		if err != nil {
			s.logger.Printf("store init failed: %v", err)
			s.store = NoopStore{}
			return
		}
		s.store = st
	}
}

// NewDAGSchedulerV0 创建调度器。
func NewDAGSchedulerV0(opts ...DAGSchedulerOption) *DAGSchedulerV0 {
	s := &DAGSchedulerV0{
		instances:      make(map[string]*DAGInstance),
		clock:          RealClock{},
		nodeEvents:     NoopNodeEventEmitter{},
		logger:         log.Default(),
		executor:       NoopExecutor{},
		store:          NoopStore{},
		maxConcurrency: 5,
		nodeTimeout:    30 * time.Second,
	}
	for _, opt := range opts {
		opt(s)
	}
	s.restoreFromStore()
	return s
}

func (s *DAGSchedulerV0) restoreFromStore() {
	instances, err := s.store.LoadAll()
	if err != nil {
		s.logger.Printf("restore failed: %v", err)
		return
	}
	for _, inst := range instances {
		s.instances[inst.ID] = inst
	}
	if len(instances) > 0 {
		s.logger.Printf("restored %d dag instance(s)", len(instances))
	}
}

func (s *DAGSchedulerV0) persistLocked(inst *DAGInstance) {
	if err := s.store.Save(inst); err != nil {
		s.logger.Printf("persist dag %s: %v", inst.ID, err)
	}
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
		if target != StatusCompleted {
			state.Output = ""
		}
	}
	instance.refreshStatus(s.clock.Now())

	dagID := instance.ID
	s.emitEvent(dagID, nodeID, prev, target, reason, output)
	s.persistLocked(instance)
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

func (s *DAGSchedulerV0) SetNodeReady(ctx context.Context, instance *DAGInstance, nodeID string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusReady, "", "")
}

func (s *DAGSchedulerV0) SetNodeRunning(ctx context.Context, instance *DAGInstance, nodeID string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusRunning, "", "")
}

func (s *DAGSchedulerV0) SetNodeCompleted(ctx context.Context, instance *DAGInstance, nodeID, output string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusCompleted, "", output)
}

func (s *DAGSchedulerV0) SetNodeFailed(ctx context.Context, instance *DAGInstance, nodeID, errMsg string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusFailed, errMsg, "")
}

func (s *DAGSchedulerV0) SetNodeBlocked(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusBlocked, reason, "")
}

func (s *DAGSchedulerV0) SetNodeSkipped(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusSkipped, reason, "")
}

func (s *DAGSchedulerV0) SetNodeCancelled(ctx context.Context, instance *DAGInstance, nodeID, reason string) error {
	return s.transitionNodeStatus(ctx, instance, nodeID, StatusCancelled, reason, "")
}

// RunAll 循环 Step 直到 DAG 完成或卡住。
func (s *DAGSchedulerV0) RunAll(ctx context.Context, dagID string) error {
	for {
		if s.IsDAGComplete(dagID) {
			return nil
		}
		if s.IsDAGStuck(dagID) {
			return fmt.Errorf("scheduler: dag %s stuck", dagID)
		}
		snapBefore, _ := s.stateFingerprint(dagID)
		if err := s.Step(ctx, dagID); err != nil {
			return err
		}
		snapAfter, _ := s.stateFingerprint(dagID)
		if snapBefore == snapAfter && !s.IsDAGComplete(dagID) {
			return fmt.Errorf("scheduler: dag %s made no progress", dagID)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
	}
}

func (s *DAGSchedulerV0) stateFingerprint(dagID string) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[dagID]
	if !ok {
		return "", fmt.Errorf("scheduler: dag %s not found", dagID)
	}
	b, err := json.Marshal(inst.NodeStates)
	if err != nil {
		return "", err
	}
	return string(b), nil
}
