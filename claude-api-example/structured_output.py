#!/usr/bin/env python3
"""结构化输出：让 Claude 返回符合 schema 的 JSON，直接拿到校验过的对象。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...
    python structured_output.py

需要较新 SDK（pip install -U anthropic）。支持模型: Opus 4.8 / Sonnet 5 / Haiku 4.5。
"""
import os
import sys
from typing import List

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-4-8"


class Contact(BaseModel):
    """想要抽取的结构。字段名/类型即 schema。"""
    name: str
    email: str
    plan: str
    interests: List[str]
    demo_requested: bool


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("错误：未设置 ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()

    text = ("从这段话抽取联系人信息：张伟 (zhang@corp.com) 想要 Enterprise 套餐，"
            "对 API 和 SDK 感兴趣，并希望预约一次演示。")

    # messages.parse 会用 output_format 约束响应，并自动校验成 Contact 实例
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": text}],
        output_format=Contact,
    )

    contact: Contact = resp.parsed_output  # 已是校验过的对象，不用手动 json.loads
    print(contact.model_dump_json(indent=2))
    print(f"\nplan={contact.plan}  demo={contact.demo_requested}  "
          f"interests={contact.interests}")


if __name__ == "__main__":
    try:
        main()
    except anthropic.AuthenticationError:
        sys.exit("认证失败：API key 无效。")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 错误 {e.status_code}: {e.message}")
