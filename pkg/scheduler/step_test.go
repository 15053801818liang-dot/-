package scheduler

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// mockExecutor 可控的 Executor，按 nodeID 返回成功或失败。
type mockExecutor struct {
	results map[string]error
}

func (e *mockExecutor) Execute(_ context.Context, _ *DAGInstance, nodeID string) (string, error) {
	if err, ok := e.results[nodeID]; ok {
		return "", err
	}
	return "ok:" + nodeID, nil
}

func newChainSpec(id string) DAGSpec {
	return DAGSpec{
		ID: id,
		Nodes: map[string]*Node{
			"A": {ID: "A"},
			"B": {ID: "B"},
			"C": {ID: "C"},
		},
		Edges: []*Edge{
			{From: "A", To: "B"},
			{From: "B", To: "C"},
		},
	}
}

// ============================================================
// Step 闭环：A → B → C
// ============================================================

func TestStep_ChainSuccess(t *testing.T) {
	sched := NewDAGSchedulerV0(WithExecutor(&mockExecutor{results: map[string]error{}}))
	spec := newChainSpec("chain-ok")
	inst, err := sched.SubmitDAG(context.Background(), spec)
	if err != nil {
		t.Fatalf("SubmitDAG: %v", err)
	}

	if inst.NodeStates["A"].Status != StatusReady {
		t.Fatalf("A should be Ready, got %s", inst.NodeStates["A"].Status)
	}
	if inst.NodeStates["B"].Status != StatusBlocked {
		t.Fatalf("B should be Blocked, got %s", inst.NodeStates["B"].Status)
	}
	if inst.NodeStates["C"].Status != StatusBlocked {
		t.Fatalf("C should be Blocked, got %s", inst.NodeStates["C"].Status)
	}

	ctx := context.Background()
	dagID := inst.ID

	// Step 1: 执行 A
	if err := sched.Step(ctx, dagID); err != nil {
		t.Fatalf("Step 1 failed: %v", err)
	}
	if sched.IsDAGComplete(dagID) {
		t.Fatal("DAG complete too early after step 1")
	}
	if inst.NodeStates["A"].Status != StatusCompleted {
		t.Errorf("A should be Completed, got %s", inst.NodeStates["A"].Status)
	}
	if inst.NodeStates["B"].Status != StatusReady {
		t.Errorf("B should be Ready, got %s", inst.NodeStates["B"].Status)
	}
	if inst.NodeStates["C"].Status != StatusBlocked {
		t.Errorf("C should be Blocked, got %s", inst.NodeStates["C"].Status)
	}

	// Step 2: 执行 B
	if err := sched.Step(ctx, dagID); err != nil {
		t.Fatalf("Step 2 failed: %v", err)
	}
	if inst.NodeStates["B"].Status != StatusCompleted {
		t.Errorf("B should be Completed, got %s", inst.NodeStates["B"].Status)
	}
	if inst.NodeStates["C"].Status != StatusReady {
		t.Errorf("C should be Ready, got %s", inst.NodeStates["C"].Status)
	}

	// Step 3: 执行 C
	if err := sched.Step(ctx, dagID); err != nil {
		t.Fatalf("Step 3 failed: %v", err)
	}
	if inst.NodeStates["C"].Status != StatusCompleted {
		t.Errorf("C should be Completed, got %s", inst.NodeStates["C"].Status)
	}
	if !sched.IsDAGComplete(dagID) {
		t.Error("DAG should be complete")
	}
}

func TestStep_ChainFailure(t *testing.T) {
	sched := NewDAGSchedulerV0(WithExecutor(&mockExecutor{
		results: map[string]error{
			"B": errors.New("B execution failed"),
		},
	}))
	inst, err := sched.SubmitDAG(context.Background(), newChainSpec("chain-fail"))
	if err != nil {
		t.Fatalf("SubmitDAG: %v", err)
	}

	ctx := context.Background()
	dagID := inst.ID

	// Step 1: A 成功
	if err := sched.Step(ctx, dagID); err != nil {
		t.Fatalf("Step 1 failed: %v", err)
	}
	if inst.NodeStates["B"].Status != StatusReady {
		t.Fatalf("B should be Ready, got %s", inst.NodeStates["B"].Status)
	}

	// Step 2: B 失败
	if err := sched.Step(ctx, dagID); err != nil {
		t.Fatalf("Step 2 failed: %v", err)
	}
	if inst.NodeStates["B"].Status != StatusFailed {
		t.Errorf("B should be Failed, got %s", inst.NodeStates["B"].Status)
	}
	if inst.NodeStates["C"].Status != StatusBlocked {
		t.Errorf("C should remain Blocked, got %s", inst.NodeStates["C"].Status)
	}
	// C 仍 blocked → DAG 未完成，但已卡住
	if sched.IsDAGComplete(dagID) {
		t.Error("DAG should not be complete while C is Blocked")
	}
	if !sched.IsDAGStuck(dagID) {
		t.Error("DAG should be stuck after B failed")
	}
}

func TestStep_NoReadyNodesButComplete(t *testing.T) {
	sched := NewDAGSchedulerV0(WithExecutor(&mockExecutor{results: map[string]error{}}))
	inst, err := sched.SubmitDAG(context.Background(), newChainSpec("chain-done"))
	if err != nil {
		t.Fatalf("SubmitDAG: %v", err)
	}
	dagID := inst.ID

	if err := sched.RunAll(context.Background(), dagID); err != nil {
		t.Fatalf("RunAll: %v", err)
	}
	if !sched.IsDAGComplete(dagID) {
		t.Fatal("expected complete before idle Step")
	}
	if len(sched.GetReadyNodes(dagID)) != 0 {
		t.Fatal("expected no ready nodes")
	}

	// 无 ready 节点时 Step 应 no-op
	if err := sched.Step(context.Background(), dagID); err != nil {
		t.Fatalf("Step failed: %v", err)
	}
	if !sched.IsDAGComplete(dagID) {
		t.Error("DAG should remain complete")
	}
}

func TestStep_CycleRejectedAtSubmit(t *testing.T) {
	sched := NewDAGSchedulerV0()
	spec := DAGSpec{
		ID: "cycle",
		Nodes: map[string]*Node{
			"A": {ID: "A"},
			"B": {ID: "B"},
		},
		Edges: []*Edge{
			{From: "A", To: "B"},
			{From: "B", To: "A"},
		},
	}
	_, err := sched.SubmitDAG(context.Background(), spec)
	if err == nil {
		t.Fatal("expected cycle error at SubmitDAG")
	}
	if len(sched.GetReadyNodes("cycle")) != 0 {
		t.Errorf("expected 0 ready nodes, got %d", len(sched.GetReadyNodes("cycle")))
	}
}

// ============================================================
// 存储 / 查询 / RunAll（原有测试）
// ============================================================

func TestJSONStoreSaveLoad(t *testing.T) {
	dir := t.TempDir()
	store, err := NewJSONStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 5, 12, 0, 0, 0, time.UTC)
	spec := &DAGSpec{
		ID:    "persist",
		Nodes: map[string]*Node{"a": {ID: "a"}},
	}
	inst := NewDAGInstance(spec, now)
	inst.NodeStates["a"].Status = StatusReady
	if err := store.Save(inst); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "persist.json")); err != nil {
		t.Fatalf("expected json file: %v", err)
	}
	loaded, err := store.LoadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded) != 1 || loaded[0].ID != "persist" {
		t.Fatalf("unexpected loaded: %+v", loaded)
	}
}

func TestRestoreFromStore(t *testing.T) {
	dir := t.TempDir()
	store, _ := NewJSONStore(dir)
	now := time.Date(2026, 7, 5, 12, 0, 0, 0, time.UTC)
	spec := &DAGSpec{ID: "restored", Nodes: map[string]*Node{"x": {ID: "x"}}}
	inst := NewDAGInstance(spec, now)
	_ = store.Save(inst)

	sched := NewDAGSchedulerV0(WithStore(store))
	got, ok := sched.GetDAG("restored")
	if !ok || got.ID != "restored" {
		t.Fatal("expected restored instance")
	}
}

func TestStepRunAllLinearDAG(t *testing.T) {
	now := time.Date(2026, 7, 5, 12, 0, 0, 0, time.UTC)
	sched := NewDAGSchedulerV0(
		WithClock(MockClock{Current: now}),
		WithExecutor(NoopExecutor{}),
		WithMaxConcurrency(2),
		WithNodeTimeout(5*time.Second),
	)
	spec := DAGSpec{
		ID: "linear",
		Nodes: map[string]*Node{
			"a": {ID: "a"},
			"b": {ID: "b"},
		},
		Edges: []*Edge{{From: "a", To: "b"}},
	}
	inst, err := sched.SubmitDAG(context.Background(), spec)
	if err != nil {
		t.Fatal(err)
	}
	if err := sched.RunAll(context.Background(), inst.ID); err != nil {
		t.Fatalf("RunAll: %v", err)
	}
	if inst.NodeStates["a"].Status != StatusCompleted {
		t.Fatalf("a: %s", inst.NodeStates["a"].Status)
	}
	if inst.NodeStates["b"].Status != StatusCompleted {
		t.Fatalf("b: %s", inst.NodeStates["b"].Status)
	}
	if !sched.IsDAGComplete(inst.ID) {
		t.Fatal("expected complete")
	}
}

func TestGetReadyBlockedNodes(t *testing.T) {
	sched := NewDAGSchedulerV0()
	spec := DAGSpec{
		ID: "qb",
		Nodes: map[string]*Node{
			"a": {ID: "a"},
			"b": {ID: "b"},
		},
		Edges: []*Edge{{From: "a", To: "b"}},
	}
	_, _ = sched.SubmitDAG(context.Background(), spec)
	if ready := sched.GetReadyNodes("qb"); len(ready) != 1 || ready[0] != "a" {
		t.Fatalf("ready: %v", ready)
	}
	if blocked := sched.GetBlockedNodes("qb"); len(blocked) != 1 || blocked[0] != "b" {
		t.Fatalf("blocked: %v", blocked)
	}
}

func TestIsDAGStuckOnFailure(t *testing.T) {
	sched := NewDAGSchedulerV0(
		WithExecutor(FuncExecutor(func(context.Context, *DAGInstance, string) (string, error) {
			return "", fmt.Errorf("boom")
		})),
	)
	spec := DAGSpec{
		ID: "fail",
		Nodes: map[string]*Node{
			"a": {ID: "a"},
			"b": {ID: "b"},
		},
		Edges: []*Edge{{From: "a", To: "b"}},
	}
	_, _ = sched.SubmitDAG(context.Background(), spec)
	_ = sched.Step(context.Background(), "fail")
	if !sched.IsDAGStuck("fail") {
		t.Fatal("expected stuck after upstream failure")
	}
}
