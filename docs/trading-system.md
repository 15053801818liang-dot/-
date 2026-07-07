---
name: trading-system
description: 赚钱系统V3回测结果和参数优化
metadata:
  type: project
---

# 赚钱系统 V3

**位置**: `F:\量化与智能体系统\02_经典赚钱系统_V3.0\`
**GitHub**: `github.com/15053801818liang-dot/-` (main分支, money-system/)

## 数据规模
- BTC: 470,750 根 5min K线 (2022-01-01 → 2026-06-23)
- ETH: 463,263 根
- SOL: 456,063 根

## 回测结果 (TP=3.5%, SL=1.0%)
- 总交易: 699 笔
- 胜率: 52.6%
- 累计 PnL: +832.1%
- 赢均: +3.15%, 亏均: -0.98%, 盈亏比: 3.20
- 0 个亏损年份 (2022-2026)
- 保本线: 22.2%

## 架构
```
run_all.py → 滑动窗口(W=2000,S=400,WIN=240)
  ├── kxian_baohan()  # 包含处理
  ├── find_fenxing()  # 分型识别
  ├── find_bi()       # 笔构建
  ├── find_duan()     # 段分解
  ├── find_zhongshu_from_duan() # 中枢
  ├── classify_zoushi() # 走势分类
  ├── find_divergence()  # 背驰检测
  └── detect_buy_sell_points() # 买卖点
```

## 已知限制
- 只有3币种数据充足, 其余5币种不足
- 纯阿娇信号, 无盘古闸门
- 当前不支持做空

**Why:** 这是目前最完整的赚钱系统, 需要盘古审计其漏洞。
**How to apply:** 新窗口任务: 搭建爬虫→实时数据→盘古自审→找出交易漏洞。
