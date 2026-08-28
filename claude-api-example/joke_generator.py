#!/usr/bin/env python3
"""随机笑话生成器（JokeAPI）。

用法:
    python3 joke_generator.py
    python3 joke_generator.py --category programming --safe-mode
    python3 joke_generator.py --type twopart --contains dog
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://v2.jokeapi.dev/joke"
VALID_CATEGORIES = {"any", "programming", "misc", "pun", "spooky", "christmas"}
VALID_TYPES = {"any", "single", "twopart"}


def build_url(
    category: str,
    joke_type: str,
    contains: str | None,
    blacklist_flags: str | None,
    safe_mode: bool,
    lang: str,
) -> str:
    params: dict[str, Any] = {"lang": lang}
    if joke_type != "any":
        params["type"] = joke_type
    if contains:
        params["contains"] = contains
    if blacklist_flags:
        params["blacklistFlags"] = blacklist_flags
    if safe_mode:
        params["safe-mode"] = ""
    return f"{API_BASE}/{category}?{urlencode(params)}"


def fetch_joke(url: str, timeout: float) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "joke-generator/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if data.get("error"):
        message = data.get("message") or "API 返回了错误。"
        raise RuntimeError(message)
    return data


def format_joke(data: dict[str, Any]) -> str:
    if data.get("type") == "single":
        joke = data.get("joke")
        if not joke:
            raise RuntimeError("API 返回的单句笑话缺少内容。")
        return f"😂 随机笑话：\n{joke}"

    setup = data.get("setup")
    delivery = data.get("delivery")
    if not setup or not delivery:
        raise RuntimeError("API 返回的双段笑话缺少内容。")
    return f"😂 随机笑话：\nQ: {setup}\nA: {delivery}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="随机笑话生成器（JokeAPI）")
    p.add_argument("--category", default="any", type=str.lower, help="类别: any/programming/misc/pun/spooky/christmas")
    p.add_argument("--type", dest="joke_type", default="any", type=str.lower, help="类型: any/single/twopart")
    p.add_argument("--contains", help="笑话需包含的关键词")
    p.add_argument("--blacklist-flags", help="过滤标签，逗号分隔（如 nsfw,religious）")
    p.add_argument("--safe-mode", action="store_true", help="启用安全模式（自动过滤不安全内容）")
    p.add_argument("--lang", default="en", help="语言代码（默认 en）")
    p.add_argument("--timeout", default=10.0, type=float, help="请求超时秒数（默认 10）")
    args = p.parse_args()

    if args.category not in VALID_CATEGORIES:
        p.error(f"--category 非法：{args.category}")
    if args.joke_type not in VALID_TYPES:
        p.error(f"--type 非法：{args.joke_type}")
    if args.timeout <= 0:
        p.error("--timeout 必须大于 0")
    return args


def main() -> None:
    args = parse_args()
    url = build_url(
        category=args.category,
        joke_type=args.joke_type,
        contains=args.contains,
        blacklist_flags=args.blacklist_flags,
        safe_mode=args.safe_mode,
        lang=args.lang,
    )
    try:
        data = fetch_joke(url, timeout=args.timeout)
        print(format_joke(data))
    except HTTPError as e:
        sys.exit(f"请求失败：HTTP {e.code}。请稍后重试。")
    except URLError:
        sys.exit("网络错误：无法连接笑话服务，请检查网络。")
    except TimeoutError:
        sys.exit("请求超时：笑话服务响应过慢，请稍后重试。")
    except json.JSONDecodeError:
        sys.exit("响应解析失败：服务返回了无效 JSON。")
    except RuntimeError as e:
        sys.exit(f"API 错误：{e}")


if __name__ == "__main__":
    main()
