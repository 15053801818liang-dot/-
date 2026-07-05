package scheduler

import "time"

// NodeStatus 节点生命周期状态。
type NodeStatus string

const (
	StatusPending   NodeStatus = "pending"
	StatusBlocked   NodeStatus = "blocked"
	StatusReady     NodeStatus = "ready"
	StatusRunning   NodeStatus = "running"
	StatusFailed    NodeStatus = "failed"
	StatusCompleted NodeStatus = "completed"
	StatusSkipped   NodeStatus = "skipped"
	StatusCancelled NodeStatus = "cancelled"
)

// IsTerminal 返回是否为终态（completed / skipped / cancelled）。
func (s NodeStatus) IsTerminal() bool {
	return s == StatusCompleted || s == StatusSkipped || s == StatusCancelled
}

// NodeState 节点运行时状态。
type NodeState struct {
	Status NodeStatus
	Error  string
	Output string
}

// Edge DAG 依赖边。
type Edge struct {
	From string `json:"from"`
	To   string `json:"to"`
}

// DAGSpec DAG 静态定义（拓扑 + 任务配置）。
type DAGSpec struct {
	ID    string
	Nodes map[string]*Node
	Edges []*Edge
}

// DAGInstance DAG 运行时实例。
type DAGInstance struct {
	Spec       *DAGSpec
	NodeStates map[string]*NodeState
	CreatedAt  time.Time
	UpdatedAt  time.Time
}

// NewDAGInstance 从 spec 创建实例，所有节点初始为 pending。
func NewDAGInstance(spec *DAGSpec, now time.Time) *DAGInstance {
	states := make(map[string]*NodeState, len(spec.Nodes))
	for id := range spec.Nodes {
		states[id] = &NodeState{Status: StatusPending}
	}
	return &DAGInstance{
		Spec:       spec,
		NodeStates: states,
		CreatedAt:  now,
		UpdatedAt:  now,
	}
}
