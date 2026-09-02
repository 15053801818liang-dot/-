package scheduler

import "fmt"

// validateTransition 校验节点状态是否允许跳转。
func validateTransition(from, to NodeStatus) error {
	transitions := map[NodeStatus]map[NodeStatus]bool{
		StatusPending: {
			StatusReady:     true,
			StatusBlocked:   true,
			StatusSkipped:   true,
			StatusCancelled: true,
		},
		StatusReady: {
			StatusRunning:   true,
			StatusBlocked:   true,
			StatusSkipped:   true,
			StatusCancelled: true,
		},
		StatusRunning: {
			StatusCompleted: true,
			StatusFailed:    true,
			StatusCancelled: true,
		},
		StatusFailed: {
			StatusReady:     true,
			StatusBlocked:   true,
			StatusSkipped:   true,
			StatusCancelled: true,
		},
		StatusBlocked: {
			StatusReady:     true,
			StatusSkipped:   true,
			StatusCancelled: true,
		},
		StatusCompleted: {},
		StatusSkipped:   {},
		StatusCancelled: {},
	}

	if _, ok := transitions[from]; !ok {
		return fmt.Errorf("scheduler: unknown source status %s", from)
	}
	if allowed, ok := transitions[from][to]; ok && allowed {
		return nil
	}
	if from.IsTerminal() {
		return fmt.Errorf("scheduler: cannot transition from terminal status %s to %s", from, to)
	}
	return fmt.Errorf("scheduler: invalid transition from %s to %s", from, to)
}
