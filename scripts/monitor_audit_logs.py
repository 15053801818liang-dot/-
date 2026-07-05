#!/usr/bin/env python3
"""盘古 · 御史台实时审计监视窗（终端版）。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def monitor_audit_logs(log_path: str = "workspace/logs/yushitai_audit.jsonl", *, interval: float = 1.0) -> None:
    """实时监控御史台审计流。"""
    path = Path(log_path)
    print("🔍 正在连接审计流... (按 Ctrl+C 停止)")
    try:
        while True:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                tail = lines[-10:] if len(lines) >= 10 else lines
                sys.stdout.write("\033[2J\033[H")  # clear screen (terminal)
                print("═══════════════════════════════════════════════════════════")
                print("🧠 盘古 · 御史台实时审计监视窗")
                print(f"📂 源: {path}  |  总行数: {len(lines)}")
                print("═══════════════════════════════════════════════════════════\n")
                for line in tail:
                    print(line)
            except FileNotFoundError:
                sys.stdout.write("\033[2J\033[H")
                print("⏳ 等待审计日志生成... (请先运行: WORKSPACE_DIR=workspace go run ./cmd/go-scheduler/)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n🛑 监视器已停止。")


def main() -> int:
    parser = argparse.ArgumentParser(description="御史台审计流监视器")
    parser.add_argument(
        "--log-path",
        default="workspace/logs/yushitai_audit.jsonl",
        help="审计日志路径",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="刷新间隔（秒）")
    args = parser.parse_args()
    monitor_audit_logs(args.log_path, interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
