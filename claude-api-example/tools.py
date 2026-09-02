#!/usr/bin/env python3
"""工具调用（function calling）：Claude 决定调哪个工具，你执行后把结果喂回去。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...
    python tools.py "北京天气怎么样，顺便算一下 (23+19)/2"

演示手写 agentic 循环（不依赖 beta），最清晰易懂。
"""
import ast
import operator
import os
import sys

import anthropic

MODEL = "claude-opus-4-8"

# 1) 定义工具：名字 + 描述 + 输入 JSON Schema。描述写清楚"什么时候调"。
TOOLS = [
    {
        "name": "get_weather",
        "description": "查询某个城市的当前天气。用户问到天气/气温时调用。",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名，如 北京"}},
            "required": ["city"],
        },
    },
    {
        "name": "calculate",
        "description": "计算一个数学表达式，如 (23+19)/2。用户要算数时调用。",
        "input_schema": {
            "type": "object",
            "properties": {"expr": {"type": "string", "description": "数学表达式"}},
            "required": ["expr"],
        },
    },
]

# 安全的四则运算求值（不用 eval，避免注入）
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg, ast.Pow: operator.pow}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("不支持的表达式")


def execute_tool(name: str, inp: dict) -> str:
    """你的工具实现：真实项目里这里查数据库/调 API，这里用假数据演示。"""
    if name == "get_weather":
        return f"{inp['city']} 晴，23°C，微风"
    if name == "calculate":
        try:
            return str(_safe_eval(ast.parse(inp["expr"], mode="eval").body))
        except Exception as e:  # 工具出错要把错误返回，让模型重试/调整
            return f"计算失败: {e}"
    return f"未知工具: {name}"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("错误：未设置 ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()

    prompt = sys.argv[1] if len(sys.argv) > 1 else "北京天气怎么样，顺便算一下 (23+19)/2"
    messages = [{"role": "user", "content": prompt}]

    # 2) agentic 循环：反复调用，直到模型不再要工具（stop_reason == end_turn）
    while True:
        resp = client.messages.create(
            model=MODEL, max_tokens=1024, tools=TOOLS, messages=messages,
        )
        if resp.stop_reason != "tool_use":
            break

        # 把 assistant 这一轮（含 tool_use 块）原样加进历史
        messages.append({"role": "assistant", "content": resp.content})

        # 执行所有被请求的工具，结果一次性作为一条 user 消息回传
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                print(f"[工具] {block.name}({block.input}) -> {result}", file=sys.stderr)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,   # 必须匹配 tool_use 的 id
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    # 3) 打印最终回答
    for block in resp.content:
        if block.type == "text":
            print(block.text)


if __name__ == "__main__":
    try:
        main()
    except anthropic.AuthenticationError:
        sys.exit("认证失败：API key 无效。")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 错误 {e.status_code}: {e.message}")
