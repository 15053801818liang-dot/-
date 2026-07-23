#!/usr/bin/env python3
"""Claude API 最小示例：单轮 / 流式 / 多轮对话。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...          # 先设好 key
    python chat.py "用一句话解释分布式调度器"      # 单轮问答
    python chat.py --stream "写一个 Python 快排"    # 流式输出
    python chat.py --model claude-haiku-4-5 "你好"  # 换便宜模型
    python chat.py --chat                          # 进入多轮对话（输入 exit 退出）

模型 ID（用精确字符串，别加日期后缀）:
    claude-opus-4-8    最强，$5/$25 每百万 token
    claude-sonnet-5    均衡
    claude-haiku-4-5   最便宜，$1/$5，适合练习
"""
import argparse
import os
import sys

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"


def make_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("错误：未设置 ANTHROPIC_API_KEY 环境变量。\n"
                 "  export ANTHROPIC_API_KEY=sk-ant-...")
    # 不传 api_key，SDK 自动读环境变量 ANTHROPIC_API_KEY
    return anthropic.Anthropic()


def ask_once(client, model: str, prompt: str) -> None:
    """单轮：发一个问题，打印完整回答。"""
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    # content 是内容块列表，按 type 取 text
    for block in resp.content:
        if block.type == "text":
            print(block.text)
    print(f"\n[tokens] in={resp.usage.input_tokens} out={resp.usage.output_tokens}",
          file=sys.stderr)


def ask_stream(client, model: str, prompt: str) -> None:
    """流式：边生成边打印，避免长响应等待/超时。"""
    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
    print()


def chat_loop(client, model: str) -> None:
    """多轮：API 无状态，每轮把完整历史传回去。"""
    print(f"多轮对话（模型 {model}）。输入 exit 退出。\n")
    messages = []
    while True:
        try:
            user = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user in ("exit", "quit", ""):
            break
        messages.append({"role": "user", "content": user})
        resp = client.messages.create(model=model, max_tokens=1024, messages=messages)
        answer = "".join(b.text for b in resp.content if b.type == "text")
        print(f"Claude > {answer}\n")
        messages.append({"role": "assistant", "content": answer})


def main() -> None:
    p = argparse.ArgumentParser(description="Claude API 最小示例")
    p.add_argument("prompt", nargs="?", help="要问的内容")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"模型 ID（默认 {DEFAULT_MODEL}）")
    p.add_argument("--stream", action="store_true", help="流式输出")
    p.add_argument("--chat", action="store_true", help="进入多轮对话模式")
    args = p.parse_args()

    client = make_client()

    try:
        if args.chat:
            chat_loop(client, args.model)
        elif args.prompt:
            (ask_stream if args.stream else ask_once)(client, args.model, args.prompt)
        else:
            p.print_help()
    except anthropic.AuthenticationError:
        sys.exit("认证失败：API key 无效或已撤销。")
    except anthropic.RateLimitError as e:
        retry = e.response.headers.get("retry-after", "60")
        sys.exit(f"触发限流，请 {retry}s 后重试。")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 错误 {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        sys.exit("网络错误：检查网络连接。")


if __name__ == "__main__":
    main()
