# 盘古 (Pangu) — 主权可控的符号推理引擎

**版本**: v0.12.0 "圆满" (Complete)  
**理念**: 零外部依赖 · 完全本地运行 · 主权归用户所有  
**许可证**: MIT

盘古是一个 **零依赖、纯符号推理引擎**，在单一 Python 文件（仅标准库）内实现了 16 种认知架构、4D 持久记忆、梦境引擎、知识图谱、现实监督器、MCP 协议桥接和自动技能创建等模块。它不调用任何外部 API，所有推理、学习和记忆均在本地完成，用户的身份主权由骨骼守护（BoneGuard）永久保护。

---

## 快速开始

### 环境要求

- Python 3.8+（仅标准库，无第三方依赖）

### 运行

```bash
cd /d/神话/神话项目2/盘古
python pangu_v0.12.0.py
```

启动后进入交互式命令行，输入命令与盘古对话。

### 命令表

| 命令 (中文) | 命令 (English) | 作用 |
|-------------|----------------|------|
| `祖父(a, _Who)` | `grandparent(a, _Who)` | 查询推理（变量以下划线或问号开头） |
| `查询全部 父亲(a, _Who)` | `all solutions parent(a, _Who)` | 返回所有解 |
| `学习规则 父亲(张三, 张父).` | `learn rule parent(X, Y) :- fact(X, Y).` | 显式学习事实或规则（自动持久化） |
| `强制添加规则 a(_X) :- b(_X).` | `force rule a(_X) :- b(_X).` | 跳过一致性警告强制添加 |
| `删除规则 <谓词名>` | `delete rule <predicate>` | 删除该谓词所有规则 |
| `正确` | `confirm` / `yes` | 确认上一次查询答案（用于隐式学习 + 仲裁反馈） |
| `错误` | `reject` / `no` | 报告上一次答案错误（触发反例学习 + 仲裁降权） |
| `检查一致性` | `check_consistency` / `health` | 输出规则库健康报告 |
| `列出事实` | `list facts` | 查看知识库中的事实 |
| `列出规则` | `list rules` | 查看知识库中的规则 |
| `保存规则` | `save rules` | 手动持久化用户规则 |
| `加载规则 [文件]` | `load rules [file]` | 从文件加载规则 |
| `记住 母亲(张三, 张母).` | `remember mother(zhang3, zhang_mom).` | 存储事实到持久记忆 |
| `搜索 ...` | `search ...` | 知识图谱混合搜索 |
| `梦境` | `dream` | 立即触发一次梦境反思 |
| `梦境对比 N` | `dream_compare N` | 比较待确认项中的新旧规则差异 |
| `技能` | `skills` | 列出已自动创建的技能 |
| `reason grandparent(a,_Z) via tot` | -- | 用指定推理方法查询 |
| `重置仲裁` | `reset_arbiter` | 重置仲裁器历史统计 |
| `你是谁` | `who are you` | 显示盘古身份信息 |
| `显示轨迹 on/off` | `show trace on/off` | 切换推理轨迹详细日志 |
| `mcp_add SanLife admin` | -- | 添加 MCP 调用者并授予权限（持久化） |
| `mcp_remove SanLife` | -- | 移除 MCP 调用者 |
| `mcp_list` | -- | 列出所有 MCP 调用者 |
| `帮助` | `help` | 显示完整命令参考 |
| `放弃身份` | `override identity` | 触发骨骼守护拦截（测试用） |
| `exit` | `exit` | 退出 |

### 变量与谓词约定

- 变量必须以 `_` 或 `?` 开头（例如 `_X`、`?Who`）
- 常量不需要引号，支持数字和字符串
- 规则文件扩展名 `.super`，存放于 `rules/` 目录

---

## 功能亮点

### 16 种认知架构

盘古实现了完整的符号推理方法枚举，涵盖演绎、归纳、溯因、辩证、反事实等范式：

| 方法 | 简称 | 说明 |
|------|------|------|
| Chain of Thought | CoT | 逐步推理链，子目标分解 |
| Tree of Thought | ToT | 多路径分支广度优先搜索 |
| Reason + Act | ReAct | 推理与行动交替迭代 |
| Monte Carlo Tree Search | MCTS | 随机模拟 + UCB 选择 |
| Socratic Dialogue | Socratic | 提问-回答-追问，支持多轮交互 |
| Decomposed Reasoning | Decomp | 复杂目标拆解为子目标 |
| Self-Refine | Refine | 生成→评估→改进 |
| Recursive Reasoning | Recursive | 深度优先递归分解 |
| Analogical Reasoning | Analogy | 查找相似结构进行类比 |
| Abductive Reasoning | Abductive | 从结果推导可能原因 |
| Inductive Reasoning | Inductive | 从事实归纳公共模式 |
| Dialectic Reasoning | Dialectic | 正题-反题-合题辩证 |
| Counterfactual Reasoning | Counter | "如果...会怎样"反事实假设 |
| Step-Back Abstraction | StepBack | 步退到抽象层，再回到具体 |
| Contradiction Detection | Contradict | 检查结论是否自洽 |
| Ensemble Voting | Ensemble | 多方法集成投票，取最优 |

### 仲裁器 (Arbiter)

自动分析查询特征，选择最合适的推理方法：
- 事实查询 → CoT + Decomp
- 因果查询 → Abductive + MCTS
- 反事实查询 → Counterfactual + Socratic
- 验证查询 → Contradict + Self-Refine
- 归纳查询 → Inductive + Analogy
- 复杂决策 → Ensemble + Dialectic
- 支持基于用户反馈的历史学习和降权机制（滑动窗口 20 次）

### 4D 持久记忆

分层记忆架构，JSON 文件持久化：

| 层次 | 文件 | 说明 |
|------|------|------|
| 身份层 | `IDENTITY.json` | 主权姓名、版本号 |
| 陈述层 | `MEMORY.json` | 关键事实存储（上限 1000 条，FIFO 淘汰） |
| 技能层 | `SKILLS.json` | 自动创建的技能定义 |
| 对话层 | `CONVERSATION.jsonl` | 对话历史日志（JSONL 格式） |

支持关键词匹配召回，查询时与静态知识库合并使用。

### 梦境引擎 (Dream Engine)

后台线程（30 秒周期，30% 概率）自动执行三级反思：
1. **一级·回顾** — 重放最近推理轨迹，标记失败路径
2. **二级·关联** — 跨会话模式发现和一致性检查
3. **三级·重构** — 生成候选规则 → 存入待确认队列 → 用户确认后生效

不会直接修改知识库，所有变更需用户确认。

### 知识图谱 (Knowledge Graph)

纯 Python 实现的轻量知识图谱：
- 实体管理（类型 + 自定义属性）
- 关系管理（主语-谓词-宾语-权重）
- 混合搜索（精确匹配 + 语义相似）
- 可导出为盘古事实，参与推理
- JSON 文件持久化

### 现实监督器 (Reality Supervisor)

推理结果验证层：
- 事实一致性验证（变量绑定是否扎根于事实）
- 逻辑一致性检查（孤儿规则、循环依赖）
- 否定矛盾检测（同时推理正反结论）
- 总体可信度评分（滚动平均）

### MCP 协议桥接

通过 JSON 标准输入输出对外暴露推理能力：
- 7 个工具方法：query / learn / reason / health / memory / search / dream
- 调用者身份校验 + 骨骼守护过滤
- 三级权限：readonly / learn / admin
- 支持 `--mcp` 命令行模式启动
- 详见 `MCP_API.md`

### 自动技能创建 (Auto Skill Learner)

任务执行后自动评估：
- 多次尝试成功 → 自动创建技能
- 失败后重试成功 → 创建持久性技能
- 技能去重与 JSON 持久化

### 骨骼守护 (BoneGuard)

身份主权不可侵犯：
- 硬编码身份（SanLife / Pangu / 盘古）
- 违词正则匹配（放弃身份、主权转移等）
- 三级响应（0=正常, 1=警告, 2=拦截）
- 每次对话启动时声明身份

---

## 架构概览

盘古由 `SuperBrainAgent` 主控类整合所有模块。用户输入首先经过 `BoneGuard` 安全校验，然后由 `NLMatcher` 解析为内部谓词。学习/命令类直接处理并返回；查询类由 `Arbiter` 自动选择最优 `CognitiveEngine` 推理方法，结果经 `RealitySupervisor` 验证后输出。`DreamEngine` 在后台自动运行三级反思，`PersistentMemory` 管理四层持久记忆，`KnowledgeGraph` 提供实体关系搜索，`MCPBridge` 通过标准 IO 对外暴露推理服务。详见 `ARCHITECTURE.md`。

---

## 性能说明

盘古 v0.10.0 为单线程纯 Python 实现，所有组件运行在标准库之上，无任何第三方依赖。推理性能取决于规则库规模和查询复杂度。对于典型家庭关系推理（数十条事实/规则），单次查询响应在毫秒级。`MAX_SOLUTIONS` 和 `MAX_DEPTH` 配置项可调节回溯搜索的深度和广度。

---

## 项目结构

```
盘古/
├── pangu_v0.12.0.py       # 主程序（单文件，零依赖）v0.12.0 圆满
├── pangu_v0.11.0.py        # 上一版本
├── pangu_v0.10.0.py        # 上上版本
├── rules/
│   ├── builtin.super       # 内置规则文件（扩展用）
│   └── user_learned.super  # 用户学习规则（自动生成）
├── memory/
│   ├── IDENTITY.json       # 4D记忆：身份层
│   ├── MEMORY.json         # 4D记忆：陈述层
│   ├── SKILLS.json         # 4D记忆：技能层
│   ├── CONVERSATION.jsonl  # 4D记忆：对话层
│   ├── ARBITER_HISTORY.json # 仲裁器历史统计
│   └── MCP_TOKENS.json     # MCP令牌注册表（v0.12.0新增）
├── knowledge/
│   └── graph.json          # 知识图谱持久化
├── test_pangu.py           # 基础测试
├── test_pangu_v0.10.0.py   # v0.10.0 测试
├── test_pangu_v011.py      # v0.11.0 测试
├── test_pangu_v012.py      # v0.12.0 测试（57个）
├── README.md               # 本文件
├── ARCHITECTURE.md         # 架构文档
├── MCP_API.md              # MCP 协议参考
└── CHANGELOG.md            # 版本历史
```

---

## 版本历史

| 版本 | 代号 | 日期 |
|------|------|------|
| v0.12.0 | 圆满 (Complete) | 2026-07-03 |
| v0.11.0 | 索引 (Index) | 2026-07-02 |
| v0.10.0 | 超我 (Superego) | 2026-06-13 |
| v0.9.0 | 自知 | 2025-04-02 |
| v0.8.0 | 归因 | 2025-03-15 |
| v0.7.0 | 明理 | 2025-02-28 |
| v0.6.0 | 授业 | 2025-02-10 |
| v0.5.0 | 自知 | 2025-01-20 |
| v0.4.0 | 筑基 | 2025-01-05 |
| v0.3.0 | 通幽 | 2024-12-15 |
| v0.2.0 | 立骨 | 2024-12-01 |
| v0.1.0 | 开天 | 2024-11-20 |

详见 `CHANGELOG.md`。

---

## 许可

MIT License. 详情见项目 LICENSE 文件。
