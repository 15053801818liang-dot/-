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

// InstanceStatus DAG 实例级状态。
type InstanceStatus string

const (
	InstancePending   InstanceStatus = "pending"
	InstanceRunning   InstanceStatus = "running"
	InstanceCompleted InstanceStatus = "completed"
	InstanceFailed    InstanceStatus = "failed"
	InstanceStuck     InstanceStatus = "stuck"
)

// NodeState 节点运行时状态。
type NodeState struct {
	Status     NodeStatus `json:"status"`
	Error      string     `json:"error,omitempty"`
	Output     string     `json:"output,omitempty"`
	DurationMS int64      `json:"duration_ms,omitempty"`
}

// NodeStatusView API 用节点状态视图。
type NodeStatusView struct {
	ID     string     `json:"id"`
	Status NodeStatus `json:"status"`
	Error  string     `json:"error,omitempty"`
}

// Edge DAG 依赖边。
type Edge struct {
	From string `json:"from"`
	To   string `json:"to"`
}

// DAGSpec DAG 静态定义（拓扑 + 任务配置）。
type DAGSpec struct {
	ID    string             `json:"id"`
	Nodes map[string]*Node   `json:"nodes"`
	Edges []*Edge            `json:"edges"`
}

// DAGInstance DAG 运行时实例。
type DAGInstance struct {
	ID         string                 `json:"id"`
	Spec       *DAGSpec               `json:"spec"`
	NodeStates map[string]*NodeState  `json:"node_states"`
	Status     InstanceStatus         `json:"status"`
	CreatedAt  time.Time              `json:"created_at"`
	UpdatedAt  time.Time              `json:"updated_at"`
}
