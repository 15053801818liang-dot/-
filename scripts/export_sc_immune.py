#!/usr/bin/env python3
"""导出单细胞分析结论到 workspace/artifacts/sc_immune_conclusion.json"""

from __future__ import annotations

import json
from pathlib import Path

SC_IMMUNE = {
    "source": "GSE120575_Sade_Feldman_2018",
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
        "LEF1", "FOXP1", "PLAC8", "LTB",
    ],
    "response_down_genes": [
        "NKG7", "PRF1", "GZMA", "GZMB", "GZMH",
        "CCL4", "CCL5", "HLA-DRA", "CD38", "GBP5",
    ],
    "cell_type_composition": {
        "CD8_memory_like": {"responder": 0.346, "nonresponder": 0.259},
        "CD8_exhausted": {"responder": 0.180, "nonresponder": 0.272},
        "B_cells": {"responder": 0.196, "nonresponder": 0.072},
        "Macrophage_Mono": {"responder": 0.036, "nonresponder": 0.117},
        "Cycling_T": {"responder": 0.019, "nonresponder": 0.050},
        "pDC": {"responder": 0.008, "nonresponder": 0.022},
    },
}


def main() -> None:
    out_dir = Path("workspace/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sc_immune_conclusion.json"
    out_path.write_text(json.dumps(SC_IMMUNE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"sc_immune_conclusion.json exported to {out_path}")


if __name__ == "__main__":
    main()
