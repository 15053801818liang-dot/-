"""事件总账 — MEMORY_EVENT_LOG_V0_SEALED"""
import json
import os
from datetime import datetime, timezone


def _event_path():
    return os.environ.get("MEMORY_EVENT_PATH", "workspace/memory_events.jsonl")


def emit(event_type: str, source_id: str, payload: dict = None):
    """记录生命周期事件。append-only，永不删。"""
    path = _event_path()
    entry = {
        "event_type": event_type,
        "source_id": source_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_events(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
