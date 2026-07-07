"""Tests for memory/inbox.py"""
import sys, os, json
sys.path.insert(0, ".")
os.environ["MEMORY_INBOX_PATH"] = "workspace/test_inbox.jsonl"


def test_write_and_dedup():
    from memory.inbox import write_inbox
    # Clean
    try:
        os.remove("workspace/test_inbox.jsonl")
    except FileNotFoundError:
        pass
    r1 = write_inbox("memory alpha", tags=["dag", "test"])
    assert r1["status"] == "created"
    r2 = write_inbox("memory alpha", tags=["dag", "test"])
    assert r2["status"] == "duplicate"


def test_write_different_content():
    from memory.inbox import write_inbox
    r = write_inbox("memory beta", tags=["pangu"], source_id="src-001")
    assert r["status"] == "created"
    assert r["id"] == "src-001"
