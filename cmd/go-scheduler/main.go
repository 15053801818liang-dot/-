package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	"myth002/pkg/scheduler"
)

func main() {
	root, err := os.Getwd()
	if err != nil {
		log.Fatal(err)
	}
	if v := os.Getenv("PROJECT_ROOT"); v != "" {
		root = v
	}
	workspace := os.Getenv("WORKSPACE_DIR")
	if workspace == "" {
		workspace = "workspace"
	}
	dagID := os.Getenv("DAG_ID")
	if dagID == "" {
		dagID = "matrix-replay-001"
	}
	sourcePath := os.Getenv("SOURCE_PATH")
	if sourcePath == "" {
		sourcePath = "data/BTCUSDT_5m.csv"
	}
	configPath := os.Getenv("STRATEGY_CONFIG")
	if configPath == "" {
		configPath = "configs/chanlun_btc.json"
	}

	logDir := filepath.Join(workspace, "logs")
	_ = os.MkdirAll(logDir, 0o755)
	auditPath := filepath.Join(logDir, "yushitai_audit.jsonl")

	auditor := scheduler.NewAuditor("总司令", auditPath)
	executor := scheduler.NewJSONExecutor(root)

	dag := &scheduler.DAG{
		ID:        dagID,
		Workspace: workspace,
		Executor:  executor,
		Auditor:   auditor,
		Nodes: []scheduler.Node{
			{
				ID:     "load_market_data",
				Script: "tasks/load_market_data.py",
				Params: map[string]interface{}{
					"source_path":    sourcePath,
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

	fmt.Println("=== 神话项目2 · Go 调度器 · 跨域联合回测闭环 ===")
	fmt.Println("任务链: load_market_data → chanlun_backtest → join_union_report → pangu_inference → write_replay_report")
	result, err := dag.Run()
	if err != nil {
		log.Fatalf("调度失败: %v", err)
	}

	report := result.Report
	if report == "" {
		report = filepath.Join(workspace, "reports", dagID+".md")
	}
	unionReport := filepath.Join(workspace, "artifacts", dagID, "union_report.json")
	fmt.Printf("✅ 调度闭环完成，回测报告: %s\n", report)
	fmt.Printf("📊 联合报告: %s\n", unionReport)
	fmt.Printf("⏱  总耗时: %.2fs | Go RSS: %.1f MB | 审计日志: %s\n",
		result.Metrics.ElapsedSec, result.Metrics.RSSMB, auditPath)
}
