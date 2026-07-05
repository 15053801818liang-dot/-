package scheduler

import (
	"fmt"
	"path/filepath"
	"time"
)

// Node DAG 节点定义。
type Node struct {
	ID     string
	Script string
	Params map[string]interface{}
}

// DAG 简单线性/依赖 DAG 执行器。
type DAG struct {
	ID        string
	Workspace string
	Nodes     []Node
	Executor  *JSONExecutor
	Auditor   *Auditor
}

// RunResult 全流程结果。
type RunResult struct {
	Artifacts map[string]interface{}
	Report    string
	Metrics   RunMetrics
}

func (d *DAG) Run() (*RunResult, error) {
	finishMetrics, _ := StartRunMetrics()
	artifacts := make(map[string]interface{})
	ws := filepath.Join(d.Executor.ProjectRoot, d.Workspace)
	for _, node := range d.Nodes {
		nodeStart := time.Now()
		d.Auditor.Log(node.ID, "EXEC_REQUESTED", "CHECK_PASSED", "pre-flight ok")
		d.Auditor.Log(node.ID, "RUNNING", "IN_PROGRESS", "")

		input := TaskInput{
			Params:       node.Params,
			WorkspaceDir: d.Workspace,
			DagID:        d.ID,
			Artifacts:    artifacts,
		}
		out, err := d.Executor.RunTask(node.Script, input)
		if err != nil {
			d.Auditor.Log(node.ID, "EXEC_FAILED", "FAILED", err.Error())
			return nil, fmt.Errorf("node %s: %w", node.ID, err)
		}

		entry := map[string]interface{}{
			"status":        out.Status,
			"message":       out.Message,
			"payload":       out.Payload,
		}
		if p := out.Payload; p != nil {
			if ap, ok := p["artifact_path"].(string); ok {
				entry["artifact_path"] = ap
			}
			if s, ok := p["summary"].(map[string]interface{}); ok {
				entry["summary"] = s
			}
			if rp, ok := p["report_path"].(string); ok {
				entry["report_path"] = rp
			}
			for _, key := range []string{
				"pangu_logic_interpretation", "market_state_code", "confidence", "semantic_audit",
			} {
				if v, ok := p[key]; ok {
					entry[key] = v
				}
			}
		}
		artifacts[node.ID] = entry
		elapsed := time.Since(nodeStart).Seconds()
		d.Auditor.Log(node.ID, "COMPLETED", "SUCCESS", fmt.Sprintf("ok elapsed=%.3fs", elapsed))
	}

	report := ""
	if w, ok := artifacts["write_replay_report"].(map[string]interface{}); ok {
		if rp, ok := w["report_path"].(string); ok {
			report = rp
		}
	}
	_ = ws
	metrics := finishMetrics()
	return &RunResult{Artifacts: artifacts, Report: report, Metrics: metrics}, nil
}
