package scheduler

import (
	"context"
	"fmt"
	"sync"
	"time"

	"golang.org/x/sync/semaphore"
)

type DAGSchedulerV0 struct {
	mu             sync.RWMutex
	instances      map[string]*DAGInstance
	executor       Executor
	maxConcurrency int64
	sem            *semaphore.Weighted
	eventBus       *EventBus
	nodeEvents     *NodeEventSource
	dagEvents      *DAGEventSource
	store          *Store
}

func NewDAGSchedulerV0(executor Executor, maxConcurrency int64, storePath string) *DAGSchedulerV0 {
	bus := NewEventBus()
	return &DAGSchedulerV0{
		instances:      make(map[string]*DAGInstance),
		executor:       executor,
		maxConcurrency: maxConcurrency,
		sem:            semaphore.NewWeighted(maxConcurrency),
		eventBus:       bus,
		nodeEvents:     NewNodeEventSource(bus),
		dagEvents:      NewDAGEventSource(bus),
		store:          NewStore(storePath),
	}
}

func (s *DAGSchedulerV0) SubmitDAG(ctx context.Context, spec *DAGSpec) (*DAGInstance, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	order, err := TopologicalSort(spec)
	if err != nil {
		return nil, fmt.Errorf("topological sort failed: %w", err)
	}

	inst := &DAGInstance{
		ID:             fmt.Sprintf("dag_%d", time.Now().UnixNano()),
		Spec:           spec,
		NodeStates:     make(map[string]*NodeState),
		ExecutionOrder: order,
		Env:            make(map[string]interface{}),
		Status:         InstanceRunning,
		CreatedAt:      time.Now(),
		UpdatedAt:      time.Now(),
	}
	inst.cond = sync.NewCond(&inst.mu)

	for id := range spec.Nodes {
		inst.NodeStates[id] = &NodeState{Status: StatusPending}
	}

	// Mark root nodes ready (no dependencies)
	for id, ns := range spec.Nodes {
		if len(ns.Dependencies) == 0 {
			inst.NodeStates[id].Status = StatusReady
		} else {
			inst.NodeStates[id].Status = StatusBlocked
		}
	}

	s.instances[inst.ID] = inst
	s.store.Save(inst)
	s.dagEvents.Emit(inst.ID, "", InstanceRunning)

	return inst, nil
}

func (s *DAGSchedulerV0) GetDAG(dagID string) (*DAGInstance, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	inst, ok := s.instances[dagID]
	return inst, ok
}

func (s *DAGSchedulerV0) GetReadyNodes(inst *DAGInstance) []string {
	var ready []string
	for id, state := range inst.NodeStates {
		if state.Status == StatusReady {
			ready = append(ready, id)
		}
	}
	return ready
}

func (s *DAGSchedulerV0) IsDAGComplete(inst *DAGInstance) bool {
	for _, state := range inst.NodeStates {
		switch state.Status {
		case StatusCompleted, StatusSkipped, StatusCancelled:
			continue
		default:
			return false
		}
	}
	return true
}

func (s *DAGSchedulerV0) IsDAGFailed(inst *DAGInstance) bool {
	for _, state := range inst.NodeStates {
		if state.Status == StatusFailed {
			return true
		}
	}
	return false
}
