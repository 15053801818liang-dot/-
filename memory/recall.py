"""候选检索 — MEMORY_RECALL_V0_SEALED"""
import json
import os


def _inbox_path():
    return os.environ.get("MEMORY_INBOX_PATH", "workspace/inbox.jsonl")


def recall(tags: list[str] = None, keyword: str = None, top_k: int = 5) -> list[dict]:
    """检索候选区，按 tags 和 keyword 匹配，返回 top_k 条。"""
    if not tags and not keyword:
        raise ValueError("empty query: must provide tags or keyword")
    path = _inbox_path()
    items = _load_inbox(path)
    results = []
    for item in items:
        item_tags = item.get("tags", [])
        if tags and not any(t in item_tags for t in tags):
            continue
        if keyword and keyword.lower() not in item.get("content", "").lower():
            continue
        results.append(item)
    return results[:top_k]


def _load_inbox(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
