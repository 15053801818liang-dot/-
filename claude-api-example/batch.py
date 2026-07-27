#!/usr/bin/env python3
"""Batch API 批量处理：非实时任务打 5 折，适合大规模离线跑。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...
    python batch.py

流程: 打包一批请求 -> 提交 -> 轮询直到 ended -> 按 custom_id 取结果。
特点: 每个请求独立、结果乱序返回（必须用 custom_id 对应，别按顺序），
      所有 token 5 折，单批最多 10 万请求，通常 1 小时内完成（上限 24h）。
"""
import os
import sys
import time

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

MODEL = "claude-haiku-4-5"   # 批量分类用最便宜的模型即可

# 要批量处理的输入（真实场景可能是几万条）
TEXTS = [
    "这个产品质量太棒了，超出预期！",
    "客服态度极差，再也不会买了。",
    "还行吧，没什么特别的。",
    "物流很快，包装也用心，好评。",
    "用了三天就坏了，垃圾。",
]


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("错误：未设置 ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()

    # 1) 打包请求：每个带唯一 custom_id，用于之后对应结果
    requests = [
        Request(
            custom_id=f"text-{i}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=16,
                messages=[{
                    "role": "user",
                    "content": f"判断这句话的情感，只回一个词（正面/负面/中性）：{t}",
                }],
            ),
        )
        for i, t in enumerate(TEXTS)
    ]

    # 2) 提交
    batch = client.messages.batches.create(requests=requests)
    print(f"已提交批次 {batch.id}，共 {len(requests)} 条，状态 {batch.processing_status}")

    # 3) 轮询直到 ended（这里几条秒完；大批量可拉长间隔）
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"  处理中... 成功 {batch.request_counts.succeeded} / "
              f"处理中 {batch.request_counts.processing}")
        time.sleep(5)

    # 4) 取结果——乱序返回，用 custom_id 建映射
    results = {}
    for r in client.messages.batches.results(batch.id):
        if r.result.type == "succeeded":
            msg = r.result.message
            results[r.custom_id] = "".join(b.text for b in msg.content if b.type == "text").strip()
        else:
            results[r.custom_id] = f"[{r.result.type}]"   # errored / canceled / expired

    # 5) 按原顺序打印
    print("\n=== 结果 ===")
    for i, t in enumerate(TEXTS):
        print(f"  {results.get(f'text-{i}', '[缺失]'):<6}  {t}")

    print("\n💡 Batch API 所有 token 均按标准价 5 折计费。")


if __name__ == "__main__":
    try:
        main()
    except anthropic.AuthenticationError:
        sys.exit("认证失败：API key 无效。")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 错误 {e.status_code}: {e.message}")
