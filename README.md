# Myth Trading — 神话量化交易系统

三哥的完整量化交易体系，从缠论引擎到实盘回测到AI推理。

## 项目结构

```
myth-trading/
├── chanlun/           # 纯Python缠论引擎 (包含处理→分型→笔→段→中枢→买卖点)
├── money-system/      # 赚钱系统V3 (阿娇信号 + 波段回测)
├── pangu/             # 盘古符号推理引擎 (多版本: v0.9→v0.12)
├── scheduler/         # Python分布式调度器 (原子操作+租约)
├── zero-dag/          # Go DAG调度器 (8态矩阵+Kahn拓扑+并发)
├── memory/            # 记忆层V0 (七刀封口: inbox/recall/review/event/core/integrity/trace)
├── skill-gate/        # 技能验证门控 (结构性→注入→功能性 三关)
├── tasks/             # Python任务节点
├── scripts/           # 数据脚本
├── data/              # 示例数据
└── configs/           # 配置文件
```

## 快速开始

### 缠论分析
```bash
cd chanlun
python demo.py
```

### 赚钱系统回测
```bash
cd money-system
python run_all.py
```

### 记忆层测试
```bash
cd memory
python -m pytest ../tests/ -v
```

## 回测成绩 (BTC/ETH/SOL, 2022-2026)

| 币种 | 交易笔数 | 胜率 | 累计PnL |
|------|---------|------|---------|
| BTC | 230 | 53% | +243.6% |
| ETH | 257 | 53% | +321.8% |
| SOL | 212 | 51% | +266.7% |

TP=3.5% SL=1.0%, 纯阿娇信号, 4.5年0亏损年份

## 技术栈

- Python 3.13+ | Go 1.23+
- 缠论: 自研纯Python (不依赖czsc)
- 盘古: 符号知识库推理引擎
- 调度器: Go + Python双引擎
