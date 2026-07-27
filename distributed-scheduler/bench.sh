#!/usr/bin/env bash
# 端到端压测 + 崩溃恢复冒烟脚本（Linux/POSIX）。
# 用法: ./bench.sh [workers] [tasks]
set -euo pipefail
cd "$(dirname "$0")/build"

WORKERS="${1:-200}"
TASKS="${2:-20000}"
PORT=5599

echo "=== 1. 端到端吞吐 (workers=$WORKERS tasks=$TASKS) ==="
rm -f neuralhub.wal
./hub --port $PORT --no-flush > hub.out 2>&1 &
HUB=$!
sleep 1
./worker_bench "$WORKERS" "$TASKS" "tcp://localhost:$PORT"
kill -TERM $HUB 2>/dev/null || true
wait $HUB 2>/dev/null || true
echo "--- hub metrics ---"
grep METRICS hub.out || true

echo
echo "=== 2. 崩溃恢复 (kill -9 then replay) ==="
rm -f neuralhub.wal
./hub --port $PORT > hub.out 2>&1 &
HUB=$!
sleep 0.5
./worker_bench "$WORKERS" 300000 "tcp://localhost:$PORT" > /dev/null 2>&1 &
B=$!
sleep 0.6
kill -9 $HUB $B 2>/dev/null || true
wait 2>/dev/null || true
echo "WAL size after crash: $(stat -c%s neuralhub.wal 2>/dev/null || echo 0) bytes"
./hub --port $((PORT+1)) > hub2.out 2>&1 &
HUB2=$!
sleep 0.5
./worker_bench "$WORKERS" 0 "tcp://localhost:$((PORT+1))"
kill -TERM $HUB2 2>/dev/null || true
wait $HUB2 2>/dev/null || true
grep -E "replay|METRICS" hub2.out || true
