# MCP 协议参考

**版本**: v0.10.0 "超我"  
**协议**: JSON over stdin/stdout  
**模式**: `python pangu_v0.10.0.py --mcp`

---

## 概述

MCP (Model Context Protocol) 桥接允许外部智能体或进程通过标准输入输出调用盘古的推理能力。安全层包含调用者身份校验、骨骼守护过滤和三级权限控制。

盘古以 JSON 行协议运行：每行一个 JSON 请求，每行一个 JSON 响应。

---

## 认证与安全

### Token 认证

每个 MCP 请求必须携带有效的调用者身份。调用者通过交互式命令注册：

| 交互命令 | 作用 |
|----------|------|
| `mcp_add <名称> <权限级别>` | 注册调用者并生成令牌 |
| `mcp_remove <名称>` | 吊销调用者令牌 |
| `mcp_list` | 列出所有已注册调用者及权限 |

**权限级别**:

| 级别 | 值 | 允许操作 |
|------|-----|----------|
| readonly | `readonly` | query, health, memory, search |
| learn | `learn` | readonly + learn |
| admin | `admin` | learn + reason, dream, 调用者管理 |

### 调用者白名单

默认信任调用者（通过 `trusted_callers` 硬编码）：
- `SanLife`
- `Pangu`
- `盘古`
- `localhost`
- `self`

未在白名单中的调用者将被拒绝。

### 骨骼守护过滤

所有请求参数中的文本会经过 `BoneGuard.check()` 检查：
- 匹配违骨模式（放弃身份、主权转移等）→ Level 2 拦截
- 拦截操作记入对话历史

### 请求身份方式

通过请求 JSON 顶层字段或 params 中的 `identity` 字段指定：

```json
// 方式一：顶层字段
{"method": "query", "params": {...}, "caller_id": "SanLife"}

// 方式二：params 字段
{"method": "query", "params": {"goal": "...", "identity": "SanLife"}}
```

---

## 方法参考

### 1. query — 单个推理查询

使用指定推理方法对目标进行单一推理，返回最优绑定。

**请求**:
```json
{
  "method": "query",
  "params": {
    "goal": "grandparent(a, _Who)",
    "method": "cot"
  },
  "caller_id": "SanLife"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `goal` | string | 是 | 推理目标谓词（如 `grandparent(a, _Who)`） |
| `method` | string | 否 | 推理方法名，默认 `cot`。可选值见下表 |

**支持的 method 值**:
`cot`, `tot`, `react`, `mcts`, `socratic`, `decomp`, `refine`, `recursive`, `analogy`, `abductive`, `inductive`, `dialectic`, `counter`, `stepback`, `contradict`, `ensemble`

**成功响应**:
```json
{
  "result": "{_Who: c}",
  "thinking": "[CoT] Goal: grandparent(a, _Who)\n  Step 1: parent(a, _Y)\n  -> {_Y: b}\n  Step 2: parent(b, _Z)\n  -> {_Z: c}",
  "success": true
}
```

**失败响应**:
```json
{
  "error": "No solution found",
  "success": false
}
```

---

### 2. learn — 学习规则

向知识库添加一条新规则。

**请求**:
```json
{
  "method": "learn",
  "params": {
    "rule": "parent(张三, 张父)"
  },
  "caller_id": "SanLife"
}
```

**复杂规则示例**:
```json
{
  "method": "learn",
  "params": {
    "rule": "grandparent(_X, _Z) :- parent(_X, _Y), parent(_Y, _Z)"
  },
  "caller_id": "SanLife"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rule` | string | 是 | 规则字符串。事实直接写谓词，规则用 `:-` 分隔头和体 |

**成功响应**:
```json
{
  "success": true,
  "message": "Learned: parent(张三, 张父)"
}
```

**错误响应**（一致性检查失败）:
```json
{
  "error": "Undefined predicates: ['father']"
}
```

---

### 3. reason — 多方法推理

使用多种推理方法分别对同一目标进行推理，返回结果对比。

**请求**:
```json
{
  "method": "reason",
  "params": {
    "goal": "ancestor(a, _X)"
  },
  "caller_id": "SanLife"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `goal` | string | 是 | 推理目标谓词 |

**响应**:
```json
{
  "cot": {
    "result": "{_X: c}",
    "thinking": "[CoT] Goal: ancestor(a, _X)\n  Step 1: parent(a, _Y)\n  -> {_Y: b}"
  },
  "tot": {
    "result": "{_X: c}",
    "thinking": "[ToT] Goal: ancestor(a, _X)\n  Branch 1: ancestor(a, _X)"
  },
  "decomp": {
    "result": "{_X: c}",
    "thinking": "[Decomp] Goal: ancestor(a, _X)\n  Sub 0: parent(a, _Y)"
  }
}
```

注：响应包含最多 5 种推理方法的结果（固定为 CoT, ToT, Decomp, StepBack, Self-Refine）。

---

### 4. health — 知识库健康报告

运行一致性证明器，返回知识库状态统计。

**请求**:
```json
{
  "method": "health",
  "params": {},
  "caller_id": "SanLife"
}
```

**响应**:
```json
{
  "rules": 4,
  "facts": 12,
  "orphans": [],
  "cycles": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `rules` | int | 规则总数 |
| `facts` | int | 事实总数 |
| `orphans` | string[] | 孤儿规则字符串列表 |
| `cycles` | list | 循环依赖路径列表 |

---

### 5. memory — 记忆检索

从 4D 持久记忆中召回相关条目。

**请求**:
```json
{
  "method": "memory",
  "params": {
    "query": "parent"
  },
  "caller_id": "SanLife"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 否 | 搜索关键词。不传则返回最近 10 条记忆 |

**响应**:
```json
{
  "memories": [
    {
      "id": "a1b2c3d4",
      "type": "user_fact",
      "content": "parent(张三, 张父)",
      "timestamp": 1718200000.0
    }
  ]
}
```

---

### 6. search — 知识图谱搜索

在知识图谱中进行混合搜索（精确 + 语义匹配）。

**请求**:
```json
{
  "method": "search",
  "params": {
    "query": "pangu"
  },
  "caller_id": "SanLife"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |

**响应**:
```json
{
  "results": [
    {
      "type": "entity",
      "name": "pangu",
      "data": {
        "type": "concept",
        "props": {},
        "created": 1718200000.0
      }
    },
    {
      "type": "relation",
      "subject": "pangu",
      "predicate": "implements",
      "object": "cognitive_engine"
    }
  ]
}
```

---

### 7. dream — 触发梦境

立即触发一次梦境反思（三级回顾/关联/重构）。

**请求**:
```json
{
  "method": "dream",
  "params": {},
  "caller_id": "SanLife"
}
```

**响应**:
```json
{
  "dream": "[Dream] Starting dream cycle...\n  Replay: parent relation query\n  Issues: 0 orphans, 0 cycles\n  Candidate rule: parent(_X, _Y) :- fact(parent(a, b))"
}
```

---

## 错误码

所有错误响应使用统一格式：

```json
{
  "error": "<错误信息>",
  "success": false
}
```

| 错误信息 | 说明 | 可能原因 |
|----------|------|----------|
| `Unknown method: <name>` | 方法名不存在 | 拼写错误 |
| `Untrusted caller: <name>` | 调用者未在白名单 | 未注册或身份不匹配 |
| `Sovereignty boundary violated by caller: <name>` | 触犯骨骼守护 | 请求参数含违骨文本 |
| `No solution found` | 推理无结果 | 知识库不完整或目标不可达 |
| `Arity mismatch: ...` | 元数不一致 | 学习规则时参数数冲突 |
| `Undefined predicates: ...` | 未定义谓词 | 规则体引用不存在的谓词 |
| `Orphans/Cycles detected...` | 孤儿/环 | 规则添加触发了结构问题 |
| `max recursion depth` | 递归过深 | 合一或回溯超过 100 层 |

---

## 安全最佳实践

### 部署建议

1. **最小权限原则**
   - 只读客户端授予 `readonly` 权限
   - 仅受信任的管理者使用 `admin`
   - 定期审查 `mcp_list` 输出

2. **调用者隔离**
   - 不同外部智能体使用不同的调用者名称
   - 定期轮换令牌（重新注册）

3. **输入过滤**
   - MCPBridge 的骨骼守护会过滤所有文本参数
   - 补充的外部过滤：不要在请求中传递用户原始输入中的身份覆盖命令

4. **日志审计**
   - 所有 MCP 调用记录在 `CONVERSATION.jsonl` 中
   - 被拦截的操作标记为 `mcp_blocked`
   - 定期审查日志检测异常模式

5. **网络隔离**
   - MCP 模式通过本地 stdin/stdout 通信
   - 如需远程访问，建议通过 TLS 代理包装，且代理层需额外认证

### 已知限制

- `trusted_callers` 硬编码在类定义中，运行时通过 `mcp_add` 添加的调用者仅在当前会话有效（不会持久化到白名单）
- Token 生成和吊销方法在 v0.10.0 中为命令行辅助接口，不暴露为 MCP 方法
- `reason` 方法固定执行前 5 种推理方法，不支持参数指定

---

## 完整调用示例

启动 MCP 模式：

```bash
python pangu_v0.10.0.py --mcp
```

逐行发送请求：

```json
{"method": "query", "params": {"goal": "grandparent(a, _Who)"}, "caller_id": "SanLife"}
{"method": "learn", "params": {"rule": "father(张三, 张父)."}, "caller_id": "SanLife"}
{"method": "health", "params": {}, "caller_id": "SanLife"}
{"method": "memory", "params": {"query": "father"}, "caller_id": "SanLife"}
{"method": "search", "params": {"query": "pangu"}, "caller_id": "SanLife"}
{"method": "dream", "params": {}, "caller_id": "SanLife"}
```
