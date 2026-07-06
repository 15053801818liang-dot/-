#!/usr/bin/env python3
"""
NIF3XScRNA.py — 系统发育 × 单细胞转录组联合分析智能体
集成 LLM 智能解读 + 选项 D（审计验证闭环，自包含，可对接盘古 reasoner）
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from Bio import AlignIO, Phylo, SeqIO
import anndata as ad
import scanpy as sc


# ---------- LLM 客户端 ----------


class LLMClient:
    """轻量级 LLM 客户端，支持 OpenAI 和 Anthropic，自动降级。"""

    def __init__(self) -> None:
        self.provider = "none"
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai

                self.client = openai.OpenAI(api_key=openai_key)
                self.provider = "openai"
                return
            except ImportError:
                pass

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=anthropic_key)
                self.provider = "anthropic"
                return
            except ImportError:
                pass

    def is_available(self) -> bool:
        return self.provider != "none" and self.client is not None

    def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        if not self.is_available():
            return "[LLM 未配置，跳过智能解读]"

        if self.provider == "openai":
            model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )
                return resp.choices[0].message.content.strip()
            except Exception as exc:
                return f"[LLM 调用失败: {exc}]"

        if self.provider == "anthropic":
            model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
            try:
                resp = self.client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.3,
                    max_tokens=800,
                )
                return resp.content[0].text.strip()
            except Exception as exc:
                return f"[LLM 调用失败: {exc}]"

        return "[LLM 未配置]"


# ---------- 1. 感知层 ----------


class NIF3ScRNAAgent:
    def __init__(self, workdir: str = ".") -> None:
        self.workdir = Path(workdir)
        self.state: Dict[str, Any] = {
            "has_fasta": False,
            "has_alignment": False,
            "has_tree": False,
            "has_asr": False,
            "has_h5ad": False,
            "nif3_homologs": [],
            "metal_sites": {},
            "cell_types": [],
            "gene_names": [],
        }
        self._locate_assets()

    def _locate_assets(self) -> None:
        fasta = self.workdir / "nif3_homologs.fasta"
        aln = self.workdir / "nif3_aligned.fasta"
        tree = self.workdir / "nif3.treefile"
        asr = self.workdir / "nif3_asr.state"
        h5ad = self.workdir / "sadefeldman_processed.h5ad"

        self.state["has_fasta"] = fasta.exists()
        self.state["has_alignment"] = aln.exists()
        self.state["has_tree"] = tree.exists()
        self.state["has_asr"] = asr.exists()
        self.state["has_h5ad"] = h5ad.exists()

        if self.state["has_fasta"]:
            self.state["nif3_homologs"] = [r.id for r in SeqIO.parse(fasta, "fasta")]

        self.state["metal_sites"] = {
            "H63": "histidine",
            "H64": "histidine",
            "D101": "aspartate",
            "H215": "histidine",
            "E219": "glutamate",
        }

        if self.state["has_h5ad"]:
            adata = sc.read_h5ad(h5ad)
            self.state["gene_names"] = adata.var_names.tolist()
            if "cell_type" in adata.obs.columns:
                self.state["cell_types"] = adata.obs["cell_type"].unique().tolist()
            elif "leiden" in adata.obs.columns:
                self.state["cell_types"] = adata.obs["leiden"].unique().tolist()

    def sense(self) -> Dict[str, Any]:
        return self.state


# ---------- 2. 规划层 ----------


class NIF3Planner:
    def __init__(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.plan: List[Dict[str, str]] = []

    def build_plan(self) -> List[Dict[str, str]]:
        if self.state["has_alignment"] and self.state["has_h5ad"]:
            self.plan.extend(
                [
                    {"step": "map_metal_to_gene", "description": "映射金属位点保守性到基因表达"},
                    {"step": "correlate_phylogeny_and_expression", "description": "系统发育距离与表达相关性"},
                    {"step": "generate_report", "description": "生成联合分析报告（含 LLM 解读与审计验证）"},
                ]
            )
        else:
            self.plan.append({"step": "warn_missing_data", "description": "缺失关键数据"})
        return self.plan


# ---------- 3. 执行层 ----------


def _try_pangu_re_reason(artifact_path: Path, feedback: str) -> Optional[Dict[str, Any]]:
    """内联盘古二次推理（可选；失败则返回 None）。"""
    root = Path(__file__).resolve().parent
    pangu_dir = root / "盘古"
    kb = root / "configs" / "pangu_symbolic_kb.json"
    if not pangu_dir.exists():
        return None
    try:
        sys.path.insert(0, str(pangu_dir))
        from reasoner import PanguReasoner

        reasoner = PanguReasoner(kb_path=str(kb) if kb.exists() else None)
        return reasoner.reason_from_artifact(str(artifact_path), feedback=feedback)
    except Exception:
        return None


class NIF3Executor:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.results: Dict[str, Any] = {}
        self.llm = LLMClient()

    def map_metal_to_gene(self, aln_path: Path, h5ad_path: Path) -> Dict[str, Any]:
        aln = AlignIO.read(aln_path, "fasta")
        ec_label = "P0AFP6"
        ec_seq = next((rec for rec in aln if rec.id.startswith(ec_label)), aln[0])

        metal_conservation: Dict[str, float] = {}
        metal_positions = {"H": [63, 64, 215], "D": [101], "E": [219]}
        for aa, positions in metal_positions.items():
            for pos in positions:
                col_idx = pos - 1
                if col_idx < len(ec_seq):
                    col_aa = ec_seq[col_idx]
                    col_chars = [rec.seq[col_idx] for rec in aln if rec.seq[col_idx] != "-"]
                    if col_chars:
                        conserved = sum(1 for c in col_chars if c == col_aa) / len(col_chars)
                        metal_conservation[f"{aa}{pos}"] = conserved

        adata = sc.read_h5ad(h5ad_path)
        candidates = ["YbgI", "C12orf65", "NIF3L1", "NIF3L2"]
        available: List[str] = []
        for c in candidates:
            matches = [g for g in adata.var_names if c.lower() in g.lower()]
            if matches:
                available.extend(matches)
        available = list(set(available))

        expression_summary: Dict[str, Any] = {}
        if available:
            expr = adata[:, available].X
            if hasattr(expr, "toarray"):
                expr = expr.toarray()
            expr_df = pd.DataFrame(expr, columns=available)
            if "cell_type" in adata.obs.columns:
                expr_df["cell_type"] = adata.obs["cell_type"].values
                expression_summary = expr_df.groupby("cell_type").mean().to_dict()
            else:
                expression_summary = {"overall_mean": expr_df.mean().to_dict()}

        result = {
            "metal_conservation": metal_conservation,
            "available_genes": available,
            "expression_summary": expression_summary,
        }
        self.results["metal_expression"] = result
        return result

    def correlate_phylogeny_and_expression(self, tree_path: Path) -> Dict[str, Any]:
        tree = Phylo.read(tree_path, "newick")
        tips = [tip.name for tip in tree.get_terminals()]
        distances = []
        for i, t1 in enumerate(tips):
            for t2 in tips[i + 1 :]:
                distances.append(tree.distance(t1, t2))
        result = {
            "num_tips": len(tips),
            "avg_distance": sum(distances) / len(distances) if distances else 0,
            "max_distance": max(distances) if distances else 0,
        }
        self.results["tree_stats"] = result
        return result

    def _llm_interpretation(self, state: Dict[str, Any], metal_res: Dict[str, Any], tree_stats: Dict[str, Any]) -> str:
        if not self.llm.is_available():
            return "> LLM 未配置，无法生成智能解读。请设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY 环境变量。\n"

        cons = metal_res.get("metal_conservation", {})
        cons_str = "\n".join([f"- {site}: {val:.2%}" for site, val in cons.items()])
        genes = metal_res.get("available_genes", [])
        genes_str = ", ".join(genes) if genes else "无明确同源基因"

        expr_summary = metal_res.get("expression_summary", {})
        expr_sample = ""
        if expr_summary:
            first_key = next(iter(expr_summary))
            if isinstance(expr_summary[first_key], dict):
                cell_expr = expr_summary[first_key]
                top_cells = sorted(cell_expr.items(), key=lambda x: x[1], reverse=True)[:3]
                expr_sample = f"最高表达细胞类型: {', '.join([f'{c} ({v:.2f})' for c, v in top_cells])}"
            else:
                expr_sample = f"整体平均表达: {expr_summary.get('overall_mean', {})}"

        system = (
            "你是一位计算生物学与演化生物学的专家，擅长整合系统发育与单细胞转录组数据。"
            "请基于提供的数据摘要，给出科学解读，提出可能的功能假说，并指出值得进一步验证的方向。回答不超过300字。"
        )
        user = f"""
# 数据摘要
## 系统发育
- 树末端节点数: {tree_stats['num_tips']}
- 平均树距离: {tree_stats['avg_distance']:.4f}
## 金属配位残基保守性
{cons_str}
## 单细胞表达
- 找到同源基因: {genes_str}
- {expr_sample}
请给出你的解读。
"""
        return self.llm.generate(system, user)

    def _load_artifact(self, artifact_path: Path) -> Dict[str, Any]:
        if artifact_path.suffix == ".gz":
            with gzip.open(artifact_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        with artifact_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _parse_structure(self, data: Dict[str, Any]) -> Tuple[List[float], List[Dict], List[Dict]]:
        detail = data.get("structure_detail") or {}
        if detail:
            strokes = detail.get("recent_strokes") or []
            pivots = detail.get("active_pivots") or []
            prices: List[float] = []
            for stroke in strokes:
                start = stroke.get("start") or {}
                end = stroke.get("end") or {}
                prices.extend(
                    [
                        float(stroke.get("start_price", start.get("price", 0) or 0)),
                        float(stroke.get("end_price", end.get("price", 0) or 0)),
                    ]
                )
            return prices, strokes, pivots

        if "bi" in data and "prices" in data:
            return data["prices"], data.get("bi", []), data.get("pivots", [])

        return data.get("prices", []), data.get("strokes", data.get("bi", [])), data.get("pivots", data.get("zhongshu", []))

    def _plot_strokes_and_pivots(
        self,
        ax,
        data: Dict[str, Any],
        *,
        color: str = "gray",
        alpha: float = 0.5,
        label: str | None = None,
        price_scale: float = 1.0,
    ) -> None:
        prices, strokes, pivots = self._parse_structure(data)
        plotted_label = False

        if prices:
            x = np.arange(len(prices))
            y = np.array(prices, dtype=float) * price_scale
            ax.plot(x, y, color=color, alpha=alpha, linewidth=1.2, label=label if not plotted_label else None)
            plotted_label = True

        x_min, x_max = ax.get_xlim()
        for pivot in pivots:
            if isinstance(pivot, dict):
                zd = float(pivot.get("zd", pivot.get("ZD", pivot.get("low", 0)) or 0))
                zg = float(pivot.get("zg", pivot.get("ZG", pivot.get("high", 0)) or 0))
                if zd and zg:
                    ax.axhspan(zd * price_scale, zg * price_scale, color="red" if color == "gray" else "blue", alpha=0.15)
            elif isinstance(pivot, (list, tuple)) and len(pivot) >= 2:
                ax.axhspan(float(pivot[0]) * price_scale, float(pivot[1]) * price_scale, color="red", alpha=0.15)

        for stroke in strokes:
            if not isinstance(stroke, dict):
                continue
            start = stroke.get("start") or {}
            end = stroke.get("end") or {}
            x0 = int(start.get("bar_index", stroke.get("start_idx", 0)))
            x1 = int(end.get("bar_index", stroke.get("end_idx", x0)))
            y0 = float(stroke.get("start_price", start.get("price", 0) or 0)) * price_scale
            y1 = float(stroke.get("end_price", end.get("price", 0) or 0)) * price_scale
            ax.plot(
                [x0, x1],
                [y0, y1],
                color="orange" if color == "gray" else "cyan",
                linewidth=2,
                alpha=0.75,
            )

        if label and not plotted_label:
            ax.plot([], [], color=color, label=label)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc="best", fontsize=8)

    def _simulate_correction(self, data: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        pangu_sidecar = data.get("pangu_inference") or {}
        state_code = pangu_sidecar.get("state_code") or data.get("state_code", "NEUTRAL")
        confidence = float(pangu_sidecar.get("confidence") or data.get("confidence", 0.5))

        if "高估" in feedback or "偏移" in feedback:
            state_code = "OSC_NEUTRAL"
            confidence = max(0.1, confidence - 0.1)
            interpretation = f"【人工质疑】{feedback[:80]} → 已降级为中性（模拟）"
        elif "确认" in feedback or "正确" in feedback:
            interpretation = f"【人工确认】{feedback[:80]} → 维持原判（模拟）"
            confidence = min(1.0, confidence + 0.05)
        else:
            interpretation = f"收到反馈: {feedback[:100]}，状态码保持 {state_code}（模拟）"

        return {
            "state_code": state_code,
            "confidence": confidence,
            "interpretation": interpretation,
            "shift": 0.0,
            "source": "simulated",
        }

    def validate_with_audit(self, artifact_path: Path, feedback: str) -> Dict[str, Any]:
        """选项 D：审计验证闭环 — 纠错 + 复合图 + 结构化结果。"""
        print(f"   🔍 审计验证: {artifact_path.name}")
        data = self._load_artifact(artifact_path)

        correction = _try_pangu_re_reason(artifact_path, feedback)
        if correction:
            correction = {
                "state_code": correction.get("state_code", "UNKNOWN"),
                "confidence": float(correction.get("confidence", 0.5)),
                "interpretation": correction.get("interpretation", ""),
                "shift": 0.0,
                "source": "pangu_reasoner",
            }
        else:
            correction = self._simulate_correction(data, feedback)

        state_code = correction["state_code"]
        confidence = correction["confidence"]
        interpretation = correction["interpretation"]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        orig_state = (data.get("pangu_inference") or {}).get("state_code") or data.get("state_code", "UNKNOWN")

        self._plot_strokes_and_pivots(ax1, data, color="gray", alpha=0.6, label="原始结构")
        ax1.set_title(f"原始结构 (状态: {orig_state})")
        ax1.set_xlabel("bar_index")
        ax1.set_ylabel("price")

        self._plot_strokes_and_pivots(ax2, data, color="gray", alpha=0.25, label="原始结构")
        shift_pct = 0.2 if ("偏移" in feedback or "高估" in feedback) else 0.0
        if shift_pct:
            self._plot_strokes_and_pivots(
                ax2, data, color="red", alpha=0.85, label="修正后（示意）", price_scale=1.0 + shift_pct / 100.0
            )
            correction["shift"] = shift_pct
        ax2.set_title(f"修正后结构 (状态: {state_code})")
        ax2.set_xlabel("bar_index")
        ax2.set_ylabel("price")

        if correction.get("shift"):
            fig.suptitle(f"审计验证: 偏移量 {correction['shift']:.2f}%", fontsize=14)

        plt.tight_layout()
        validation_plot = self.workdir / "audit_validation.png"
        plt.savefig(validation_plot, dpi=150)
        plt.close()

        verified_states = {"OSC_BUY", "OSC_SELL", "BUY_DIVERGENCE_CONFIRM", "HIGH_RISK_EXIT"}
        result = {
            "validation_status": "VERIFIED" if state_code in verified_states else "DEVIATED",
            "shift_percent": float(correction.get("shift", 0.0)),
            "new_state": state_code,
            "new_confidence": confidence,
            "plot_path": str(validation_plot),
            "summary": interpretation,
            "correction_source": correction.get("source", "unknown"),
        }
        self.results["validation"] = result
        return result

    def generate_report(self, state: Dict[str, Any], metal_res: Dict[str, Any], tree_stats: Dict[str, Any]) -> str:
        report_lines = [
            "# NIF3 蛋白家族 × 黑色素瘤单细胞转录组 联合分析报告",
            f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
            "## 1. 系统发育分析摘要",
            f"- 同源序列数: {len(state['nif3_homologs'])}",
            f"- 树末端节点数: {tree_stats['num_tips']}",
            f"- 平均树距离: {tree_stats['avg_distance']:.4f}",
            f"- 最大树距离: {tree_stats['max_distance']:.4f}\n",
            "## 2. 金属配位残基保守性",
            "| 位点 | 残基 | 保守度 |",
            "|------|------|--------|",
        ]
        cons = metal_res.get("metal_conservation", {})
        for site, val in cons.items():
            report_lines.append(f"| {site} | {state['metal_sites'].get(site, '')} | {val:.2%} |")
        report_lines.append("")
        self._plot_conservation_heatmap(cons)

        report_lines.append("## 3. 单细胞表达概况")
        genes = metal_res.get("available_genes", [])
        if genes:
            report_lines.append(f"- 找到 NIF3 同源基因: {', '.join(genes)}")
            expr_summary = metal_res.get("expression_summary", {})
            if expr_summary:
                report_lines.append("### 各细胞类型的平均表达（部分）")
                df = pd.DataFrame(expr_summary)
                try:
                    report_lines.append(df.head(10).to_markdown())
                except ImportError:
                    report_lines.append(df.head(10).to_string())
                self._plot_expression_heatmap(df)
        else:
            report_lines.append("⚠️ 未在单细胞数据中找到明确的 NIF3 同源基因（尝试了 YbgI, C12orf65, NIF3L1/L2）")

        report_lines.append("## 4. 智能解读（LLM 生成）")
        report_lines.append(self._llm_interpretation(state, metal_res, tree_stats))

        report_lines.append("## 5. 静态推论")
        if cons and genes:
            high_conserved = [site for site, v in cons.items() if v > 0.9]
            if high_conserved:
                report_lines.append(f"- 高度保守位点: {', '.join(high_conserved)}，暗示这些残基对功能至关重要。")
            report_lines.append("- 同源基因在单细胞中检出，提示 NIF3 功能在黑色素瘤微环境中可能具有转录活性。")
        else:
            report_lines.append("- 数据不足以推导交叉结论，建议补充表达数据或优化基因映射。")

        if "validation" in self.results:
            val = self.results["validation"]
            report_lines.extend(
                [
                    "## 6. 审计验证结果（选项 D）",
                    f"- 验证状态: **{val['validation_status']}**",
                    f"- 背驰偏移量: {val['shift_percent']:.2f}%",
                    f"- 修正后状态码: {val['new_state']}",
                    f"- 置信度: {val['new_confidence']:.2f}",
                    f"- 纠错来源: {val.get('correction_source', 'unknown')}",
                    f"- 解读: {val['summary']}",
                    f"![审计验证复合图]({Path(val['plot_path']).name})",
                    "",
                ]
            )

        report_lines.append("\n---")
        report_lines.append("*报告由 NIF3XScRNA 智能体自动生成，LLM 解读由 AI 生成，需结合领域知识审阅。*")

        report_path = self.workdir / "nif3_scRNA_report.md"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        self._add_image_references(report_path)
        return str(report_path)

    def _plot_conservation_heatmap(self, cons: Dict[str, float]) -> None:
        if not cons:
            return
        plt.figure(figsize=(6, 4))
        sites = list(cons.keys())
        values = list(cons.values())
        sns.barplot(x=sites, y=values, palette="viridis")
        plt.ylim(0, 1)
        plt.ylabel("保守度")
        plt.title("金属配位残基保守性")
        for i, v in enumerate(values):
            plt.text(i, v + 0.02, f"{v:.0%}", ha="center")
        plt.tight_layout()
        plt.savefig(self.workdir / "metal_conservation_heatmap.png", dpi=150)
        plt.close()

    def _plot_expression_heatmap(self, expr_df: pd.DataFrame) -> None:
        if expr_df.empty:
            return
        num_cols = expr_df.select_dtypes(include=[np.number]).columns
        if len(num_cols) == 0:
            return
        plot_data = expr_df[num_cols[:10]]
        plt.figure(figsize=(8, 6))
        sns.heatmap(plot_data.T, cmap="RdBu_r", center=0, annot=False)
        plt.title("NIF3 同源基因表达（细胞类型均值）")
        plt.tight_layout()
        plt.savefig(self.workdir / "expression_heatmap.png", dpi=150)
        plt.close()

    def _add_image_references(self, report_path: Path) -> None:
        with report_path.open("a", encoding="utf-8") as f:
            f.write("\n\n## 7. 可视化图表\n")
            f.write("![金属位点保守性](metal_conservation_heatmap.png)\n\n")
            f.write("![表达热图](expression_heatmap.png)\n")


# ---------- 4. 主入口 ----------


def run_nif3_scRNA_analysis(
    workdir: str = ".",
    audit_artifact: str | None = None,
    audit_feedback: str | None = None,
) -> None:
    print("\n🧬 NIF3 × ScRNA 联合分析智能体启动 (LLM + 审计验证)")
    print("=" * 60)

    agent = NIF3ScRNAAgent(workdir)
    state = agent.sense()
    print(f"📊 感知结果: 系统发育数据={state['has_alignment']}, 单细胞数据={state['has_h5ad']}")

    planner = NIF3Planner(state)
    plan = planner.build_plan()
    print(f"📋 执行计划: {[p['step'] for p in plan]}")

    executor = NIF3Executor(Path(workdir))

    for step in plan:
        print(f"\n▶ 执行: {step['step']}")
        if step["step"] == "map_metal_to_gene":
            result = executor.map_metal_to_gene(
                Path(workdir) / "nif3_aligned.fasta",
                Path(workdir) / "sadefeldman_processed.h5ad",
            )
            print(f"   → 金属位点保守度: {len(result['metal_conservation'])} 个位点")
            print(f"   → 找到基因: {result['available_genes']}")

        elif step["step"] == "correlate_phylogeny_and_expression":
            stats = executor.correlate_phylogeny_and_expression(Path(workdir) / "nif3.treefile")
            print(f"   → 树末端节点数: {stats['num_tips']}, 平均距离: {stats['avg_distance']:.4f}")

        elif step["step"] == "generate_report":
            if audit_artifact and audit_feedback:
                artifact_path = Path(audit_artifact)
                if not artifact_path.is_absolute():
                    artifact_path = Path(workdir) / artifact_path
                if artifact_path.exists():
                    print("\n   🔍 执行选项 D 审计验证...")
                    validation = executor.validate_with_audit(artifact_path, audit_feedback)
                    print(f"   → 验证状态: {validation['validation_status']}")
                else:
                    print(f"   ⚠️ 审计 artifact 不存在: {artifact_path}")

            metal_res = executor.results.get("metal_expression", {})
            tree_stats = executor.results.get("tree_stats", {})
            report_path = executor.generate_report(state, metal_res, tree_stats)
            print(f"   → 报告已生成: {report_path}")

        elif step["step"] == "warn_missing_data":
            print("   ⚠️ 缺少关键数据，跳过分析。请确保 nif3_aligned.fasta 和 sadefeldman_processed.h5ad 存在。")

    print("\n✅ 分析完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NIF3 × ScRNA 联合分析 + 选项 D 审计验证")
    parser.add_argument("--workdir", default=".", help="工作目录")
    parser.add_argument("--audit", help="审计 artifact 路径（如 workspace/artifacts/.../chanlun_replay.json）")
    parser.add_argument(
        "--feedback",
        default="背驰点与中枢区间存在偏移，请重新映射",
        help="审计反馈",
    )
    args = parser.parse_args()
    run_nif3_scRNA_analysis(workdir=args.workdir, audit_artifact=args.audit, audit_feedback=args.feedback)
