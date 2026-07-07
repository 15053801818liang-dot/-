import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(base, "workspace_test", "recall.jsonl")
os.makedirs(os.path.dirname(P), exist_ok=True)
os.environ["MEMORY_INBOX_PATH"] = P

import memory.inbox
importlib.reload(memory.inbox)
import memory.recall
importlib.reload(memory.recall)


def test_recall_by_tags():
    try: os.remove(P)
    except FileNotFoundError: pass
    from memory.inbox import write_inbox
    from memory.recall import recall
    write_inbox("important dag memory", tags=["dag", "critical"])
    write_inbox("another note", tags=["note"])
    results = recall(tags=["dag"])
    assert len(results) >= 1
    assert results[0]["content"] == "important dag memory"


def test_recall_by_keyword():
    from memory.recall import recall
    results = recall(keyword="dag")
    assert len(results) >= 1


def test_recall_empty_query():
    import pytest
    from memory.recall import recall
    with pytest.raises(ValueError):
        recall()
