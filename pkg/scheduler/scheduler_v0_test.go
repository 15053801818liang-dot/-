package scheduler

import (
	"context"
	"testing"
	"time"
)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type recordingEmitter struct {
	events []string
}

func (e *recordingEmitter) record(name string) {
	e.events = append(e.events, name)
}

func (e *recordingEmitter) EmitReady(dagID, nodeID string) {
	e.record("ready:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitRunning(dagID, nodeID string) {
	e.record("running:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitCompleted(dagID, nodeID, output string) {
	e.record("completed:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitFailed(dagID, nodeID, errMsg string) {
	e.record("failed:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitBlocked(dagID, nodeID, reason string) {
	e.record("blocked:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitSkipped(dagID, nodeID, reason string) {
	e.record("skipped:" + dagID + "/" + nodeID)
}
func (e *recordingEmitter) EmitCancelled(dagID, nodeID, reason string) {
	e.record("cancelled:" + dagID + "/" + nodeID)
}

func newTestInstance(t *testing.T) (*DAGSchedulerV0, *DAGInstance) {
	t.Helper()
	now := time.Date(2026, 7, 5, 12, 0, 0, 0, time.UTC)
	spec := &DAGSpec{
		ID: "test-dag",
		Nodes: map[string]*Node{
			"a": {ID: "a", Script: "a.py"},
			"b": {ID: "b", Script: "b.py"},
		},
		Edges: []*Edge{{From: "a", To: "b"}},
	}
	inst := NewDAGInstance(spec, now)
	emitter := &recordingEmitter{}
	sched := NewDAGSchedulerV0(
		WithClock(fixedClock{t: now}),
		WithNodeEvents(emitter),
	)
	return sched, inst
}

func TestHappyPath(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	if err := sched.SetNodeReady(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeReady: %v", err)
	}
	if err := sched.SetNodeRunning(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeRunning: %v", err)
	}
	if err := sched.SetNodeCompleted(ctx, inst, "a", "ok"); err != nil {
		t.Fatalf("SetNodeCompleted: %v", err)
	}
	if inst.NodeStates["a"].Status != StatusCompleted {
		t.Fatalf("expected completed, got %s", inst.NodeStates["a"].Status)
	}
	if inst.NodeStates["a"].Output != "ok" {
		t.Fatalf("expected output ok, got %q", inst.NodeStates["a"].Output)
	}
}

func TestRetryPath(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	_ = sched.SetNodeReady(ctx, inst, "a")
	_ = sched.SetNodeRunning(ctx, inst, "a")
	if err := sched.SetNodeFailed(ctx, inst, "a", "boom"); err != nil {
		t.Fatalf("SetNodeFailed: %v", err)
	}
	if err := sched.SetNodeReady(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeReady retry: %v", err)
	}
	if err := sched.SetNodeRunning(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeRunning retry: %v", err)
	}
	if err := sched.SetNodeCompleted(ctx, inst, "a", "recovered"); err != nil {
		t.Fatalf("SetNodeCompleted: %v", err)
	}
}

func TestBlockedRecovery(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	if err := sched.SetNodeBlocked(ctx, inst, "a", "dep missing"); err != nil {
		t.Fatalf("SetNodeBlocked: %v", err)
	}
	if err := sched.SetNodeReady(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeReady from blocked: %v", err)
	}
	if inst.NodeStates["a"].Status != StatusReady {
		t.Fatalf("expected ready, got %s", inst.NodeStates["a"].Status)
	}
}

func TestReadyToBlockedAndBack(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	_ = sched.SetNodeReady(ctx, inst, "a")
	if err := sched.SetNodeBlocked(ctx, inst, "a", "upstream changed"); err != nil {
		t.Fatalf("SetNodeBlocked from ready: %v", err)
	}
	if err := sched.SetNodeReady(ctx, inst, "a"); err != nil {
		t.Fatalf("SetNodeReady after blocked: %v", err)
	}
}

func TestTerminalRejection(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	_ = sched.SetNodeReady(ctx, inst, "a")
	_ = sched.SetNodeRunning(ctx, inst, "a")
	_ = sched.SetNodeCompleted(ctx, inst, "a", "done")

	if err := sched.SetNodeReady(ctx, inst, "a"); err == nil {
		t.Fatal("expected error transitioning from completed")
	}
}

func TestBlockedCannotGoPending(t *testing.T) {
	// blocked -> pending 不在收紧矩阵中
	err := validateTransition(StatusBlocked, StatusPending)
	if err == nil {
		t.Fatal("blocked -> pending should be denied")
	}
}

func TestTopoSortOK(t *testing.T) {
	sched := NewDAGSchedulerV0()
	spec := &DAGSpec{
		ID: "dag",
		Nodes: map[string]*Node{
			"a": {ID: "a"},
			"b": {ID: "b"},
			"c": {ID: "c"},
		},
		Edges: []*Edge{
			{From: "a", To: "b"},
			{From: "a", To: "c"},
			{From: "b", To: "c"},
		},
	}
	order, err := sched.topoSort(spec)
	if err != nil {
		t.Fatalf("topoSort: %v", err)
	}
	if len(order) != 3 {
		t.Fatalf("expected 3 nodes, got %d", len(order))
	}
	// a must come before b and c; b before c
	pos := map[string]int{}
	for i, id := range order {
		pos[id] = i
	}
	if pos["a"] >= pos["b"] || pos["b"] >= pos["c"] {
		t.Fatalf("invalid order: %v", order)
	}
}

func TestTopoSortCycle(t *testing.T) {
	sched := NewDAGSchedulerV0()
	spec := &DAGSpec{
		ID: "cycle",
		Nodes: map[string]*Node{
			"a": {ID: "a"},
			"b": {ID: "b"},
		},
		Edges: []*Edge{
			{From: "a", To: "b"},
			{From: "b", To: "a"},
		},
	}
	_, err := sched.topoSort(spec)
	if err == nil {
		t.Fatal("expected cycle error")
	}
}

func TestContextCancellation(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if err := sched.SetNodeReady(ctx, inst, "a"); err == nil {
		t.Fatal("expected context error")
	}
}

func TestNodeNotFound(t *testing.T) {
	sched, inst := newTestInstance(t)
	ctx := context.Background()

	if err := sched.SetNodeReady(ctx, inst, "missing"); err == nil {
		t.Fatal("expected node not found error")
	}
}

func TestNewDAGInstanceAllPending(t *testing.T) {
	now := time.Now()
	spec := &DAGSpec{
		ID:    "d",
		Nodes: map[string]*Node{"x": {ID: "x"}},
	}
	inst := NewDAGInstance(spec, now)
	if inst.NodeStates["x"].Status != StatusPending {
		t.Fatalf("expected pending, got %s", inst.NodeStates["x"].Status)
	}
}
