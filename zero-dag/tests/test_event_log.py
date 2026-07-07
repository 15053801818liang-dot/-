import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(base, "workspace_test", "elog.jsonl")
os.makedirs(os.path.dirname(P), exist_ok=True)


def test_emit_and_read():
    os.environ["MEMORY_EVENT_PATH"] = P
    import memory.event_log
    importlib.reload(memory.event_log)
    try: os.remove(P)
    except FileNotFoundError: pass
    memory.event_log.emit("candidate_created", "src-001", {"action": "test"})
    memory.event_log.emit("inbox_written", "src-001", {"action": "test"})
    memory.event_log.emit("review_approved", "src-001", {"action": "approve"})
    with open(P) as f:
        events = [json.loads(line) for line in f]
    assert len(events) == 3
