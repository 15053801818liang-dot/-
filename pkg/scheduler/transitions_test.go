package scheduler

import "testing"

func TestValidateTransitionAllowed(t *testing.T) {
	allowed := []struct{ from, to NodeStatus }{
		{StatusPending, StatusReady},
		{StatusPending, StatusBlocked},
		{StatusPending, StatusSkipped},
		{StatusPending, StatusCancelled},
		{StatusReady, StatusRunning},
		{StatusReady, StatusBlocked},
		{StatusReady, StatusSkipped},
		{StatusReady, StatusCancelled},
		{StatusRunning, StatusCompleted},
		{StatusRunning, StatusFailed},
		{StatusRunning, StatusCancelled},
		{StatusFailed, StatusReady},
		{StatusFailed, StatusBlocked},
		{StatusFailed, StatusSkipped},
		{StatusFailed, StatusCancelled},
		{StatusBlocked, StatusReady},
		{StatusBlocked, StatusSkipped},
		{StatusBlocked, StatusCancelled},
	}
	for _, tc := range allowed {
		if err := validateTransition(tc.from, tc.to); err != nil {
			t.Errorf("expected allowed %s -> %s, got %v", tc.from, tc.to, err)
		}
	}
}

func TestValidateTransitionDenied(t *testing.T) {
	denied := []struct{ from, to NodeStatus }{
		{StatusPending, StatusRunning},
		{StatusPending, StatusCompleted},
		{StatusPending, StatusFailed},
		{StatusReady, StatusPending},
		{StatusReady, StatusFailed},
		{StatusReady, StatusCompleted},
		{StatusRunning, StatusReady},
		{StatusRunning, StatusSkipped},
		{StatusRunning, StatusBlocked},
		{StatusFailed, StatusRunning},
		{StatusFailed, StatusCompleted},
		{StatusBlocked, StatusPending},
		{StatusBlocked, StatusRunning},
		{StatusBlocked, StatusFailed},
		{StatusCompleted, StatusReady},
		{StatusSkipped, StatusReady},
		{StatusCancelled, StatusRunning},
	}
	for _, tc := range denied {
		if err := validateTransition(tc.from, tc.to); err == nil {
			t.Errorf("expected denied %s -> %s", tc.from, tc.to)
		}
	}
}

func TestValidateTransitionTerminal(t *testing.T) {
	terminals := []NodeStatus{StatusCompleted, StatusSkipped, StatusCancelled}
	targets := []NodeStatus{
		StatusPending, StatusReady, StatusRunning, StatusFailed,
		StatusBlocked, StatusCompleted, StatusSkipped, StatusCancelled,
	}
	for _, from := range terminals {
		for _, to := range targets {
			if from == to {
				continue
			}
			err := validateTransition(from, to)
			if err == nil {
				t.Errorf("terminal %s should not transition to %s", from, to)
			}
		}
	}
}

func TestValidateTransitionUnknownSource(t *testing.T) {
	err := validateTransition(NodeStatus("unknown"), StatusReady)
	if err == nil {
		t.Fatal("expected error for unknown source status")
	}
}
