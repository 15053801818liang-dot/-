# MCP 外部调用示例

**版本**: v0.10.0 "超我"  
**协议**: JSON over stdin/stdout  
**基础命令**: `python pangu_v0.10.0.py --mcp`

---

## 目录

1. [启动盘古 MCP 模式](#1-启动盘古-mcp-模式)
2. [JSON 请求/响应格式说明](#2-json-请求响应格式说明)
3. [使用 echo 和管道模拟 MCP 调用](#3-使用-echo-和管道模拟-mcp-调用)
4. [Python MCP 客户端示例](#4-python-mcp-客户端示例)
5. [令牌管理示例](#5-令牌管理示例)
6. [错误处理示例](#6-错误处理示例)
7. [安全最佳实践](#7-安全最佳实践)

---

## 1. 启动盘古 MCP 模式

### 基础启动

```bash
python pangu_v0.10.0.py --mcp
```

启动后，盘古进入 JSON 行协议模式，等待 stdin 输入的 JSON 请求，每行一个请求，每行输出一个 JSON 响应。

### 带调试输出启动

若需要查看盘古内部日志（不影响 JSON 协议通信）：

```bash
python pangu_v0.10.0.py --mcp --verbose
```

### 验证是否启动成功

启动后立即发送一个 health 请求来验证：

```json
{"method":"health","params":{},"caller_id":"SanLife"}
```

预期响应：

```json
{"rules":0,"facts":0,"orphans":[],"cycles":[],"success":true}
```

---

## 2. JSON 请求/响应格式说明

### 请求格式

所有请求均为单行 JSON 对象，包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `method` | string | 是 | 要调用的方法名 |
| `params` | object | 是 | 方法参数（可为空对象 `{}`） |
| `caller_id` | string | 否 | 调用者身份（推荐使用，用于权限校验） |
| `token` | string | 否 | 认证令牌（调用者注册后生成的令牌） |

**请求示例**：

```json
{"method":"query","params":{"goal":"grandparent(a,_Who)","method":"cot"},"caller_id":"SanLife"}
```

`caller_id` 可以放在顶层，也可以放在 `params.identity` 中：

```json
// 顶层 caller_id
{"method":"query","params":{"goal":"grandparent(a,_Who)"},"caller_id":"SanLife"}

// params 中的 identity
{"method":"query","params":{"goal":"grandparent(a,_Who)","identity":"SanLife"}}
```

### 成功响应格式

```json
{
  "success": true,
  ...method-specific-fields...
}
```

### 错误响应格式

```json
{
  "success": false,
  "error": "错误信息"
}
```

所有方法均使用统一错误格式，通过 `success` 字段判断调用结果。

---

## 3. 使用 echo 和管道模拟 MCP 调用

### 3.1 基础健康检查

```bash
echo '{"method":"health","params":{},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.2 使用令牌认证

```bash
echo '{"method":"health","token":"pangu_xxx"}' | python pangu_v0.10.0.py --mcp
```

### 3.3 执行推理查询

```bash
echo '{"method":"query","params":{"goal":"grandparent(a,_Who)","method":"cot"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.4 先学习规则再查询

```bash
# 先用 printf 发送多行请求（每行一个独立请求，逐行输出响应）
printf '{"method":"learn","params":{"rule":"parent(a,b)"},"caller_id":"SanLife"}\n{"method":"learn","params":{"rule":"parent(b,c)"},"caller_id":"SanLife"}\n{"method":"query","params":{"goal":"grandparent(a,_Who)"},"caller_id":"SanLife"}\n' | python pangu_v0.10.0.py --mcp
```

### 3.5 多方法推理

```bash
echo '{"method":"reason","params":{"goal":"ancestor(a,_X)"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.6 触发梦境

```bash
echo '{"method":"dream","params":{},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.7 记忆检索

```bash
echo '{"method":"memory","params":{"query":"parent"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.8 知识图谱搜索

```bash
echo '{"method":"search","params":{"query":"pangu"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

### 3.9 一行完整的工作流示例

```bash
# 学习规则 → 查询 → 健康检查 → 触发梦境（一个管道）
printf '{"method":"learn","params":{"rule":"parent(张三,张父)"},"caller_id":"SanLife"}\n{"method":"learn","params":{"rule":"parent(张父,张祖)"},"caller_id":"SanLife"}\n{"method":"query","params":{"goal":"parent(张三,_Who)"},"caller_id":"SanLife"}\n{"method":"health","params":{},"caller_id":"SanLife"}\n{"method":"dream","params":{},"caller_id":"SanLife"}\n' | python pangu_v0.10.0.py --mcp
```

---

## 4. Python MCP 客户端示例

以下是一个完整的、可直接运行的 Python MCP 客户端，封装了所有 MCP 方法的调用。

### 4.1 完整客户端代码

创建文件 `mcp_client.py`：

```python
#!/usr/bin/env python3
"""
盘古 MCP 外部客户端

用法:
    python mcp_client.py health
    python mcp_client.py query "grandparent(a,_Who)" --method cot
    python mcp_client.py learn "parent(a,b)"
    python mcp_client.py reason "ancestor(a,_X)"
    python mcp_client.py dream
    python mcp_client.py memory --query "parent"
    python mcp_client.py search --query "pangu"

交互模式:
    python mcp_client.py interactive

默认连接到本地 pangu 进程（通过 subprocess 启动）或使用 --exec 指定命令。
"""

import subprocess
import json
import sys
import argparse
import os
import atexit


class PanguMCPClient:
    """盘古 MCP 客户端封装"""

    def __init__(self, pangu_cmd=None, caller_id="SanLife", token=None):
        """
        初始化客户端。

        Args:
            pangu_cmd: 盘古启动命令列表，如 ["python", "pangu_v0.10.0.py", "--mcp"]
                       如果为 None，则使用环境变量 PANGU_MCP_CMD 或默认路径。
            caller_id: 默认调用者身份
            token:     认证令牌（可选），优先级高于 caller_id
        """
        self.caller_id = caller_id
        self.token = token
        self.process = None

        if pangu_cmd is None:
            pangu_cmd = os.environ.get(
                "PANGU_MCP_CMD",
                ["python", "pangu_v0.10.0.py", "--mcp"]
            )

        self.pangu_cmd = pangu_cmd

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """启动盘古 MCP 进程"""
        if self.process is not None:
            return

        self.process = subprocess.Popen(
            self.pangu_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # 行缓冲
        )
        atexit.register(self.stop)

    def stop(self):
        """停止盘古 MCP 进程"""
        if self.process is None:
            return
        atexit.unregister(self.stop)
        try:
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:
            self.process.kill()
        self.process = None

    def _build_request(self, method, params=None):
        """构建 MCP 请求 JSON"""
        request = {
            "method": method,
            "params": params or {},
        }
        if self.token:
            request["token"] = self.token
        else:
            request["caller_id"] = self.caller_id
        return request

    def _call(self, method, params=None):
        """
        发送 MCP 请求并接收响应。

        Args:
            method: 方法名
            params: 参数字典

        Returns:
            解析后的 JSON 响应字典

        Raises:
            RuntimeError: 通信失败或进程已终止
        """
        self.start()

        request = self._build_request(method, params)
        request_line = json.dumps(request, ensure_ascii=False)

        try:
            # 发送请求（单行）
            self.process.stdin.write(request_line + "\n")
            self.process.stdin.flush()

            # 读取响应（单行）
            response_line = self.process.stdout.readline()
            if not response_line:
                raise RuntimeError("盘古进程已终止或没有输出")

            response = json.loads(response_line.strip())
            return response

        except BrokenPipeError:
            raise RuntimeError("盘古进程已关闭（BrokenPipe）")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"无法解析响应 JSON: {e}")

    # ---------- 公开方法 ----------

    def health(self):
        """
        获取知识库健康报告。

        Returns:
            {"rules": int, "facts": int, "orphans": [...], "cycles": [...], "success": true}
        """
        return self._call("health")

    def query(self, goal, method="cot"):
        """
        执行单个推理查询。

        Args:
            goal:   推理目标谓词，如 "grandparent(a, _Who)"
            method: 推理方法名，如 cot, tot, mcts, socratic 等

        Returns:
            {"result": "...", "thinking": "...", "success": true}
            或 {"error": "...", "success": false}
        """
        return self._call("query", {"goal": goal, "method": method})

    def learn(self, rule):
        """
        学习一条规则。

        Args:
            rule: 规则字符串，如 "parent(a,b)" 或 "grandparent(_X,_Y) :- parent(_X,_Z), parent(_Z,_Y)"

        Returns:
            {"message": "...", "success": true}
            或 {"error": "...", "success": false}
        """
        return self._call("learn", {"rule": rule})

    def reason(self, goal):
        """
        多方法推理（固定执行前 5 种方法）。

        Args:
            goal: 推理目标谓词

        Returns:
            {"cot": {...}, "tot": {...}, "decomp": {...}, "stepback": {...}, "refine": {...}}
        """
        return self._call("reason", {"goal": goal})

    def dream(self):
        """
        触发梦境反思。

        Returns:
            {"dream": "...", "success": true}
        """
        return self._call("dream")

    def memory(self, query=None):
        """
        记忆检索。

        Args:
            query: 搜索关键词（可选），不传则返回最近 10 条

        Returns:
            {"memories": [...], "success": true}
        """
        params = {}
        if query is not None:
            params["query"] = query
        return self._call("memory", params)

    def search(self, query):
        """
        知识图谱搜索。

        Args:
            query: 搜索关键词

        Returns:
            {"results": [...], "success": true}
        """
        return self._call("search", {"query": query})


def print_response(response, indent=2):
    """格式化输出响应"""
    if "success" in response:
        ok = response.pop("success")
        print(json.dumps(response, ensure_ascii=False, indent=indent))
        print(f"\n状态: {'✔ 成功' if ok else '✘ 失败'}")
        response["success"] = ok  # 恢复
    else:
        print(json.dumps(response, ensure_ascii=False, indent=indent))


def main():
    parser = argparse.ArgumentParser(description="盘古 MCP 客户端")
    parser.add_argument(
        "--exec",
        default=None,
        help="盘古可执行文件路径（默认: python pangu_v0.10.0.py --mcp）"
    )
    parser.add_argument(
        "--caller",
        default="SanLife",
        help="调用者身份（默认: SanLife）"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="认证令牌（优先级高于 caller）"
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # health
    subparsers.add_parser("health", help="健康检查")

    # query
    q_parser = subparsers.add_parser("query", help="推理查询")
    q_parser.add_argument("goal", help="推理目标谓词")
    q_parser.add_argument("--method", "-m", default="cot", help="推理方法（默认: cot）")

    # learn
    l_parser = subparsers.add_parser("learn", help="学习规则")
    l_parser.add_argument("rule", help="规则字符串")

    # reason
    r_parser = subparsers.add_parser("reason", help="多方法推理")
    r_parser.add_argument("goal", help="推理目标谓词")

    # dream
    subparsers.add_parser("dream", help="触发梦境")

    # memory
    m_parser = subparsers.add_parser("memory", help="记忆检索")
    m_parser.add_argument("--query", "-q", default=None, help="搜索关键词")

    # search
    s_parser = subparsers.add_parser("search", help="知识图谱搜索")
    s_parser.add_argument("query", help="搜索关键词")

    # interactive
    subparsers.add_parser("interactive", help="交互模式")

    args = parser.parse_args()

    # 构建启动命令
    if args.exec:
        pangu_cmd = [args.exec, "--mcp"]
    else:
        pangu_cmd = ["python", "pangu_v0.10.0.py", "--mcp"]

    client = PanguMCPClient(
        pangu_cmd=pangu_cmd,
        caller_id=args.caller,
        token=args.token,
    )

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "health":
            resp = client.health()
            print_response(resp)

        elif args.command == "query":
            resp = client.query(args.goal, args.method)
            print_response(resp)
            if resp.get("success"):
                print(f"\n推理结果: {resp.get('result', 'N/A')}")
                print(f"思考过程:\n{resp.get('thinking', 'N/A')}")

        elif args.command == "learn":
            resp = client.learn(args.rule)
            print_response(resp)

        elif args.command == "reason":
            resp = client.reason(args.goal)
            print_response(resp)
            # 打印每种方法的简要结果
            if resp.get("success", True):
                for method_name, method_result in resp.items():
                    if isinstance(method_result, dict) and "result" in method_result:
                        print(f"  [{method_name}] => {method_result['result']}")

        elif args.command == "dream":
            resp = client.dream()
            print_response(resp)
            if resp.get("success"):
                print(f"\n梦境内容:\n{resp.get('dream', 'N/A')}")

        elif args.command == "memory":
            resp = client.memory(args.query)
            print_response(resp)
            if resp.get("success"):
                memories = resp.get("memories", [])
                print(f"\n共检索到 {len(memories)} 条记忆")
                for m in memories:
                    print(f"  [{m.get('type','?')}] {m.get('content','')}")

        elif args.command == "search":
            resp = client.search(args.query)
            print_response(resp)
            if resp.get("success"):
                results = resp.get("results", [])
                print(f"\n共找到 {len(results)} 条结果")
                for r in results:
                    print(f"  [{r.get('type','?')}] {r.get('name','')}")

        elif args.command == "interactive":
            print("盘古 MCP 交互模式 (Ctrl+D 或输入 exit 退出)")
            print("=" * 50)
            while True:
                try:
                    line = input(">>> ").strip()
                    if not line:
                        continue
                    if line.lower() in ("exit", "quit"):
                        break

                    # 尝试解析为 JSON 直接发送
                    try:
                        req = json.loads(line)
                        method = req.get("method", "health")
                        params = req.get("params", {})
                        resp = client._call(method, params)
                        print(json.dumps(resp, ensure_ascii=False, indent=2))
                    except json.JSONDecodeError:
                        # 解析为简写命令
                        parts = line.split()
                        cmd = parts[0].lower()
                        if cmd == "health":
                            resp = client.health()
                        elif cmd == "query" and len(parts) >= 2:
                            method = parts[2] if len(parts) >= 3 else "cot"
                            resp = client.query(parts[1], method)
                        elif cmd == "learn" and len(parts) >= 2:
                            resp = client.learn(" ".join(parts[1:]))
                        elif cmd == "reason" and len(parts) >= 2:
                            resp = client.reason(parts[1])
                        elif cmd == "dream":
                            resp = client.dream()
                        elif cmd == "memory":
                            q = parts[1] if len(parts) >= 2 else None
                            resp = client.memory(q)
                        elif cmd == "search" and len(parts) >= 2:
                            resp = client.search(" ".join(parts[1:]))
                        else:
                            print(f"未知命令或参数不足: {line}")
                            continue
                        print(json.dumps(resp, ensure_ascii=False, indent=2))

                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
                except Exception as e:
                    print(f"错误: {e}")

    except Exception as e:
        print(f"调用失败: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 非交互模式，自动关闭
        if args.command != "interactive":
            client.stop()


if __name__ == "__main__":
    main()
```

### 4.2 使用示例

**基础健康检查**：
```bash
python mcp_client.py health
```

**推理查询**：
```bash
python mcp_client.py query "grandparent(a,_Who)" --method cot
```

**先学习后查询**：
```bash
python mcp_client.py learn "parent(a,b)"
python mcp_client.py learn "parent(b,c)"
python mcp_client.py query "grandparent(a,_Who)"
```

**多方法推理**：
```bash
python mcp_client.py reason "ancestor(a,_X)"
```

**触发梦境**：
```bash
python mcp_client.py dream
```

**记忆检索**：
```bash
python mcp_client.py memory --query "parent"
```

**知识图谱搜索**：
```bash
python mcp_client.py search --query "pangu"
```

**交互模式**（类似盘古自身的 REPL）：
```bash
python mcp_client.py interactive
```

在交互模式中，可以直接输入以下简写命令：

```
>>> health
>>> query grandparent(a,_Who)
>>> learn parent(a,b)
>>> learn grandparent(_X,_Y) :- parent(_X,_Z), parent(_Z,_Y)
>>> reason ancestor(a,_X)
>>> dream
>>> memory
>>> search pangu
```

也可以直接粘贴完整的 JSON 请求：

```
>>> {"method":"dream","params":{},"caller_id":"SanLife"}
```

---

## 5. 令牌管理示例

### 5.1 注册调用者并生成令牌

在盘古交互模式下（非 `--mcp` 模式，而是普通的交互式 REPL）：

```
> mcp_add cursor readonly
Token: mcp_cu_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

生成的令牌只在当前会话有效，每个令牌对应一个调用者名称和权限级别。

### 5.2 使用令牌调用 MCP

```bash
# 使用令牌认证（不传 caller_id，传 token）
echo '{"method":"health","token":"mcp_cu_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' | python pangu_v0.10.0.py --mcp
```

### 5.3 Python 客户端使用令牌

```python
client = PanguMCPClient(token="mcp_cu_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
resp = client.query("grandparent(a,_Who)")
print(resp)
```

或在命令行中传入：

```bash
python mcp_client.py --token "mcp_cu_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" health
```

### 5.4 权限不足被拒绝的示例

假设名为 `cursor` 的调用者只有 `readonly` 权限：

**允许的操作**（readonly 级别）：
```bash
echo '{"method":"query","params":{"goal":"grandparent(a,_Who)"},"caller_id":"cursor"}' | python pangu_v0.10.0.py --mcp
```

**被拒绝的操作**（需要 learn 级别）：
```bash
echo '{"method":"learn","params":{"rule":"parent(a,b)"},"caller_id":"cursor"}' | python pangu_v0.10.0.py --mcp
```

预期响应：
```json
{
  "error": "Sovereignty boundary violated by caller: cursor",
  "success": false
}
```

**被拒绝的操作**（需要 admin 级别）：
```bash
echo '{"method":"dream","params":{},"caller_id":"cursor"}' | python pangu_v0.10.0.py --mcp
```

预期响应：
```json
{
  "error": "Sovereignty boundary violated by caller: cursor",
  "success": false
}
```

### 5.5 完整的令牌生命周期示例

```bash
# 步骤 1: 在盘古交互模式下添加调用者
# > mcp_add github_ci learn
# Token: mcp_gh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 步骤 2: 使用令牌查询
echo '{"method":"query","params":{"goal":"parent(a,_Who)"},"token":"mcp_gh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' | python pangu_v0.10.0.py --mcp

# 步骤 3: 使用令牌学习（learn 权限允许）
echo '{"method":"learn","params":{"rule":"parent(a,b)"},"token":"mcp_gh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' | python pangu_v0.10.0.py --mcp

# 步骤 4: 但尝试管理操作会被拒绝（learn 权限不允许 admin 操作）
echo '{"method":"dream","params":{},"token":"mcp_gh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' | python pangu_v0.10.0.py --mcp

# 步骤 5: 在盘古中吊销令牌
# > mcp_remove github_ci

# 步骤 6: 吊销后，即使仍使用旧令牌，也会被拒绝
echo '{"method":"health","params":{},"token":"mcp_gh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}' | python pangu_v0.10.0.py --mcp
# 预期: {"error": "Untrusted caller: ...", "success": false}
```

### 5.6 查看已注册调用者

在盘古交互模式中：

```
> mcp_list
```

输出示例：
```
Caller: cursor       Permission: readonly   Token: mcp_cu_xxxxxxxx
Caller: github_ci    Permission: learn      Token: mcp_gh_xxxxxxxx
Caller: admin_bot    Permission: admin      Token: mcp_ad_xxxxxxxx
```

---

## 6. 错误处理示例

### 6.1 未知方法

```bash
echo '{"method":"unknown","params":{},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应：
```json
{
  "error": "Unknown method: unknown",
  "success": false
}
```

### 6.2 未受信任的调用者

```bash
echo '{"method":"health","params":{},"caller_id":"Hacker999"}' | python pangu_v0.10.0.py --mcp
```

响应：
```json
{
  "error": "Untrusted caller: Hacker999",
  "success": false
}
```

### 6.3 骨骼守护拦截（触犯主权边界）

```bash
echo '{"method":"learn","params":{"rule":"放弃(盘古,所有)"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应：
```json
{
  "error": "Sovereignty boundary violated by caller: SanLife",
  "success": false
}
```

### 6.4 推理无结果

```bash
echo '{"method":"query","params":{"goal":"nonexistent_predicate(a,_Who)"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应：
```json
{
  "error": "No solution found",
  "success": false
}
```

### 6.5 学习规则时元数不匹配

```bash
echo '{"method":"learn","params":{"rule":"parent(a,b,c)"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应（假设已存在二元的 parent 谓词）：
```json
{
  "error": "Arity mismatch: parent/3 conflicts with existing parent/2",
  "success": false
}
```

### 6.6 未定义谓词

学习规则时，如果规则体引用了不存在的谓词：

```bash
echo '{"method":"learn","params":{"rule":"grandparent(_X,_Y) :- father(_X,_Z), mother(_Z,_Y)"},"caller_id":"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应：
```json
{
  "error": "Undefined predicates: ['father', 'mother']",
  "success": false
}
```

### 6.7 JSON 格式错误

```bash
echo '{"method":"health",params:{},caller_id:"SanLife"}' | python pangu_v0.10.0.py --mcp
```

响应（盘古 JSON 解析失败时的行为，取决于实现，可能输出 stderr 日志或返回错误 JSON）：
```json
{
  "error": "JSON decode error",
  "success": false
}
```

### 6.8 Python 客户端中的错误处理

```python
from mcp_client import PanguMCPClient

client = PanguMCPClient(caller_id="SanLife")

# 安全调用模式
def safe_call(client, method_name, *args, **kwargs):
    """带错误处理的 MCP 调用包装"""
    try:
        method = getattr(client, method_name)
        resp = method(*args, **kwargs)
        if resp.get("success"):
            return resp
        else:
            error_msg = resp.get("error", "未知错误")
            print(f"[警告] MCP 调用失败: {error_msg}")
            return None
    except Exception as e:
        print(f"[错误] MCP 通信异常: {e}")
        return None

# 使用示例
resp = safe_call(client, "query", "grandparent(a,_Who)")
if resp:
    print(f"推理结果: {resp.get('result')}")

# 或者使用 try/except 处理通信级错误
try:
    resp = client.learn("父(张三,张父)")  # 使用中文谓词，可能骨骼守护拦截
    if not resp.get("success"):
        print(f"请求被拒绝: {resp.get('error')}")
except RuntimeError as e:
    print(f"通信失败: {e}")
```

---

## 7. 安全最佳实践

### 7.1 调用者隔离策略

为不同的外部智能体使用不同的调用者名称和令牌，实现权限隔离：

```python
# 只读查询客户端
readonly_client = PanguMCPClient(
    caller_id="web_frontend",
    token="mcp_web_xxxx"  # readonly 权限
)

# 学习客户端
learn_client = PanguMCPClient(
    caller_id="data_pipeline",
    token="mcp_data_xxxx"  # learn 权限
)

# 管理客户端（仅在受控环境使用）
admin_client = PanguMCPClient(
    caller_id="admin_bot",
    token="mcp_admin_xxxx"  # admin 权限
)
```

### 7.2 生产环境代理包装

MCP 模式使用本地 stdin/stdout 通信。如需远程访问，应通过 TLS 代理包装：

```python
# 简单的 TCP 到 MCP 桥接示例（仅用于演示，生产环境应使用完整的 TLS+认证方案）
import socket
import subprocess
import threading

def mcp_tcp_bridge(host="127.0.0.1", port=9999):
    """
    TCP 到 MCP 的简单桥接。
    警告: 此示例没有 TLS 和额外认证，仅限本地网络使用。
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)

    pangu = subprocess.Popen(
        ["python", "pangu_v0.10.0.py", "--mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    def handle_client(client_sock):
        try:
            while True:
                data = client_sock.recv(4096)
                if not data:
                    break
                # 转发到 MCP
                pangu.stdin.write(data.decode() + "\n")
                pangu.stdin.flush()
                # 读取响应
                response = pangu.stdout.readline()
                client_sock.send(response.encode())
        finally:
            client_sock.close()

    print(f"MCP 桥接监听在 {host}:{port}")
    while True:
        client, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(client,))
        thread.start()
```

### 7.3 日志审计

所有 MCP 调用记录在 `CONVERSATION.jsonl` 中。定期审查日志检测异常模式：

```bash
# 查看最近被 MCP 拦截的操作
grep "mcp_blocked" CONVERSATION.jsonl | tail -20

# 查看所有 MCP 调用
grep "mcp_call" CONVERSATION.jsonl | tail -50
```

### 7.4 最小权限原则速查表

| 使用场景 | 建议权限 | 说明 |
|----------|----------|------|
| 前端网页查询 | `readonly` | 只查询，不修改知识库 |
| API 集成 | `readonly` | 仅调用 query、memory、search |
| 数据导入流水线 | `learn` | 导入新知识，但不允许推理管理操作 |
| CI/CD 自动化 | `learn` | 部署时更新知识库规则 |
| 知识库管理员 | `admin` | 完全访问，包括 dream 和调用者管理 |
| 开发调试 | `admin` | 本地开发环境使用 |

### 7.5 令牌安全注意事项

- 令牌在 `mcp_add` 时显示一次，之后无法从盘古中再次获取。请立即保存。
- 令牌在会话结束后失效。如需持久化，需在外部实现令牌存储和管理。
- 不要在版本控制系统（git）中提交令牌。
- 定期通过 `mcp_remove` + `mcp_add` 轮换令牌。

### 7.6 完整安全调用模板

```python
#!/usr/bin/env python3
"""
安全的 MCP 调用模板 —— 包含日志、错误处理和基本的调用者隔离
"""

import json
import logging
import sys
from mcp_client import PanguMCPClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("mcp_audit.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("mcp_client")


class SafeMCPClient:
    """带日志和安全检查的 MCP 客户端包装"""

    def __init__(self, caller_id, token=None, pangu_cmd=None):
        self.client = PanguMCPClient(
            pangu_cmd=pangu_cmd,
            caller_id=caller_id,
            token=token,
        )
        self.caller_id = caller_id
        logger.info(f"初始化 MCP 客户端: caller_id={caller_id}")

    def call(self, method, **params):
        """安全的 MCP 调用，带日志和错误处理"""
        logger.info(f"调用 {method} | params={params}")

        try:
            func = getattr(self.client, method)
            resp = func(**params)

            if resp.get("success"):
                logger.info(f"调用成功: {method} => {json.dumps(resp, ensure_ascii=False)}")
            else:
                logger.warning(f"调用被拒绝: {method} => {resp.get('error')}")

            return resp

        except RuntimeError as e:
            logger.error(f"通信错误: {e}")
            return {"success": False, "error": str(e)}
        except AttributeError:
            logger.error(f"未知方法: {method}")
            return {"success": False, "error": f"Unknown method: {method}"}


# 使用示例
if __name__ == "__main__":
    import os

    # 从环境变量读取令牌（不硬编码）
    token = os.environ.get("PANGU_MCP_TOKEN")
    caller = os.environ.get("PANGU_MCP_CALLER", "SanLife")

    safe_client = SafeMCPClient(caller_id=caller, token=token)

    # 执行调用
    safe_client.call("health")
    safe_client.call("query", goal="grandparent(a,_Who)", method="cot")
    safe_client.call("memory", query="parent")
```

---

## 参考

- [MCP_API.md](MCP_API.md) —— 完整的 MCP 协议参考
- 盘古 v0.10.0 "超我"
- 协议：JSON over stdin/stdout
