package scheduler

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"
)

// AuditEntry 御史台结构化审计记录。
type AuditEntry struct {
	Timestamp string `json:"timestamp"`
	NodeID    string `json:"node_id"`
	Action    string `json:"action"`
	User      string `json:"user"`
	Status    string `json:"status"`
	Message   string `json:"message,omitempty"`
}

// Auditor 输出御史台审计日志。
type Auditor struct {
	User string
}

func NewAuditor(user string) *Auditor {
	if user == "" {
		user = "总司令"
	}
	return &Auditor{User: user}
}

func (a *Auditor) Log(nodeID, action, status, message string) {
	entry := AuditEntry{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		NodeID:    nodeID,
		Action:    action,
		User:      a.User,
		Status:    status,
		Message:   message,
	}
	b, _ := json.Marshal(entry)
	fmt.Fprintf(os.Stderr, "[御史台审计] %s\n", string(b))
	log.Printf("[调度器] %s action=%s status=%s %s", nodeID, action, status, message)
}
