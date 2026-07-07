"""人工审核 — MEMORY_REVIEW_GATE_V0_SEALED"""
import json
import os
import uuid
from datetime import datetime, timezone


def _get_paths():
    return (
        os.environ.get("MEMORY_INBOX_PATH", "workspace/inbox.jsonl"),
        os.environ.get("MEMORY_CORE_PATH", "workspace/core_memory.jsonl"),
        os.environ.get("MEMORY_REVIEW_PATH", "workspace/review_log.jsonl"),
    )


def review(source_id: str, action: str) -> dict:
    """人工审核：approve 或 reject。写入审计日志 + 核心区。"""
    if action not in ("approve", "reject"):
        raise ValueError("action must be approve or reject")

    inbox_path, core_path, review_path = _get_paths()
    inbox_items = _load_path(inbox_path)
    target = next((item for item in inbox_items if item["id"] == source_id), None)
    if not target:
        return {"status": "not_found", "id": source_id}

    os.makedirs(os.path.dirname(review_path), exist_ok=True)
    with open(review_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "action": action,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False) + "\n")

    if action == "approve":
        core_item = {
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "content": target["content"],
            "tags": target.get("tags", []),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        os.makedirs(os.path.dirname(core_path), exist_ok=True)
        with open(core_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(core_item, ensure_ascii=False) + "\n")
        return {"status": "approved", "core_id": core_item["id"]}
    return {"status": "rejected", "id": source_id}


def _load_path(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
