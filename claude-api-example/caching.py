#!/usr/bin/env python3
"""Prompt Caching 省钱演示：把大段固定上下文缓存，重复请求最多省 ~90%。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...
    python caching.py

原理：缓存是"前缀匹配"。把稳定的大段内容放前面并加 cache_control，
第一次请求写缓存（~1.25x 价），后续相同前缀读缓存（~0.1x 价）。
关键：前缀必须逐字节相同——别在里面放时间戳/随机 ID，否则每次都失效。
"""
import os
import sys

import anthropic

MODEL = "claude-opus-4-8"

# 一大段固定的"背景知识"。必须够长才会缓存（Opus 4.8 最小 ~4096 token），
# 且每次请求逐字节相同。这里用重复段落凑长度模拟真实大上下文（如长文档）。
_PARA = (
    "分布式调度器 NeuralHub 采用 IO 线程 + 单锁调度线程 + watchdog 的三线程模型，"
    "基于 ZeroMQ ROUTER/DEALER 收发消息，WAL 二进制日志保证崩溃恢复。"
    "空闲 worker 用 O(1) 集合索引，任务经 submit->派发->RUN_TASK->TASK_DONE 全链路。"
)
BIG_CONTEXT = "以下是需要你参考的系统文档，请基于它回答问题。\n" + (_PARA + "\n") * 200


def ask(client, question: str):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=[{
            "type": "text",
            "text": BIG_CONTEXT,
            "cache_control": {"type": "ephemeral"},   # 缓存到这一块为止
        }],
        messages=[{"role": "user", "content": question}],
    )
    u = resp.usage
    return u, "".join(b.text for b in resp.content if b.type == "text")


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("错误：未设置 ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()

    print("第 1 次请求（写缓存）...")
    u1, _ = ask(client, "NeuralHub 用什么线程模型？")
    print(f"  cache_creation={u1.cache_creation_input_tokens}  "
          f"cache_read={u1.cache_read_input_tokens}  input={u1.input_tokens}")

    print("第 2 次请求（相同前缀，读缓存）...")
    u2, ans = ask(client, "它靠什么保证崩溃恢复？")
    print(f"  cache_creation={u2.cache_creation_input_tokens}  "
          f"cache_read={u2.cache_read_input_tokens}  input={u2.input_tokens}")

    print(f"\n回答: {ans}")
    if u2.cache_read_input_tokens > 0:
        print(f"\n✅ 第 2 次命中缓存：{u2.cache_read_input_tokens} token 按 ~0.1x 计价，省钱生效。")
    else:
        print("\n⚠️ 未命中缓存：前缀可能太短，或两次请求前缀不完全一致。")


if __name__ == "__main__":
    try:
        main()
    except anthropic.AuthenticationError:
        sys.exit("认证失败：API key 无效。")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 错误 {e.status_code}: {e.message}")
