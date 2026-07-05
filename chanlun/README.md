# 缠论内核 chanlun

> 缠中说禅技术分析的**纯 Python、零外部依赖**实现。

从原始 K 线出发，逐级识别缠论结构，直到给出买卖点：

```
K线 → 包含处理 → 分型 → 笔 → 中枢 → MACD背驰 → 一/二/三类买卖点
```

## 快速上手

```python
from chanlun import analyze, bars_from_hl

# (high, low) 列表；也可用 bars_from_ohlc([(open, high, low, close), ...])
bars = bars_from_hl([(10, 9), (11, 10), (12, 11), ...])
result = analyze(bars)                 # 默认阿娇缠论新笔 (StrokeStandard.NEW)
result = analyze(bars, stroke_standard=StrokeStandard.OLD)  # 老笔/严笔

for tp in result.trade_points:
    print(tp.kind.value, tp.bar_index, tp.price, tp.reason)
```

`ChanResult` 字段：`bars` / `merged`（合并K线）/ `fractals`（分型）/
`strokes`（笔）/ `pivots`（中枢）/ `macd` / `trade_points`（买卖点）。

## 运行演示

```bash
python3 -m chanlun.demo
```

演示两个场景：**下降通道底背驰 → 第一类买点**、**中枢突破回调 → 第三类买点**。

## 运行测试

```bash
python3 chanlun/test_chanlun.py
# 或
python3 -m pytest chanlun/test_chanlun.py
```

## 模块结构

| 文件 | 职责 |
| --- | --- |
| `models.py` | 数据结构（Bar / MergedBar / Fractal / Stroke / Pivot / TradePoint） |
| `kline.py` | K 线包含处理（按走势方向合并） |
| `fractal.py` | 顶/底分型识别 |
| `stroke_rules.py` | 阿娇缠论成笔规则校验（新笔/老笔） |
| `stroke.py` | 笔构建（顶底交替 + 规则校验 + 假分型回退） |
| `pivot.py` | 中枢识别（连续三笔重叠 + 终点延伸判定） |
| `macd.py` | EMA / MACD / 柱面积（力度度量） |
| `signals.py` | 背驰判定与一/二/三类买卖点 |
| `analyzer.py` | 门面：串起整条流水线 |
| `sample.py` | 合成样本行情（demo 与测试共用） |
| `demo.py` | 命令行演示 |

## 算法口径与边界

- **包含处理**：向上取「高高、低取高」，向下取「低低、高取低」；方向由已合并序列最后两根判定。
- **分型（阿娇/108课）**：顶分型 = 中间 K 线高、低点均为三根中最高；底分型 = 中间 K 线高、低点均为三根中最低。
- **笔（默认新笔）**：
  1. 顶底分型不共用原始 K 线；
  2. 顶分型最高 K 与底分型最低 K 之间（不含端点）≥ 3 根原始 K 线；
  3. 合并 K 线跨度 ≥ 4 根。
- **老笔（严笔）**：`StrokeStandard.OLD`，合并 K 线跨度 ≥ 5 根。
- **中枢**：`ZG = min(头三笔高点)`，`ZD = max(头三笔低点)`，`ZG > ZD` 成立；后续笔**终点**仍在 `[ZD, ZG]` 内则延伸，脱离即为离开中枢。
- **背驰**：相邻同向笔（i 与 i-2）比较，后一笔创新高/新低但 MACD 柱面积更小。
- 这是**笔级别**的工程化近似实现，未含线段、递归级别与走势类型的完整判定；适合作为可测试、可扩展的基础内核。
