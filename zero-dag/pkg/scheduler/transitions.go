package scheduler

import "fmt"

var transitionMatrix = map[NodeStatus]map[NodeStatus]bool{
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

func ValidateTransition(from, to NodeStatus) error {
	if from == to {
		return nil
	}
	targets, ok := transitionMatrix[from]
	if !ok {
		return fmt.Errorf("unknown source status: %s", from)
	}
	if !targets[to] {
		return fmt.Errorf("invalid transition: %s -> %s", from, to)
	}
	return nil
}

var instanceTransitions = map[InstanceStatus]map[InstanceStatus]bool{
	InstanceRunning: {
		InstanceCompleted: true,
		InstanceFailed:    true,
	},
}

func ValidateInstanceTransition(from, to InstanceStatus) error {
	if from == to {
		return nil
	}
	targets, ok := instanceTransitions[from]
	if !ok {
		return fmt.Errorf("unknown instance status: %s", from)
	}
	if !targets[to] {
		return fmt.Errorf("invalid instance transition: %s -> %s", from, to)
	}
	return nil
}
