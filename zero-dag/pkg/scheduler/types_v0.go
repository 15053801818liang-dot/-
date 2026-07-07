package scheduler

import (
	"sync"
	"time"
)

type NodeStatus string

const (
	StatusPending   NodeStatus = "pending"
	StatusReady     NodeStatus = "ready"
	StatusRunning   NodeStatus = "running"
	StatusCompleted NodeStatus = "completed"
	StatusFailed    NodeStatus = "failed"
	StatusBlocked   NodeStatus = "blocked"
	StatusSkipped   NodeStatus = "skipped"
	StatusCancelled NodeStatus = "cancelled"
)

type InstanceStatus string

const (
	InstanceRunning   InstanceStatus = "running"
	InstanceCompleted InstanceStatus = "completed"
	InstanceFailed    InstanceStatus = "failed"
)

type DAGInstance struct {
	ID             string
	Spec           *DAGSpec
	NodeStates     map[string]*NodeState
	ExecutionOrder []string
	Env            map[string]interface{}
	Status         InstanceStatus
	CreatedAt      time.Time
	UpdatedAt      time.Time
	mu             sync.RWMutex
	executingCount int32
	cond           *sync.Cond
}

type NodeState struct {
	Status  NodeStatus
	Output  string
	Error   string
	Attempt int
}

type DAGSpec struct {
	Nodes map[string]*NodeSpec
	Edges map[string][]string
}

type NodeSpec struct {
	ID           string
	Dependencies []string
	Timeout      time.Duration
	RetryCount   int
	ExecutorType string
	Params       map[string]interface{}
}

type NodeEvent struct {
	NodeID    string
	From      NodeStatus
	To        NodeStatus
	Timestamp time.Time
	DAGID     string
}

type DAGEvent struct {
	DAGID     string
	From      InstanceStatus
	To        InstanceStatus
	Timestamp time.Time
}
