#!/usr/bin/env python3
"""LLM Worker：连到 C++ 分布式调度器 Hub，接任务后调用 Claude 做推理。

把调度器的 PendingTask.code 当作 LLM prompt、manifest 当作可选 system prompt。
worker 走 ZMQ DEALER，说的是 Hub 的线协议（WORKER_READY / RUN_TASK / TASK_DONE）。

用法:
    # 真实推理（需要 key）
    export ANTHROPIC_API_KEY=sk-ant-...
    python llm_worker.py --id w1 --endpoint tcp://localhost:5555

    # 协议连通性演示（不花钱、不用 key，返回假答案）
    python llm_worker.py --id w1 --mock
"""
import argparse
import json
import os
import sys

import zmq


def call_claude(system: str, prompt: str, model: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    kwargs = {}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(
        model=model, max_tokens=512,
        messages=[{"role": "user", "content": prompt}], **kwargs,
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM worker for the distributed scheduler")
    ap.add_argument("--id", default="llm-worker-1", help="worker 身份（Hub 用它路由）")
    ap.add_argument("--endpoint", default="tcp://localhost:5555")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--mock", action="store_true", help="不调 API，返回假答案（验证协议）")
    args = ap.parse_args()

    if not args.mock and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("需要 ANTHROPIC_API_KEY，或加 --mock 跑协议连通性演示。")

    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt_string(zmq.IDENTITY, args.id)   # 必须在 connect 前设置
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(args.endpoint)

    # 注册：DEALER 发 [空分隔帧, JSON]；Hub 的 ROUTER 会自动前置 identity
    sock.send_multipart([b"", json.dumps({"op": "WORKER_READY"}).encode()])
    print(f"[{args.id}] 已注册到 {args.endpoint}，等待任务...", file=sys.stderr)

    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)

    while True:
        if not dict(poller.poll(timeout=1000)):
            continue
        frames = sock.recv_multipart()
        payload = frames[-1]              # 最后一帧是 JSON（前面可能有分隔帧）
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if msg.get("op") != "RUN_TASK":
            continue

        task_id = msg.get("task_id", "")
        prompt = msg.get("code", "")       # 调度器的 code 字段 = LLM prompt
        system = msg.get("manifest", "")   # manifest 字段 = 可选 system prompt

        if args.mock:
            answer = f"[mock] 已处理 {task_id}: {prompt[:50]}"
        else:
            try:
                answer = call_claude(system, prompt, args.model)
            except Exception as e:
                # 失败 -> TASK_FAILED，Hub 会重新入队给别的 worker
                sock.send_multipart([b"", json.dumps(
                    {"op": "TASK_FAILED", "task_id": task_id, "error": str(e)}).encode()])
                print(f"[{args.id}] 任务 {task_id} 失败: {e}", file=sys.stderr)
                continue

        print(f"\n[{args.id}] ▸ Q: {prompt}\n[{args.id}] ◂ A: {answer}\n", flush=True)
        # 完成 -> TASK_DONE（带上结果；Hub 只认 task_id，result 是给下游看的）
        sock.send_multipart([b"", json.dumps(
            {"op": "TASK_DONE", "task_id": task_id, "result": answer}).encode()])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
