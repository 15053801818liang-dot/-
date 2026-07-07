import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

base = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(base, "workspace_test"), exist_ok=True)
IP = os.path.join(base, "workspace_test", "review_inbox.jsonl")
CP = os.path.join(base, "workspace_test", "review_core.jsonl")
RP = os.path.join(base, "workspace_test", "review_log.jsonl")
os.environ["MEMORY_INBOX_PATH"] = IP
os.environ["MEMORY_CORE_PATH"] = CP
os.environ["MEMORY_REVIEW_PATH"] = RP
for mod in ["memory.inbox", "memory.review_gate"]:
    if mod in sys.modules:
        del sys.modules[mod]


def test_review_approve():
    for p in [IP, CP, RP]:
        try: os.remove(p)
        except FileNotFoundError: pass
    from memory.inbox import write_inbox
    from memory.review_gate import review
    r = write_inbox("test memory for approval", tags=["test"])
    result = review(r["id"], "approve")
    assert result["status"] == "approved"
    assert result["core_id"] is not None


def test_review_reject():
    from memory.inbox import write_inbox
    from memory.review_gate import review
    r = write_inbox("test memory for rejection", tags=["test"])
    result = review(r["id"], "reject")
    assert result["status"] == "rejected"


def test_review_not_found():
    from memory.review_gate import review
    result = review("nonexistent-id", "approve")
    assert result["status"] == "not_found"


def test_review_invalid_action():
    import pytest
    from memory.review_gate import review
    with pytest.raises(ValueError):
        review("id", "delete")
