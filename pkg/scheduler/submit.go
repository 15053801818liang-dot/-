package scheduler

import (
	"context"
	"fmt"
)

const initialBlockedReason = "waiting for dependencies"

func validateDAGSpec(spec *DAGSpec) error {
	if spec.ID == "" {
		return fmt.Errorf("scheduler: dag id is required")
	}
	if len(spec.Nodes) == 0 {
		return fmt.Errorf("scheduler: dag must have at least one node")
	}
	for id, node := range spec.Nodes {
		if id == "" {
			return fmt.Errorf("scheduler: node id is required")
		}
		if node == nil {
			return fmt.Errorf("scheduler: node %s is nil", id)
		}
	}
	return nil
}

// SubmitDAG 校验 spec、判环、初始化节点状态并注册实例。
//
// 初始化规则：入度 0 → ready；入度 > 0 → blocked。
func (s *DAGSchedulerV0) SubmitDAG(ctx context.Context, spec DAGSpec) (*DAGInstance, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	if err := validateDAGSpec(&spec); err != nil {
		return nil, err
	}
	if _, err := TopoSort(&spec); err != nil {
		return nil, err
	}
	inDegree, _, err := buildGraph(&spec)
	if err != nil {
		return nil, err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.instances[spec.ID]; exists {
		return nil, fmt.Errorf("scheduler: dag %s already exists", spec.ID)
	}

	specCopy := spec
	now := s.clock.Now()
	instance := NewDAGInstance(&specCopy, now)

	dagID := spec.ID
	for nodeID := range spec.Nodes {
		state := instance.NodeStates[nodeID]
		if inDegree[nodeID] == 0 {
			if err := validateTransition(state.Status, StatusReady); err != nil {
				return nil, err
			}
			state.Status = StatusReady
			s.emitEvent(dagID, nodeID, StatusPending, StatusReady, "", "")
		} else {
			if err := validateTransition(state.Status, StatusBlocked); err != nil {
				return nil, err
			}
			state.Status = StatusBlocked
			state.Error = initialBlockedReason
			s.emitEvent(dagID, nodeID, StatusPending, StatusBlocked, initialBlockedReason, "")
		}
	}
	instance.refreshStatus(now)
	s.instances[dagID] = instance
	s.persistLocked(instance)
	s.logger.Printf("dag submitted id=%s nodes=%d", dagID, len(spec.Nodes))
	return instance, nil
}
