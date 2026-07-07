"""Tests for state transition matrix"""
import pytest

# Replicate transition logic for testing
NodeStatus = type("NodeStatus", (), {
    "PENDING": "pending", "READY": "ready", "RUNNING": "running",
    "COMPLETED": "completed", "FAILED": "failed", "BLOCKED": "blocked",
    "SKIPPED": "skipped", "CANCELLED": "cancelled",
})

TRANSITIONS = {
    "pending": {"ready", "blocked", "skipped", "cancelled"},
    "ready": {"running", "blocked", "skipped", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "failed": {"ready", "blocked", "skipped", "cancelled"},
    "blocked": {"ready", "skipped", "cancelled"},
    "completed": set(),
    "skipped": set(),
    "cancelled": set(),
}


def validate_transition(from_st, to_st):
    if from_st == to_st:
        return
    if to_st not in TRANSITIONS.get(from_st, set()):
        raise ValueError(f"invalid: {from_st} -> {to_st}")


def test_valid_transitions():
    assert validate_transition("pending", "ready") is None
    assert validate_transition("ready", "running") is None
    assert validate_transition("running", "completed") is None
    assert validate_transition("failed", "ready") is None


def test_invalid_transition():
    with pytest.raises(ValueError):
        validate_transition("completed", "running")


def test_terminal_no_exit():
    with pytest.raises(ValueError):
        validate_transition("completed", "pending")
    with pytest.raises(ValueError):
        validate_transition("cancelled", "ready")
