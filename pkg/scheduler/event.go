package scheduler

// EventType 节点事件类型。
type EventType string

const (
	EventReady     EventType = "ready"
	EventRunning   EventType = "running"
	EventCompleted EventType = "completed"
	EventFailed    EventType = "failed"
	EventBlocked   EventType = "blocked"
	EventSkipped   EventType = "skipped"
	EventCancelled EventType = "cancelled"
)

// NodeEvent 结构化节点事件。
type NodeEvent struct {
	Type      EventType  `json:"type"`
	DAGID     string     `json:"dag_id"`
	NodeID    string     `json:"node_id"`
	From      NodeStatus `json:"from,omitempty"`
	To        NodeStatus `json:"to,omitempty"`
	Reason    string     `json:"reason,omitempty"`
	Output    string     `json:"output,omitempty"`
	Timestamp int64      `json:"timestamp_ms,omitempty"`
}
