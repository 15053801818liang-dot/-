#!/usr/bin/env python3
"""联合报告节点：合并缠论结构分析与单细胞免疫结论。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.task_base import TaskBase, artifact_dir

DEFAULT_SC_IMMUNE: Dict[str, Any] = {
    "source": "GSE120575_Sade-Feldman_2018",
    "n_cells": 16060,
    "n_patients": 32,
    "n_samples": 48,
    "key_finding": "CD8_memory_enriched_in_responders",
    "mem_exh_ratio_responder": 2.70,
    "mem_exh_ratio_nonresponder": 0.91,
    "mem_exh_p": 0.0029,
    "auc_loo": 0.859,
    "auc_paper": 0.843,
    "auc_mem_exh": 0.767,
    "response_up_genes": [
        "IL7R", "GPR183", "CCR7", "SELL", "TCF7",
        "LEF1", "FOXP1", "PLAC8", "LTB", "CD55",
        "YPEL5", "SORL1", "ATM",
    ],
    "response_down_genes": [
        "NKG7", "PRF1", "GZMA", "GZMB", "GZMH",
        "CCL4", "CCL5", "HLA-DRA", "HLA-DPA1",
        "HLA-DRB1", "IFI6", "PSMB9", "GBP5", "CD38",
    ],
    "cell_type_composition": {
        "CD8_memory_like": {"responder": 0.346, "nonresponder": 0.259},
        "CD8_exhausted": {"responder": 0.180, "nonresponder": 0.272},
        "B_cells": {"responder": 0.196, "nonresponder": 0.072},
        "Macrophage_Mono": {"responder": 0.036, "nonresponder": 0.117},
        "Cycling_T": {"responder": 0.019, "nonresponder": 0.050},
        "pDC": {"responder": 0.008, "nonresponder": 0.022},
        "Treg": {"responder": 0.035, "nonresponder": 0.040},
        "NK": {"responder": 0.033, "nonresponder": 0.034},
        "CD4_T_conv": {"responder": 0.147, "nonresponder": 0.134},
    },
}


def _artifact_path(artifacts: Dict[str, Any], node_id: str) -> str | None:
    entry = artifacts.get(node_id, {})
    return entry.get("artifact_path") or (entry.get("payload") or {}).get("artifact_path")


def _extract_chanlun_summary(chanlun_data: Dict[str, Any]) -> Dict[str, Any]:
    metrics = chanlun_data.get("metrics", {})
    structure = chanlun_data.get("structure", {})
    validation = chanlun_data.get("validation", {})

    bi_list = chanlun_data.get("bi") or []
    duan_list = structure.get("duan") or chanlun_data.get("duan") or []
    divergences = structure.get("divergences") or chanlun_data.get("divergences") or []

    return {
        "bi_count": metrics.get("strokes_count", structure.get("bi_count", len(bi_list))),
        "duan_count": metrics.get("duan_count", len(duan_list)),
        "divergence_events": metrics.get("divergence_count", len(divergences)),
        "signals_count": metrics.get("signals_count", len(structure.get("signals", []))),
        "structure_valid": validation.get("passed", True),
        "interval_nesting_rate": validation.get("interval_nesting", {}).get("rate"),
    }


def _load_sc_immune(params: Dict[str, Any], workspace_dir: str) -> Dict[str, Any]:
    sc_params = params.get("sc_immune")
    if sc_params:
        return sc_params

    sc_path = Path(workspace_dir) / "artifacts" / "sc_immune_conclusion.json"
    if sc_path.exists():
        with sc_path.open(encoding="utf-8") as f:
            return json.load(f)

    return DEFAULT_SC_IMMUNE.copy()


def _compute_alignment(chanlun: Dict[str, Any], immune: Dict[str, Any]) -> Dict[str, Any]:
    score = 0.5
    if chanlun.get("structure_valid", True):
        score += 0.15
    else:
        score -= 0.1

    mem = immune.get("mem_exh_ratio_responder", 1.0)
    exh = immune.get("mem_exh_ratio_nonresponder", 1.0)
    immune_lean = "responder_like" if mem > exh else "nonresponder_like"

    div_events = chanlun.get("divergence_events", 0)
    structure_lean = "stable" if div_events < 10 else "conflicted"

    if immune_lean == "responder_like" and structure_lean == "stable":
        score += 0.25
    elif immune_lean == "nonresponder_like" and structure_lean == "conflicted":
        score += 0.25
    else:
        score -= 0.15

    score = max(0.0, min(1.0, score))
    if score >= 0.65:
        status = "aligned"
    elif score >= 0.45:
        status = "neutral"
    else:
        status = "misaligned"
    return {"score": round(score, 3), "status": status}


def _compute_risk_indicator(chanlun: Dict[str, Any], immune: Dict[str, Any]) -> float:
    risk = 0.0
    div_events = chanlun.get("divergence_events", 0)
    if div_events > 20:
        risk += 0.3
    elif div_events > 10:
        risk += 0.15
    if not chanlun.get("structure_valid", True):
        risk += 0.2

    mem = immune.get("mem_exh_ratio_responder", 1.0)
    exh = immune.get("mem_exh_ratio_nonresponder", 1.0)
    if exh > mem:
        risk += 0.3

    nesting_rate = chanlun.get("interval_nesting_rate")
    if nesting_rate is not None and nesting_rate < 0.6:
        risk += 0.1
    return round(min(1.0, risk), 3)


class JoinUnionReport(TaskBase):
    def run(self, params, workspace_dir, dag_id, artifacts):
        chanlun_path = _artifact_path(artifacts, "chanlun_backtest")
        if not chanlun_path or not Path(chanlun_path).exists():
            raise ValueError("missing chanlun_backtest artifact")

        with open(chanlun_path, encoding="utf-8") as f:
            chanlun_data = json.load(f)

        sc_data = _load_sc_immune(params, workspace_dir)
        chanlun_summary = _extract_chanlun_summary(chanlun_data)
        cross_domain_align = _compute_alignment(chanlun_summary, sc_data)

        union_report = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dag_id": dag_id,
            "chanlun": chanlun_summary,
            "immune": {
                "source": sc_data.get("source", "GSE120575"),
                "mem_exh_ratio_responder": sc_data.get("mem_exh_ratio_responder"),
                "mem_exh_ratio_nonresponder": sc_data.get("mem_exh_ratio_nonresponder"),
                "auc_loo": sc_data.get("auc_loo"),
                "auc_paper": sc_data.get("auc_paper"),
                "response_up_genes": (sc_data.get("response_up_genes") or [])[:10],
                "response_down_genes": (sc_data.get("response_down_genes") or [])[:10],
                "cell_type_summary": sc_data.get("cell_type_composition", {}),
            },
            "cross_domain": {
                "alignment_score": cross_domain_align["score"],
                "status": cross_domain_align["status"],
                "risk_indicator": _compute_risk_indicator(chanlun_summary, sc_data),
            },
        }

        out_dir = artifact_dir(workspace_dir, dag_id)
        artifact_path = out_dir / "union_report.json"
        artifact_path.write_text(json.dumps(union_report, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "artifact_path": str(artifact_path),
            "chanlun_bi_count": union_report["chanlun"]["bi_count"],
            "immune_auc": union_report["immune"]["auc_loo"],
            "alignment_score": union_report["cross_domain"]["alignment_score"],
        }


if __name__ == "__main__":
    JoinUnionReport().execute()
