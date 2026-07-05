package scheduler

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

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
