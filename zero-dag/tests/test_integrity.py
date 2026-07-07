import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(base, "workspace_test"), exist_ok=True)
os.environ["MEMORY_CORE_PATH"] = os.path.join(base, "workspace_test", "int_core.jsonl")
os.environ["MEMORY_INBOX_PATH"] = os.path.join(base, "workspace_test", "int_inbox.jsonl")
os.environ["MEMORY_REVIEW_PATH"] = os.path.join(base, "workspace_test", "int_review.jsonl")
os.environ["MEMORY_EVENT_PATH"] = os.path.join(base, "workspace_test", "int_events.jsonl")
import memory.integrity
importlib.reload(memory.integrity)


def _clean():
    for k in ["MEMORY_CORE_PATH", "MEMORY_INBOX_PATH", "MEMORY_REVIEW_PATH", "MEMORY_EVENT_PATH"]:
        try: os.remove(os.environ[k])
        except FileNotFoundError: pass


def test_clean_integrity():
    _clean()
    result = memory.integrity.run_integrity_check()
    assert result["clean"] is True


def test_dirty_integrity():
    _clean()
    with open(os.environ["MEMORY_CORE_PATH"], "w") as f:
        f.write(json.dumps({"id": "c9", "source_id": "ghost", "content": "orphan", "tags": ["orphan"]}) + "\n")
    result = memory.integrity.run_integrity_check()
    assert not result["clean"]
    assert any(i["type"] == "core_without_approved_event" for i in result["inconsistencies"])
