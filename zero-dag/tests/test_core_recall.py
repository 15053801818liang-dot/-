import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(base, "workspace_test", "core.jsonl")
os.makedirs(os.path.dirname(P), exist_ok=True)


def test_core_recall():
    os.environ["MEMORY_CORE_PATH"] = P
    import memory.core_recall
    importlib.reload(memory.core_recall)
    try: os.remove(P)
    except FileNotFoundError: pass
    with open(P, "w", encoding="utf-8") as f:
        f.write(json.dumps({"id":"c1","source_id":"s1","content":"dag runs on kahn algo","tags":["dag","algo"],"approved_at":"2026-01-01T00:00:00"})+"\n")
        f.write(json.dumps({"id":"c2","source_id":"s2","content":"pangu uses symbolic kb","tags":["pangu","inference"],"approved_at":"2026-01-02T00:00:00"})+"\n")
    r1 = memory.core_recall.recall_core(tags=["dag"])
    assert len(r1) == 1
    r2 = memory.core_recall.recall_core(keyword="kahn")
    assert len(r2) == 1
    r3 = memory.core_recall.recall_core(tags=["nonexistent"])
    assert len(r3) == 0
