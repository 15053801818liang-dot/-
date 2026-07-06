// cmd/scheduler-api/main.go — Backtest HTTP API + legacy DAG scheduler endpoints
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"myth002/pkg/backtestapi"
	"myth002/pkg/scheduler"
)

var sched *scheduler.DAGSchedulerV0

func main() {
	root, _ := os.Getwd()
	if v := os.Getenv("PROJECT_ROOT"); v != "" {
		root = v
	}
	dataDir := os.Getenv("SCHEDULER_DATA_DIR")
	if dataDir == "" {
		dataDir = filepath.Join(root, "data", "scheduler")
	}
	taskDir := os.Getenv("BACKTEST_TASK_DIR")
	if taskDir == "" {
		taskDir = filepath.Join(root, "data", "backtest_tasks")
	}
	maxConc := 2
	if v := os.Getenv("BACKTEST_MAX_CONCURRENT"); v != "" {
		fmt.Sscanf(v, "%d", &maxConc)
	}

	sched = scheduler.NewDAGSchedulerV0(
		scheduler.WithExecutor(&HTTPExecutor{}),
		scheduler.WithMaxConcurrency(5),
		scheduler.WithDataDir(dataDir),
	)

	taskStore, err := backtestapi.NewStore(taskDir)
	if err != nil {
		fmt.Printf("task store init failed: %v\n", err)
		os.Exit(1)
	}
	queue := backtestapi.NewQueue(taskStore, &backtestapi.Runner{ProjectRoot: root}, maxConc)
	api := backtestapi.NewServer(queue)

	mux := http.NewServeMux()
	api.Register(mux)
	mux.HandleFunc("POST /submit", submitHandler)
	mux.HandleFunc("GET /status", statusHandler)

	addr := ":8080"
	if v := os.Getenv("SCHEDULER_ADDR"); v != "" {
		addr = v
	}
	server := &http.Server{Addr: addr, Handler: mux}
	go func() {
		fmt.Printf("Scheduler API listening on %s\n", addr)
		fmt.Println("  POST /api/backtest  — submit chanlun backtest")
		fmt.Println("  GET  /api/backtest/{id} — task status")
		fmt.Println("  GET  /api/report/{id}   — backtest report")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			fmt.Printf("Server error: %v\n", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	fmt.Println("Shutting down server...")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = server.Shutdown(ctx)
	fmt.Println("Server stopped")
}

type submitRequest struct {
	DAG scheduler.DAGSpec `json:"dag"`
}

type submitResponse struct {
	InstanceID string                   `json:"instance_id"`
	Status     scheduler.InstanceStatus `json:"status"`
}

type statusResponse struct {
	InstanceID string                     `json:"instance_id"`
	Status     scheduler.InstanceStatus   `json:"status"`
	Nodes      []scheduler.NodeStatusView `json:"nodes"`
}

func submitHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req submitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if len(req.DAG.Nodes) == 0 {
		http.Error(w, "DAG must have at least one node", http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	inst, err := sched.SubmitDAG(ctx, req.DAG)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	go func(id string) {
		_ = sched.RunAll(context.Background(), id)
	}(inst.ID)
	resp := submitResponse{InstanceID: inst.ID, Status: inst.Status}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

func statusHandler(w http.ResponseWriter, r *http.Request) {
	dagID := r.URL.Query().Get("id")
	if dagID == "" {
		http.Error(w, "missing id parameter", http.StatusBadRequest)
		return
	}
	inst, ok := sched.GetDAG(dagID)
	if !ok {
		http.Error(w, "instance not found", http.StatusNotFound)
		return
	}
	resp := statusResponse{
		InstanceID: inst.ID,
		Status:     inst.Status,
		Nodes:      inst.NodeStatusList(),
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

// HTTPExecutor placeholder for legacy /submit DAG v0 path.
type HTTPExecutor struct{}

func (e *HTTPExecutor) Execute(ctx context.Context, _ *scheduler.DAGInstance, nodeID string) (string, error) {
	select {
	case <-ctx.Done():
		return "", ctx.Err()
	case <-time.After(50 * time.Millisecond):
		return "ok:" + nodeID, nil
	}
}
