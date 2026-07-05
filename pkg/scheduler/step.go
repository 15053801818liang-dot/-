package scheduler

import (
	"context"
	"fmt"
	"sync"
)

// Step 并发执行所有 ready 节点（限流 + 超时），完成后推进 blocked 下游。
func (s *DAGSchedulerV0) Step(ctx context.Context, dagID string) error {
	inst, ok := s.GetDAG(dagID)
	if !ok {
		return fmt.Errorf("scheduler: dag %s not found", dagID)
	}

	s.promoteBlockedNodes(ctx, inst)
	ready := s.GetReadyNodes(dagID)
	if len(ready) == 0 {
		return nil
	}

	sem := make(chan struct{}, s.maxConcurrency)
	var wg sync.WaitGroup
	errCh := make(chan error, len(ready))

	for _, nodeID := range ready {
		wg.Add(1)
		go func(nodeID string) {
			defer wg.Done()
			select {
			case sem <- struct{}{}:
				defer func() { <-sem }()
			case <-ctx.Done():
				errCh <- ctx.Err()
				return
			}
			if err := s.runNode(ctx, inst, nodeID); err != nil {
				errCh <- err
			}
		}(nodeID)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			return err
		}
	}
	s.promoteBlockedNodes(ctx, inst)
	return nil
}

func (s *DAGSchedulerV0) runNode(ctx context.Context, inst *DAGInstance, nodeID string) error {
	if err := s.SetNodeRunning(ctx, inst, nodeID); err != nil {
		return err
	}

	nodeCtx, cancel := context.WithTimeout(ctx, s.nodeTimeout)
	defer cancel()

	start := s.clock.Now()
	output, err := s.executor.Execute(nodeCtx, inst, nodeID)
	elapsed := s.clock.Now().Sub(start).Milliseconds()

	s.mu.Lock()
	if st, ok := inst.NodeStates[nodeID]; ok {
		st.DurationMS = elapsed
	}
	s.mu.Unlock()

	if err != nil {
		return s.SetNodeFailed(ctx, inst, nodeID, err.Error())
	}
	return s.SetNodeCompleted(ctx, inst, nodeID, output)
}

func (s *DAGSchedulerV0) promoteBlockedNodes(ctx context.Context, inst *DAGInstance) {
	s.mu.Lock()
	var toReady []string
	for nodeID, st := range inst.NodeStates {
		if st.Status != StatusBlocked {
			continue
		}
		if depsSatisfied(inst, nodeID) {
			toReady = append(toReady, nodeID)
		}
	}
	s.mu.Unlock()

	for _, nodeID := range toReady {
		_ = s.SetNodeReady(ctx, inst, nodeID)
	}
}
