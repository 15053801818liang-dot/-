package scheduler

import "fmt"

// GetDAG 按 ID 获取已注册的 DAG 实例。
func (s *DAGSchedulerV0) GetDAG(dagID string) (*DAGInstance, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[dagID]
	return inst, ok
}

// ListDAGs 返回所有已注册实例 ID。
func (s *DAGSchedulerV0) ListDAGs() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.instances))
	for id := range s.instances {
		ids = append(ids, id)
	}
	return ids
}

// GetReadyNodes 返回 ready 状态节点 ID 列表。
func (s *DAGSchedulerV0) GetReadyNodes(dagID string) []string {
	return s.filterNodesByStatus(dagID, StatusReady)
}

// GetBlockedNodes 返回 blocked 状态节点 ID 列表。
func (s *DAGSchedulerV0) GetBlockedNodes(dagID string) []string {
	return s.filterNodesByStatus(dagID, StatusBlocked)
}

func (s *DAGSchedulerV0) filterNodesByStatus(dagID string, status NodeStatus) []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[dagID]
	if !ok {
		return nil
	}
	var out []string
	for id, st := range inst.NodeStates {
		if st.Status == status {
			out = append(out, id)
		}
	}
	return out
}

// IsDAGComplete 所有节点均处于终态。
func (s *DAGSchedulerV0) IsDAGComplete(dagID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[dagID]
	if !ok {
		return false
	}
	for _, st := range inst.NodeStates {
		if !st.Status.IsTerminal() {
			return false
		}
	}
	return true
}

// IsDAGStuck 无 ready/running 且未完成。
func (s *DAGSchedulerV0) IsDAGStuck(dagID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[dagID]
	if !ok {
		return false
	}
	allTerminal := true
	for _, st := range inst.NodeStates {
		if !st.Status.IsTerminal() {
			allTerminal = false
		}
		if st.Status == StatusReady || st.Status == StatusRunning {
			return false
		}
	}
	if allTerminal {
		return false
	}
	return true
}

// RemoveDAG 移除实例。
func (s *DAGSchedulerV0) RemoveDAG(dagID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.instances[dagID]; !ok {
		return fmt.Errorf("scheduler: dag %s not found", dagID)
	}
	delete(s.instances, dagID)
	return nil
}

// topoSort 保留方法别名，供测试使用。
func (s *DAGSchedulerV0) topoSort(spec *DAGSpec) ([]string, error) {
	return TopoSort(spec)
}
