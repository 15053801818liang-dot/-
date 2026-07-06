package scheduler

import "time"

// NewDAGInstance 从 spec 创建实例，所有节点初始为 pending。
func NewDAGInstance(spec *DAGSpec, now time.Time) *DAGInstance {
	states := make(map[string]*NodeState, len(spec.Nodes))
	for id := range spec.Nodes {
		states[id] = &NodeState{Status: StatusPending}
	}
	inst := &DAGInstance{
		ID:         spec.ID,
		Spec:       spec,
		NodeStates: states,
		CreatedAt:  now,
		UpdatedAt:  now,
	}
	inst.Status = inst.ComputeStatus()
	return inst
}

// ComputeStatus 根据节点状态计算实例级状态。
func (inst *DAGInstance) ComputeStatus() InstanceStatus {
	if len(inst.NodeStates) == 0 {
		return InstancePending
	}
	allTerminal := true
	anyFailed := false
	anyRunningOrReady := false
	for _, st := range inst.NodeStates {
		if !st.Status.IsTerminal() {
			allTerminal = false
		}
		if st.Status == StatusFailed {
			anyFailed = true
		}
		if st.Status == StatusRunning || st.Status == StatusReady {
			anyRunningOrReady = true
		}
	}
	if allTerminal {
		if anyFailed {
			return InstanceFailed
		}
		return InstanceCompleted
	}
	if anyRunningOrReady {
		return InstanceRunning
	}
	hasBlockedOnly := true
	for _, st := range inst.NodeStates {
		if st.Status != StatusBlocked && !st.Status.IsTerminal() {
			hasBlockedOnly = false
			break
		}
	}
	if hasBlockedOnly && !anyRunningOrReady {
		return InstanceStuck
	}
	return InstancePending
}

// NodeStatusList 返回所有节点状态列表（API 用）。
func (inst *DAGInstance) NodeStatusList() []NodeStatusView {
	out := make([]NodeStatusView, 0, len(inst.NodeStates))
	for id, st := range inst.NodeStates {
		out = append(out, NodeStatusView{ID: id, Status: st.Status, Error: st.Error})
	}
	return out
}

// refreshStatus 更新实例级状态与时间戳。
func (inst *DAGInstance) refreshStatus(now time.Time) {
	inst.Status = inst.ComputeStatus()
	inst.UpdatedAt = now
}
