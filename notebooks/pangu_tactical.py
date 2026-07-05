"""Notebook 战术工具 — 选项 B/C/D（纠错、可视化、组合拳）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PANGU_DIR = ROOT / "盘古"
if str(PANGU_DIR) not in sys.path:
    sys.path.insert(0, str(PANGU_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_chanlun_artifact(artifact_path: str) -> Dict[str, Any]:
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(artifact_path)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_structure_detail(artifact: Dict[str, Any]) -> Dict[str, Any]:
    return artifact.get("structure_detail") or {}


def force_re_reason(artifact_path: str, user_feedback: str) -> Optional[Dict[str, Any]]:
    """选项 B：注入人类反馈，强制盘古二次推理。"""
    try:
        from reasoner import PanguReasoner

        print(f"🔄 正在注入人类反馈并反思: {user_feedback}")
        kb = ROOT / "configs" / "pangu_symbolic_kb.json"
        reasoner = PanguReasoner(kb_path=str(kb) if kb.exists() else None)
        correction = reasoner.reason_from_artifact(artifact_path, feedback=user_feedback)
        print("\n✅ 纠错完成，新的裁决如下：")
        print(f"   📊 新状态码: {correction.get('state_code')}")
        print(f"   📖 新审计解读: {correction.get('interpretation')}")
        print(f"   📈 新置信度: {correction.get('confidence')}")
        return correction
    except Exception as exc:
        print(f"❌ 纠错引擎异常: {exc}")
        return None


def _stroke_xy(stroke: Dict[str, Any]) -> Tuple[int, float, int, float]:
    start = stroke.get("start") or {}
    end = stroke.get("end") or {}
    x0 = int(start.get("bar_index", stroke.get("index", 0)))
    x1 = int(end.get("bar_index", x0))
    y0 = float(stroke.get("start_price", start.get("price", 0)))
    y1 = float(stroke.get("end_price", end.get("price", y0)))
    return x0, y0, x1, y1


def plot_chanlun_structure(artifact_path: str, figsize: Tuple[int, int] = (14, 7)) -> None:
    """选项 C：缠论结构透视（笔 / 中枢 / 背驰）。"""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("请先安装 matplotlib: pip install matplotlib") from exc

    artifact = load_chanlun_artifact(artifact_path)
    structure = get_structure_detail(artifact)
    if not structure.get("recent_strokes"):
        raise ValueError(
            "artifact 无 structure_detail.recent_strokes；"
            "请使用 chanlun_btc_100k 或重跑 pangu-inference DAG"
        )

    fig, ax = plt.subplots(figsize=figsize)
    strokes = structure.get("recent_strokes") or []

    xs: list[int] = []
    ys: list[float] = []
    for stroke in strokes:
        x0, y0, x1, y1 = _stroke_xy(stroke)
        color = "tab:blue" if stroke.get("direction") == "up" else "tab:orange"
        ax.plot([x0, x1], [y0, y1], color=color, linewidth=2, alpha=0.85)
        ax.plot(x0, y0, "o", color=color, markersize=4)
        xs.extend([x0, x1])
        ys.extend([y0, y1])

    for pivot in structure.get("active_pivots") or []:
        zd = float(pivot.get("zd", 0))
        zg = float(pivot.get("zg", 0))
        if zd and zg and xs:
            ax.axhspan(zd, zg, xmin=0, xmax=1, color="red", alpha=0.12)
            ax.text(xs[0], (zd + zg) / 2, f"ZG={zg:.2f}", fontsize=8, color="darkred")

    div = structure.get("last_divergence")
    if div:
        idx = int(div.get("bar_index", 0))
        price = float(div.get("price", 0))
        ax.scatter(idx, price, color="red", marker="*", s=120, label="Divergence", zorder=5)

    for tp in (structure.get("trade_points") or [])[-3:]:
        idx = int(tp.get("bar_index", 0))
        price = float(tp.get("price", 0))
        ax.scatter(idx, price, color="green", marker="^", s=60, zorder=5)

    ax.set_title("🧠 盘古 · 缠论结构透视")
    ax.set_xlabel("bar_index")
    ax.set_ylabel("price")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def audit_and_visualize(artifact_path: str, user_feedback: str) -> None:
    """选项 D：纠错 + 可视化组合拳。"""
    correction = force_re_reason(artifact_path, user_feedback)
    if not correction:
        return
    print("\n🔄 正在刷新视觉验证...")
    plot_chanlun_structure(artifact_path)
    print("\n✅ 组合拳执行完毕。请对比纠错前后的解读与结构图。")
