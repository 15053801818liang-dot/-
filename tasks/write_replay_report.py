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
        union_art = artifacts.get("join_union_report", {})
        pangu_art = artifacts.get("pangu_inference", {})
        bt_path = bt_art.get("artifact_path") or bt_art.get("payload", {}).get("artifact_path")
        if not bt_path or not Path(bt_path).exists():
            raise ValueError("missing chanlun_backtest artifact")

        with open(bt_path, encoding="utf-8") as f:
            result = json.load(f)

        metrics = result.get("metrics", {})
        audit = result.get("audit", {})
        load_summary = load_art.get("summary") or load_art.get("payload", {}).get("summary", {})

        union_data = {}
        union_path = union_art.get("artifact_path") or (union_art.get("payload") or {}).get("artifact_path")
        if union_path and Path(union_path).exists():
            with open(union_path, encoding="utf-8") as f:
                union_data = json.load(f)

        pangu_data = {}
        pangu_path = pangu_art.get("artifact_path") or (pangu_art.get("payload") or {}).get("artifact_path")
        if pangu_path and Path(pangu_path).exists():
            with open(pangu_path, encoding="utf-8") as f:
                pangu_data = json.load(f)
        elif pangu_art.get("payload"):
            pangu_data = pangu_art["payload"]

        reports_dir = Path(workspace_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{dag_id}.md"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"# 缠论回测报告 — {dag_id}",
            "",
            f"- 生成时间 (UTC): {now}",
            f"- 引擎: {audit.get('engine', 'chanlun')} {audit.get('version', '')}",
            f"- 成笔口径: {audit.get('stroke_standard', 'new')}",
            "",
            "## 数据摘要",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| K 线数 | {load_summary.get('bars', audit.get('bars', 'N/A'))} |",
            f"| 数据源 | {load_summary.get('source', 'N/A')} |",
            f"| 首收盘 | {load_summary.get('first_close', 'N/A')} |",
            f"| 末收盘 | {load_summary.get('last_close', 'N/A')} |",
            "",
            "## 缠论结构",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 笔数 (bi) | {metrics.get('strokes_count', 0)} |",
            f"| 线段数 (duan) | {metrics.get('duan_count', 0)} |",
            f"| 中枢数 | {metrics.get('pivots_count', 0)} |",
            f"| 买卖信号 | {metrics.get('signals_count', 0)} |",
            f"| 背驰事件 (一买/一卖) | {metrics.get('divergence_count', 0)} |",
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
        ]

        if union_data:
            cross = union_data.get("cross_domain", {})
            immune = union_data.get("immune", {})
            lines.extend([
                "## 跨域联合分析",
                "",
                f"| 指标 | 值 |",
                f"|------|-----|",
                f"| 免疫数据源 | {immune.get('source', 'N/A')} |",
                f"| 免疫 AUC (LOO) | {immune.get('auc_loo', 'N/A')} |",
                f"| 跨域一致性评分 | {cross.get('alignment_score', 'N/A')} |",
                f"| 跨域状态 | {cross.get('status', 'N/A')} |",
                f"| 综合风险指标 | {cross.get('risk_indicator', 'N/A')} |",
                "",
            ])

        if pangu_data:
            lines.extend([
                "## 盘古符号推理",
                "",
                f"| 字段 | 值 |",
                f"|------|-----|",
                f"| 市场状态码 | {pangu_data.get('market_state_code') or pangu_data.get('state_code', 'N/A')} |",
                f"| 置信度 | {pangu_data.get('confidence', 'N/A')} |",
                f"| 跨域对齐 | {pangu_data.get('cross_domain_align', False)} |",
                "",
                f"> {pangu_data.get('pangu_logic_interpretation') or pangu_data.get('interpretation', '')}",
                "",
            ])

        lines.extend([
            "## 御史台审计声明",
            "",
            "- 本报告由 Go 调度器驱动 Python 任务链自动生成",
            "- 任务流: load_market_data → chanlun_backtest → join_union_report → pangu_inference → write_replay_report",
            "- 交易逻辑: chanlun 缠论买卖点 (非 SMA)",
            "- 结果 artifact 路径可追溯，支持复现",
            "",
            f"原始结果 JSON: `{bt_path}`",
        ])
        if union_path:
            lines.append(f"联合报告 JSON: `{union_path}`")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        out_dir = artifact_dir(workspace_dir, dag_id)
        meta_path = out_dir / "report_meta.json"
        meta = {
            "report_path": str(report_path),
            "metrics": metrics,
            "audit": audit,
            "union": union_data.get("cross_domain"),
            "pangu": pangu_data,
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_path": str(meta_path),
            "report_path": str(report_path),
            "summary": metrics,
        }


if __name__ == "__main__":
    WriteReplayReport().execute()
