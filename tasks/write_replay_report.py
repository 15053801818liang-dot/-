#!/usr/bin/env python3
"""任务：生成可审计 Markdown 回测报告。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.task_base import TaskBase, artifact_dir


class WriteReplayReport(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        load_art = artifacts.get("load_market_data", {})
        bt_art = artifacts.get("chanlun_backtest", {})
        bt_path = bt_art.get("artifact_path") or bt_art.get("payload", {}).get("artifact_path")
        if not bt_path or not Path(bt_path).exists():
            raise ValueError("missing chanlun_backtest artifact")

        with open(bt_path, encoding="utf-8") as f:
            result = json.load(f)

        metrics = result.get("metrics", {})
        audit = result.get("audit", {})
        load_summary = load_art.get("summary") or load_art.get("payload", {}).get("summary", {})
        clean_audit = load_summary.get("clean_audit", {})

        pangu_art = artifacts.get("pangu_inference", {})
        pangu_payload = pangu_art.get("payload") or {}
        pangu_text = (
            pangu_art.get("pangu_logic_interpretation")
            or pangu_payload.get("pangu_logic_interpretation")
            or "无盘古推理结果"
        )
        market_state = (
            pangu_art.get("market_state_code")
            or pangu_payload.get("market_state_code")
            or "UNKNOWN"
        )
        confidence = (
            pangu_art.get("confidence")
            or pangu_payload.get("confidence")
            or 0.0
        )
        semantic_audit = (
            pangu_art.get("semantic_audit")
            or pangu_payload.get("semantic_audit")
            or {}
        )
        structure_detail = result.get("structure_detail") or {}

        reports_dir = Path(workspace_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{dag_id}.md"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"# 缠论回测报告 — {dag_id}",
            "",
            f"- 生成时间 (UTC): {now}",
            f"- 引擎: {audit.get('engine', 'chanlun')} {audit.get('version', '')}",
            f"- 成笔口径: {audit.get('stroke_standard', 'new')} (阿娇缠论新笔)",
            "",
            "## 数据摘要",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| K 线数 | {load_summary.get('bars', audit.get('bars', 'N/A'))} |",
            f"| 数据源 | {load_summary.get('source', 'N/A')} |",
            f"| 清洗丢弃 | {clean_audit.get('dropped_invalid', 0)} 无效 / {clean_audit.get('dropped_duplicate', 0)} 重复 |",
            f"| 分析模式 | {audit.get('analyze_mode', 'N/A')} ({audit.get('analyze_seconds', '?')}s) |",
            f"| 首收盘 | {load_summary.get('first_close', 'N/A')} |",
            f"| 末收盘 | {load_summary.get('last_close', 'N/A')} |",
            "",
            "## 缠论结构",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 分型数 | {metrics.get('fractals_count', 0)} |",
            f"| 笔数 | {metrics.get('strokes_count', 0)} |",
            f"| 中枢数 | {metrics.get('pivots_count', 0)} |",
            f"| 买卖信号 | {metrics.get('signals_count', 0)} |",
            "",
            "## 缠论结构语义",
            "",
        ]
        struct_start = len(lines)

        if structure_detail.get("last_stroke"):
            ls = structure_detail["last_stroke"]
            lines.append(
                f"- 当前笔: #{ls.get('index', '?')} "
                f"({ls.get('direction', '?')}) "
                f"终点价 {ls.get('end_price', 'N/A')}"
            )
        if structure_detail.get("active_pivots"):
            ap = structure_detail["active_pivots"][-1]
            lines.append(
                f"- 活跃中枢: ZG={ap.get('zg')} ZD={ap.get('zd')} "
                f"(笔区间 {ap.get('start_index')}–{ap.get('end_index')})"
            )
        if structure_detail.get("last_divergence"):
            d = structure_detail["last_divergence"]
            lines.append(
                f"- 最近背驰: {d.get('reason')} @ bar#{d.get('bar_index')} "
                f"价 {d.get('price')}"
            )
        if structure_detail.get("trade_points"):
            tp = structure_detail["trade_points"][-1]
            lines.append(
                f"- 末次信号: `{tp.get('kind')}` — {tp.get('reason')} "
                f"@ bar#{tp.get('bar_index')}"
            )
        if len(lines) == struct_start:
            lines.append("- （无结构细节，请重新运行 chanlun_backtest）")

        lines.extend([
            "",
            "## 回测指标",
            "",
            f"| 指标 | 毛收益 (无摩擦) | 净收益 (含摩擦) |",
            f"|------|----------------|----------------|",
            f"| 总收益率 | {metrics.get('total_return_gross', 0)} | {metrics.get('total_return', 0)} |",
            f"| 夏普 | {metrics.get('sharpe_gross', 'N/A')} | {metrics.get('sharpe', 0)} |",
            f"| 最大回撤 | {metrics.get('max_drawdown_gross', 'N/A')} | {metrics.get('max_drawdown', 0)} |",
            f"| 胜率 | {metrics.get('win_rate_gross', 'N/A')} | {metrics.get('win_rate', 0)} |",
            "",
            "## 摩擦成本",
            "",
            f"| 项目 | 值 |",
            f"|------|-----|",
            f"| 手续费率 | {metrics.get('commission_rate', audit.get('commission', 0))} |",
            f"| 滑点率 | {metrics.get('slippage_rate', audit.get('slippage', 0))} |",
            f"| 累计手续费 | {metrics.get('total_commission', 0)} |",
            f"| 累计滑点成本 | {metrics.get('total_slippage_cost', 0)} |",
            f"| 摩擦拖累 | {metrics.get('friction_drag', 0)} |",
            f"| 成交笔数 | {metrics.get('total_trades', 0)} |",
            "",
            "## 盘古逻辑解读",
            "",
            pangu_text,
            "",
            f"- **市场状态码**: `{market_state}`",
            f"- **置信度**: {float(confidence):.2f}",
            "",
        ])

        if semantic_audit.get("active_pivot"):
            ap = semantic_audit["active_pivot"]
            lines.append(
                f"- **语义审计**: 第 {semantic_audit.get('stroke_index', 0) + 1} 笔，"
                f"中枢 ZG={ap.get('zg')} ZD={ap.get('zd')}，"
                f"位置 {semantic_audit.get('pivot_position', '未知')}"
            )
        if semantic_audit.get("last_signal"):
            sig = semantic_audit["last_signal"]
            lines.append(
                f"- **确认信号**: `{sig.get('kind')}` — {sig.get('reason')}"
            )

        lines.extend([
            "",
            "## 御史台审计声明",
            "",
            "- 本报告由 Go 调度器驱动 Python 任务链自动生成",
            "- 任务流: load_market_data → chanlun_backtest → pangu_inference → write_replay_report",
            "- 交易逻辑: chanlun 缠论买卖点 (非 SMA)",
            "- 结果 artifact 路径可追溯，支持复现",
            "",
            f"原始结果 JSON: `{bt_path}`",
        ])

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        out_dir = artifact_dir(workspace_dir, dag_id)
        meta_path = out_dir / "report_meta.json"
        meta = {"report_path": str(report_path), "metrics": metrics, "audit": audit}
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_path": str(meta_path),
            "report_path": str(report_path),
            "summary": metrics,
        }


if __name__ == "__main__":
    WriteReplayReport().execute()
