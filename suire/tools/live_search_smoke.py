#!/usr/bin/env python3
"""V0.3.1 Live Search Smoke — 真实 API 最小回归（本地手动运行，不进 CI 假数据）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evidence_gate import EvidenceItem, assess_evidence, filter_evidence_items
from core.input_packet import parse_input
from core.intent_router import route_intent
from core.safety_gate import check_safety
from core.tool_contract import (
    ToolRequest,
    build_tool_request,
    execute_tool_request,
    process_contract_turn,
)
from tools.search_api import SearchAPIAdapter
from tools.search_config import SearchConfig
from tools.search_diagnostic import AdapterDiagnostic


DEFAULT_QUERY = "GPT price"
REPORT_DIR = ROOT / "reports"


@dataclass
class SmokeReport:
    timestamp: str
    provider: str
    api_key_present: bool
    query: str
    status: str
    error: str
    item_count: int
    citations_count: int
    missing_url_count: int
    ads_rejected_count: int
    elapsed_ms: int
    smoke_pass: bool
    smoke_notes: List[str] = field(default_factory=list)
    diagnostic: Optional[AdapterDiagnostic] = None

    def to_log_lines(self) -> List[str]:
        lines = [
            f"timestamp={self.timestamp}",
            f"provider={self.provider}",
            f"api_key_present={self.api_key_present}",
            f'query="{self.query}"',
            f"status={self.status}",
            f"error={self.error or 'none'}",
            f"item_count={self.item_count}",
            f"citations_count={self.citations_count}",
            f"missing_url_count={self.missing_url_count}",
            f"ads_rejected_count={self.ads_rejected_count}",
            f"elapsed_ms={self.elapsed_ms}",
            f"smoke_pass={self.smoke_pass}",
        ]
        if self.diagnostic is not None:
            lines.extend(self.diagnostic.to_log_lines())
        for note in self.smoke_notes:
            lines.append(f"note={note}")
        return lines

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _count_raw_metrics(raw_items: List[Dict[str, Any]], source_policy: str) -> tuple[int, int]:
    missing_url = sum(1 for it in raw_items if not it.get("url"))
    evidence_items = [
        EvidenceItem(
            title=str(it.get("title", "")),
            snippet=str(it.get("snippet", "")),
            source=str(it.get("source", "")),
            url=it.get("url"),
            trust_score=float(it.get("trust_score", 1.0)),
        )
        for it in raw_items
    ]
    _, rejections = filter_evidence_items(evidence_items, source_policy=source_policy)
    ads_rejected = sum(1 for r in rejections if "rejected_ad_source" in r)
    return missing_url, ads_rejected


def _evaluate_pass(report: SmokeReport) -> tuple[bool, List[str]]:
    notes: List[str] = []
    if not report.api_key_present:
        notes.append("SKIP: no API key — set SUIREN_SEARCH_API_KEY for live smoke")
        return False, notes

    if report.status == "tool_failed" and report.error == "not_configured":
        notes.append("FAIL: api_key_present but adapter returned not_configured")
        return False, notes

    if report.status not in ("ok", "tool_failed", "insufficient_evidence"):
        notes.append(f"FAIL: unexpected status={report.status}")
        return False, notes

    if report.status == "ok":
        if report.citations_count < 1:
            notes.append("FAIL: status=ok but citations_count < 1")
            return False, notes
        if report.missing_url_count != 0:
            notes.append("FAIL: missing_url_count must be 0 when status=ok")
            return False, notes
        notes.append("PASS: live search returned gated evidence with citations")
        return True, notes

    notes.append(f"PASS_WITH_TOOL_FAILED: explicit failure ({report.error or report.status})")
    return True, notes


def run_live_smoke(
    query: str = DEFAULT_QUERY,
    *,
    config: Optional[SearchConfig] = None,
    adapter: Optional[SearchAPIAdapter] = None,
) -> SmokeReport:
    """执行 live smoke 并返回结构化报告（不输出 API key）。"""
    cfg = config or SearchConfig.from_env()
    backend = adapter or SearchAPIAdapter(config=cfg)
    api_key_present = cfg.is_configured

    t0 = time.perf_counter()
    user_text = f"搜索: {query}"

    packet = parse_input(user_text)
    safety = check_safety(packet)
    intent = route_intent(packet)
    evidence = assess_evidence(packet, intent, safety)
    tool_request = build_tool_request(packet, intent, evidence)

    raw_items: List[Dict[str, Any]] = []
    gated_status = "tool_failed"
    gated_error = "no_request"
    citations_count = 0
    item_count = 0
    diagnostic: Optional[AdapterDiagnostic] = None

    if tool_request and safety.allowed:
        raw = backend.invoke(tool_request)
        if hasattr(backend, "last_diagnostic"):
            diagnostic = getattr(backend, "last_diagnostic")
        raw_items = list(raw.items or [])
        gated = execute_tool_request(tool_request, backend, evidence=evidence)
        gated_status = gated.status
        gated_error = gated.error or raw.error
        citations_count = len(gated.citations or [])
        item_count = len(gated.items or [])

        turn = process_contract_turn(user_text, backend=backend)
        if turn.tool_result is not None:
            gated_status = turn.tool_result.status
            gated_error = turn.tool_result.error or gated_error
            citations_count = len(turn.tool_result.citations or [])
            item_count = len(turn.tool_result.items or [])
    elif not safety.allowed:
        gated_status = "tool_failed"
        gated_error = safety.blocked_reason or "blocked"

    missing_url_count, ads_rejected_count = _count_raw_metrics(
        raw_items,
        source_policy=tool_request.source_policy if tool_request else "no_ads",
    )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    report = SmokeReport(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        provider=cfg.provider,
        api_key_present=api_key_present,
        query=query,
        status=gated_status,
        error=gated_error if gated_status != "ok" else "",
        item_count=item_count,
        citations_count=citations_count,
        missing_url_count=missing_url_count,
        ads_rejected_count=ads_rejected_count,
        elapsed_ms=elapsed_ms,
        smoke_pass=False,
        smoke_notes=[],
        diagnostic=diagnostic,
    )
    passed, notes = _evaluate_pass(report)
    report.smoke_pass = passed
    report.smoke_notes = notes
    return report


def write_report(report: SmokeReport, out_dir: Path = REPORT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "live_search_smoke_report.txt"
    content = "\n".join(report.to_log_lines()) + "\n"
    path.write_text(content, encoding="utf-8")
    json_path = out_dir / "live_search_smoke_report.json"
    json_path.write_text(report.to_json(), encoding="utf-8")
    return path


def _assert_no_secret_leak(text: str, api_key: str) -> None:
    if api_key and api_key in text:
        raise RuntimeError("API key leaked into smoke output")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Suiren V0.3.1 live search smoke")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="search query")
    parser.add_argument("--json", action="store_true", help="print JSON to stdout")
    parser.add_argument("--no-write", action="store_true", help="skip report file")
    args = parser.parse_args(argv)

    cfg = SearchConfig.from_env()
    report = run_live_smoke(args.query, config=cfg)
    output = report.to_json() if args.json else "\n".join(report.to_log_lines())
    _assert_no_secret_leak(output, cfg.api_key)

    print(output)
    if not args.no_write:
        path = write_report(report)
        print(f"report_written={path}", file=sys.stderr)

    return 0 if report.smoke_pass or not cfg.is_configured else 1


if __name__ == "__main__":
    raise SystemExit(main())
