package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"zero-dag/pkg/scheduler"
)

func main() {
	mode := flag.String("mode", "full-chain", "execution mode: full-chain | dry-run")
	flag.Parse()

	workspace := os.Getenv("WORKSPACE_DIR")
	if workspace == "" {
		workspace = "workspace"
	}

	executor := scheduler.NewPythonExecutor("python", "tasks")
	s := scheduler.NewDAGSchedulerV0(executor, 10, "workspace/state")

	// Build 5-node DAG
	spec := &scheduler.DAGSpec{
		Nodes: map[string]*scheduler.NodeSpec{
			"load_market_data":   {ID: "load_market_data", ExecutorType: "python"},
			"chanlun_backtest":   {ID: "chanlun_backtest", Dependencies: []string{"load_market_data"}, ExecutorType: "python"},
			"join_union_report":  {ID: "join_union_report", Dependencies: []string{"chanlun_backtest"}, ExecutorType: "python"},
			"pangu_inference":    {ID: "pangu_inference", Dependencies: []string{"join_union_report"}, ExecutorType: "python"},
			"write_replay_report": {ID: "write_replay_report", Dependencies: []string{"pangu_inference"}, ExecutorType: "python"},
		},
		Edges: map[string][]string{
			"load_market_data":   {"chanlun_backtest"},
			"chanlun_backtest":   {"join_union_report"},
			"join_union_report":  {"pangu_inference"},
			"pangu_inference":    {"write_replay_report"},
		},
	}

	fmt.Printf("[SCHEDULER] Mode: %s, Workspace: %s\n", *mode, workspace)
	if *mode == "dry-run" {
		order, err := scheduler.TopologicalSort(spec)
		if err != nil {
			log.Fatalf("Topo sort failed: %v", err)
		}
		fmt.Printf("[SCHEDULER] Node order: %v\n", order)
		return
	}

	inst, err := s.SubmitDAG(nil, spec)
	if err != nil {
		log.Fatalf("SubmitDAG failed: %v", err)
	}
	fmt.Printf("[SCHEDULER] DAG submitted: %s, nodes: %v\n", inst.ID, inst.ExecutionOrder)
}
