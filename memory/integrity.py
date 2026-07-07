"""一致性校验 — MEMORY_INTEGRITY_V0_SEALED（纯只读，绝不修改数据）"""
import json
import os


def run_integrity_check() -> dict:
    """纯只读一致性校验，返回 clean + inconsistencies 列表。"""
    core_path = os.environ.get("MEMORY_CORE_PATH", "workspace/core_memory.jsonl")
    inbox_path = os.environ.get("MEMORY_INBOX_PATH", "workspace/inbox.jsonl")
    review_path = os.environ.get("MEMORY_REVIEW_PATH", "workspace/review_log.jsonl")
    event_path = os.environ.get("MEMORY_EVENT_PATH", "workspace/memory_events.jsonl")

    core = _load_path(core_path)
    inbox = _load_path(inbox_path)
    reviews = _load_path(review_path)
    events = _load_path(event_path)

    inconsistencies = []

    # 规则1：每条 core 记录必须有对应的 review_approved 事件
    core_source_ids = {item.get("source_id") for item in core}
    approved_ids = {e.get("source_id") for e in events if e.get("event_type") == "review_approved"}
    for cid in core_source_ids:
        if cid not in approved_ids:
            inconsistencies.append({"type": "core_without_approved_event", "source_id": cid})

    # 规则2：每条 inbox 写入必须有 candidate_created + inbox_written
    inbox_ids = {item.get("id") for item in inbox}
    created_ids = {e.get("source_id") for e in events if e.get("event_type") == "candidate_created"}
    written_ids = {e.get("source_id") for e in events if e.get("event_type") == "inbox_written"}
    for iid in inbox_ids:
        if iid not in created_ids:
            inconsistencies.append({"type": "inbox_without_created", "source_id": iid})
        if iid not in written_ids:
            inconsistencies.append({"type": "inbox_without_written", "source_id": iid})

    # 规则3：review_log 与 ledger 计数一致
    rl_approved = sum(1 for r in reviews if r.get("action") == "approve")
    rl_rejected = sum(1 for r in reviews if r.get("action") == "reject")
    ledger_approved = sum(1 for e in events if e.get("event_type") == "review_approved")
    ledger_rejected = sum(1 for e in events if e.get("event_type") == "review_rejected")
    if rl_approved != ledger_approved or rl_rejected != ledger_rejected:
        inconsistencies.append({
            "type": "review_log_mismatch",
            "review_log": {"approve": rl_approved, "reject": rl_rejected},
            "ledger": {"approve": ledger_approved, "reject": ledger_rejected},
        })

    return {
        "clean": len(inconsistencies) == 0,
        "inconsistencies": inconsistencies,
        "stats": {"core": len(core), "inbox": len(inbox), "reviews": len(reviews), "events": len(events)},
    }


def _load_path(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []
