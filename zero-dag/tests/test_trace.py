import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(base, "workspace_test", "trace.jsonl")
os.makedirs(os.path.dirname(P), exist_ok=True)
os.environ["MEMORY_EVENT_PATH"] = P

import memory.event_log
importlib.reload(memory.event_log)
import memory.trace
importlib.reload(memory.trace)


def test_trace_full_lifecycle():
    try: os.remove(P)
    except FileNotFoundError: pass
    sid = "trace-001"
    from memory.event_log import emit
    emit("candidate_created", sid)
    emit("inbox_written", sid)
    emit("review_approved", sid)
    from memory.trace import trace_memory, derive_status
    timeline = trace_memory(sid)
    assert len(timeline) == 3
    assert derive_status(timeline) == "promoted"


def test_trace_nonexistent():
    from memory.trace import trace_memory
    assert trace_memory("ghost-id") == []
