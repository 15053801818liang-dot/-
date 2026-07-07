"""候选写入 + 去重 — MEMORY_INBOX_V0_FIRST_WRITE_SEALED"""
import json
import os
import uuid
from datetime import datetime, timezone


def _inbox_path():
    return os.environ.get("MEMORY_INBOX_PATH", "workspace/inbox.jsonl")


def write_inbox(content: str, tags: list[str], source_id: str = None) -> dict:
    """写入候选记忆，自动去重。返回 status + id。"""
    path = _inbox_path()
    existing = _load_inbox(path)
    if any(
        item["content"] == content and set(item.get("tags", [])) == set(tags)
        for item in existing
    ):
        return {"status": "duplicate", "id": None}

    item = {
        "id": source_id or str(uuid.uuid4()),
        "content": content,
        "tags": tags,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"status": "created", "id": item["id"]}


def _load_inbox(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
