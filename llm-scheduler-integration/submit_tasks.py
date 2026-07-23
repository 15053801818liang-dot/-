#!/usr/bin/env python3
"""提交 LLM 任务到调度器 Hub：把 prompt 塞进 SUBMIT_TASK 的 code 字段。

用法:
    python submit_tasks.py --endpoint tcp://localhost:5555
"""
import argparse
import json
import time

import zmq

# 一批要交给 LLM worker 处理的 prompt（真实场景可能是几万条）
PROMPTS = [
    "用一句话解释什么是预写日志（WAL）。",
    "把这句话翻译成英文：分布式调度器保证任务不丢失。",
    "3 的 10 次方等于多少？只回数字。",
    "给下面的评论分类（正面/负面）：这个产品太好用了。",
    "用一个比喻解释什么是消息队列。",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="tcp://localhost:5555")
    ap.add_argument("--system", default="", help="可选 system prompt（放进 manifest 字段）")
    args = ap.parse_args()

    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt_string(zmq.IDENTITY, "submitter")
    sock.setsockopt(zmq.LINGER, 1000)   # 关闭前给未发出的消息 1s 时间
    sock.connect(args.endpoint)
    time.sleep(0.3)                     # 等连接建立

    for i, prompt in enumerate(PROMPTS):
        sock.send_multipart([b"", json.dumps({
            "op": "SUBMIT_TASK",
            "task_id": f"llm-{i}",
            "manifest": args.system,   # system prompt（可空）
            "code": prompt,            # 用户 prompt
        }).encode()])

    print(f"已提交 {len(PROMPTS)} 个 LLM 任务到 {args.endpoint}")
    time.sleep(1)   # 让消息刷出去
    sock.close()
    ctx.term()


if __name__ == "__main__":
    main()
