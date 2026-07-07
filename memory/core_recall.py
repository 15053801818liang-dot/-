"""核心检索 — MEMORY_CORE_RECALL_V0_SEALED"""
import json
import os


def _core_path():
    return os.environ.get("MEMORY_CORE_PATH", "workspace/core_memory.jsonl")


def recall_core(tags: list[str] = None, keyword: str = None, top_k: int = 5) -> list[dict]:
    """检索核心区（已审核通过的永久记忆）。"""
    if not tags and not keyword:
        raise ValueError("empty query: must provide tags or keyword")
    path = _core_path()
    items = _load_path(path)
    results = []
    for item in items:
        item_tags = item.get("tags", [])
        if tags and not any(t in item_tags for t in tags):
            continue
        if keyword and keyword.lower() not in item.get("content", "").lower():
            continue
        results.append(item)
    return results[:top_k]


def _load_path(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
