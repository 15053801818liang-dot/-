#!/usr/bin/env bash
# 端到端演示：C++ 调度器 Hub + 2 个 Python LLM worker + 提交一批 prompt。
#   ./run_demo.sh --mock   # 不花钱、不用 key，验证协议全链路
#   ./run_demo.sh          # 真实推理（需要 ANTHROPIC_API_KEY）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCHED="$(cd "$HERE/.." && pwd)/distributed-scheduler"
PORT=5555
MOCK=""
[ "${1:-}" = "--mock" ] && MOCK="--mock"

# 需要时先编译 Hub
if [ ! -x "$SCHED/build/hub" ]; then
  echo "编译 Hub..."
  cmake -B "$SCHED/build" -S "$SCHED" -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build "$SCHED/build" -j >/dev/null
fi

cleanup() { kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT

rm -f "$SCHED/build/neuralhub.wal"
echo "启动 Hub (tcp://*:$PORT)..."
"$SCHED/build/hub" --port $PORT > /tmp/llm_hub.out 2>&1 &
HUB=$!
sleep 1

echo "启动 2 个 LLM worker..."
python3 "$HERE/llm_worker.py" --id w1 --endpoint "tcp://localhost:$PORT" $MOCK &
python3 "$HERE/llm_worker.py" --id w2 --endpoint "tcp://localhost:$PORT" $MOCK &
sleep 1.5

echo "提交任务..."
python3 "$HERE/submit_tasks.py" --endpoint "tcp://localhost:$PORT"
sleep 3

kill -TERM $HUB 2>/dev/null || true
sleep 0.5
echo "=== Hub metrics ==="
grep METRICS /tmp/llm_hub.out || echo "(no metrics)"
