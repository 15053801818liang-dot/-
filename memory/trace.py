"""时间线回放 — MEMORY_TRACE_V0_SEALED"""
import json
import os


def _event_path():
    return os.environ.get("MEMORY_EVENT_PATH", "workspace/memory_events.jsonl")


def trace_memory(source_id: str) -> list[dict]:
    """按 source_id 回放完整生命周期时间线。"""
    path = _event_path()
    events = _load_path(path)
    timeline = [e for e in events if e.get("source_id") == source_id]
    return sorted(timeline, key=lambda x: x.get("timestamp", ""))


def derive_status(timeline: list[dict]) -> str:
    """从时间线推导当前状态。"""
    if not timeline:
        return "unknown"
    event_types = {e.get("event_type") for e in timeline}
    if "review_approved" in event_types:
        return "promoted"
    if "review_rejected" in event_types:
        return "rejected"
    if "inbox_written" in event_types:
        return "in_inbox"
    if "candidate_created" in event_types:
        return "candidate"
    return "orphan"


def _load_path(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
