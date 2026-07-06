package backtestapi

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"myth002/pkg/scheduler"
)

// Runner executes the chanlun DAG pipeline for a task.
type Runner struct {
	ProjectRoot string
}

func (r *Runner) Run(task *Task) (*ReportResponse, error) {
	marketPath, err := ResolveMarketPath(r.ProjectRoot, task.Request)
	if err != nil {
		return nil, err
	}
	configPath := ResolveStrategyConfig(r.ProjectRoot, task.Request)
	workspace := task.Workspace
	if workspace == "" {
		workspace = filepath.Join("workspace", "api", task.ID)
	}
	task.Workspace = workspace

	executor := scheduler.NewJSONExecutor(r.ProjectRoot)
	auditPath := filepath.Join(r.ProjectRoot, workspace, "logs", "yushitai_audit.jsonl")
	_ = os.MkdirAll(filepath.Dir(auditPath), 0o755)
	auditor := scheduler.NewAuditor("api", auditPath)

	dag := &scheduler.DAG{
		ID:        task.ID,
		Workspace: workspace,
		Executor:  executor,
		Auditor:   auditor,
		Nodes: []scheduler.Node{
			{
				ID:     "load_market_data",
				Script: "tasks/load_market_data.py",
				Params: map[string]interface{}{
					"source_path":    marketPath,
					"prefer_parquet": true,
				},
			},
			{
				ID:     "chanlun_backtest",
				Script: "tasks/chanlun_backtest.py",
				Params: map[string]interface{}{
					"strategy_config_path": configPath,
				},
			},
			{
				ID:     "join_union_report",
				Script: "tasks/join_union_report.py",
				Params: map[string]interface{}{},
			},
			{
				ID:     "pangu_inference",
				Script: "tasks/pangu_inference.py",
				Params: map[string]interface{}{},
			},
			{
				ID:     "write_replay_report",
				Script: "tasks/write_replay_report.py",
				Params: map[string]interface{}{},
			},
		},
	}

	result, err := dag.Run()
	if err != nil {
		return nil, err
	}
	return buildReport(r.ProjectRoot, workspace, task.ID, result)
}

func buildReport(projectRoot, workspace, taskID string, result *scheduler.RunResult) (*ReportResponse, error) {
	reportPath := filepath.Join(projectRoot, workspace, "reports", taskID+".md")
	raw, err := os.ReadFile(reportPath)
	if err != nil {
		if rp := result.Report; rp != "" {
			raw, err = os.ReadFile(rp)
		}
		if err != nil {
			return nil, fmt.Errorf("read report: %w", err)
		}
	}

	resp := &ReportResponse{RawReport: string(raw)}

	replayPath := filepath.Join(projectRoot, workspace, "artifacts", taskID, "chanlun_replay.json")
	b, err := os.ReadFile(replayPath)
	if err != nil {
		return resp, nil
	}
	var doc struct {
		Metrics map[string]interface{} `json:"metrics"`
	}
	if err := json.Unmarshal(b, &doc); err != nil {
		return resp, nil
	}
	if m := doc.Metrics; m != nil {
		resp.BiCount = intFrom(m, "strokes_count")
		resp.DuanCount = intFrom(m, "duan_count")
		resp.SignalCount = intFrom(m, "signals_count")
		resp.DivergenceCnt = intFrom(m, "divergence_count")
	}

	unionPath := filepath.Join(projectRoot, workspace, "artifacts", taskID, "union_report.json")
	if ub, err := os.ReadFile(unionPath); err == nil {
		var union struct {
			CrossDomain struct {
				AlignmentScore float64 `json:"alignment_score"`
				Status         string  `json:"status"`
				RiskIndicator  float64 `json:"risk_indicator"`
			} `json:"cross_domain"`
		}
		if err := json.Unmarshal(ub, &union); err == nil {
			resp.AlignmentScore = union.CrossDomain.AlignmentScore
			resp.CrossDomainStat = union.CrossDomain.Status
			resp.RiskIndicator = union.CrossDomain.RiskIndicator
		}
	}
	return resp, nil
}

func intFrom(m map[string]interface{}, key string) int {
	v, ok := m[key]
	if !ok {
		return 0
	}
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	default:
		return 0
	}
}

// Queue manages async backtest execution.
type Queue struct {
	store  *Store
	runner *Runner
	sem    chan struct{}
}

func NewQueue(store *Store, runner *Runner, maxConcurrent int) *Queue {
	if maxConcurrent <= 0 {
		maxConcurrent = 2
	}
	return &Queue{
		store:  store,
		runner: runner,
		sem:    make(chan struct{}, maxConcurrent),
	}
}

func (q *Queue) Submit(task *Task) error {
	task.Status = StatusSubmitted
	task.Progress = 0
	now := time.Now().UTC()
	task.CreatedAt = now
	task.UpdatedAt = now
	if err := q.store.Save(task); err != nil {
		return err
	}
	go q.runAsync(task.ID)
	return nil
}

func (q *Queue) runAsync(taskID string) {
	q.sem <- struct{}{}
	defer func() { <-q.sem }()

	task, ok := q.store.Get(taskID)
	if !ok {
		return
	}
	task.Status = StatusRunning
	task.Progress = 5
	task.UpdatedAt = time.Now().UTC()
	_ = q.store.Save(task)

	report, err := q.runner.Run(task)
	if err != nil {
		task.Status = StatusFailed
		task.Error = err.Error()
		task.Progress = 100
		task.UpdatedAt = time.Now().UTC()
		_ = q.store.Save(task)
		return
	}

	task.Report = report
	task.Status = StatusCompleted
	task.Progress = 100
	task.UpdatedAt = time.Now().UTC()
	_ = q.store.Save(task)
}

func (q *Queue) StatusView(task *Task) TaskStatus {
	return TaskStatus{
		ID:        task.ID,
		Status:    task.Status,
		Progress:  task.Progress,
		CreatedAt: task.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt: task.UpdatedAt.UTC().Format(time.RFC3339),
		Error:     task.Error,
	}
}
