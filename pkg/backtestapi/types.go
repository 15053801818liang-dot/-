package backtestapi

import "time"

// SubmitRequest POST /api/backtest body.
type SubmitRequest struct {
	Symbol    string `json:"symbol"`
	Interval  string `json:"interval"`
	StartDate string `json:"start_date"`
	EndDate   string `json:"end_date"`
}

// SubmitResponse POST /api/backtest response.
type SubmitResponse struct {
	TaskID string `json:"task_id"`
	Status string `json:"status"`
}

// TaskStatus GET /api/backtest/{id} response.
type TaskStatus struct {
	ID        string `json:"id"`
	Status    string `json:"status"`
	Progress  int    `json:"progress"`
	CreatedAt string `json:"created_at"`
	UpdatedAt string `json:"updated_at"`
	Error     string `json:"error,omitempty"`
}

// ReportResponse GET /api/report/{id} response.
type ReportResponse struct {
	BiCount       int    `json:"bi_count"`
	DuanCount     int    `json:"duan_count"`
	SignalCount   int    `json:"signal_count"`
	DivergenceCnt int    `json:"divergence_count"`
	RawReport     string `json:"raw_report"`
}

// Task persisted backtest job.
type Task struct {
	ID        string         `json:"id"`
	Request   SubmitRequest  `json:"request"`
	Status    string         `json:"status"`
	Progress  int            `json:"progress"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
	Error     string         `json:"error,omitempty"`
	Report    *ReportResponse `json:"report,omitempty"`
	Workspace string         `json:"workspace"`
}

const (
	StatusSubmitted = "submitted"
	StatusRunning   = "running"
	StatusCompleted = "completed"
	StatusFailed    = "failed"
)
