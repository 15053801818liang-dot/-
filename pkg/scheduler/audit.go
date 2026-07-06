package scheduler

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"time"

	"gopkg.in/natefinch/lumberjack.v2"
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

// Auditor 输出御史台审计日志（stderr + 轮转文件）。
type Auditor struct {
	User   string
	writer io.Writer
}

func NewAuditor(user, logPath string) *Auditor {
	if user == "" {
		user = "总司令"
	}
	var w io.Writer = os.Stderr
	if logPath != "" {
		lj := &lumberjack.Logger{
			Filename:   logPath,
			MaxSize:    10,
			MaxBackups: 5,
			MaxAge:     30,
			Compress:   true,
		}
		w = io.MultiWriter(os.Stderr, lj)
	}
	return &Auditor{User: user, writer: w}
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
	fmt.Fprintf(a.writer, "[御史台审计] %s\n", string(b))
	log.Printf("[调度器] %s action=%s status=%s %s", nodeID, action, status, message)
}
