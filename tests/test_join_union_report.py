#!/usr/bin/env python3
"""Unit tests for cross-domain union report helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.join_union_report import (  # noqa: E402
    DEFAULT_SC_IMMUNE,
    _compute_alignment,
    _compute_risk_indicator,
    _extract_chanlun_summary,
)


def test_extract_chanlun_summary_from_structure():
    data = {
        "metrics": {"strokes_count": 10, "duan_count": 2, "divergence_count": 3},
        "structure": {"duan": [{}, {}], "divergences": [{}, {}, {}]},
    }
    summary = _extract_chanlun_summary(data)
    assert summary["bi_count"] == 10
    assert summary["duan_count"] == 2
    assert summary["divergence_events"] == 3


def test_compute_alignment_responder_stable():
    chanlun = {"structure_valid": True, "divergence_events": 5}
    result = _compute_alignment(chanlun, DEFAULT_SC_IMMUNE)
    assert result["status"] == "aligned"
    assert result["score"] >= 0.65


def test_compute_risk_indicator_low_risk():
    chanlun = {"divergence_events": 2, "structure_valid": True}
    risk = _compute_risk_indicator(chanlun, DEFAULT_SC_IMMUNE)
    assert risk == 0.0


def test_compute_risk_indicator_high_divergence():
    chanlun = {"divergence_events": 25, "structure_valid": False}
    immune = {"mem_exh_ratio_responder": 0.5, "mem_exh_ratio_nonresponder": 2.0}
    risk = _compute_risk_indicator(chanlun, immune)
    assert risk >= 0.5
