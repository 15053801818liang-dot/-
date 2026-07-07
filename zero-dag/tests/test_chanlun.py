"""Tests for chanlun engine — edge cases and validation"""
import sys, os, numpy as np, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from czsc import RawBar, Freq
from internal.chanlun.duan_engine import DuanEngine
from internal.chanlun.chanlun_engine import ChanlunEngine
from internal.chanlun.backtest import run_backtest

BASE = datetime(2024, 1, 1, 10, 0)


def rb(i, o, h, l, c, v=10.0):
    return RawBar(symbol='T', id=i, dt=BASE + timedelta(minutes=i * 5),
                  open=float(o), high=float(h), low=float(l), close=float(c),
                  vol=float(v), amount=float(v * c), freq=Freq.F5)


def _make_divergence_bars(direction='up', n_waves=6):
    """Build bars with clear divergence: same direction, weakening power, with noise to form bi."""
    rng = np.random.RandomState(42)
    bars = []; t = 0; price = 50000.0
    for wave in range(n_waves):
        power = 600.0 - wave * 90.0
        for i in range(120):
            t += 1; dt = BASE + timedelta(minutes=t * 5)
            if direction == 'up':
                mid = price + power / 120 * (i + 1) * 0.4
            else:
                mid = price - power / 120 * (i + 1) * 0.4
            o = mid + rng.randn() * 20
            h = mid + abs(rng.randn() * 60) + 30
            l = mid - abs(rng.randn() * 60) - 30
            c = mid + rng.randn() * 40
            bars.append(rb(t, o, h, l, c))
        for i in range(50):
            t += 1; dt = BASE + timedelta(minutes=t * 5)
            pb = bars[-1].close - i * 25 / 50 + rng.randn() * 30
            bars.append(rb(t, pb, pb + 15, pb - 15, pb))
    return bars


# ── Edge cases ────────────────────────────────────
def test_duan_empty_bars():
    d = DuanEngine().decompose([])
    assert d['bi_count'] == 0


def test_duan_insufficient_bars():
    d = DuanEngine().decompose([rb(i, 100, 110, 90, 105) for i in range(3)])
    assert d['bi_count'] == 0


def test_duan_normal_500_bars():
    rng = np.random.RandomState(99)
    n = 500
    mid = 50000 + np.cumsum(rng.randn(n) * 80) + np.sin(np.linspace(0, 6 * np.pi, n)) * 300
    bars = [rb(i, mid[i] + rng.randn() * 20, mid[i] + abs(rng.randn() * 60) + 15,
               mid[i] - abs(rng.randn() * 60) - 15, mid[i] + rng.randn() * 30) for i in range(n)]
    d = DuanEngine().decompose(bars)
    assert d['bi_count'] > 10, f'expected >10 bi, got {d["bi_count"]}'
    assert d['last_direction'] in ('向上', '向下')


# ── Divergence detection ─────────────────────────
def test_clear_top_divergence():
    bars = _make_divergence_bars('up')
    d = DuanEngine().decompose(bars)
    c = ChanlunEngine().run(bars, d)
    top = [s for s in c['signals'] if s['type'] == 'top_divergence']
    assert len(top) >= 1, f'expected top divergence, got 0. bi={d["bi_count"]}'
    for s in top:
        assert s['prev_power'] > s['curr_power']


def test_clear_bottom_divergence():
    bars = _make_divergence_bars('down')
    d = DuanEngine().decompose(bars)
    c = ChanlunEngine().run(bars, d)
    bottom = [s for s in c['signals'] if s['type'] == 'bottom_divergence']
    assert len(bottom) >= 1, f'expected bottom divergence, got 0. bi={d["bi_count"]}'
    for s in bottom:
        assert s['prev_power'] > s['curr_power']


def test_no_divergence_trending():
    rng = np.random.RandomState(42)
    n = 400
    trend = 50000 + np.cumsum(np.ones(n) * 60) + rng.randn(n) * 30
    bars = [rb(i, v + 10, v + 50, v - 10, v + 30) for i, v in enumerate(trend)]
    d = DuanEngine().decompose(bars)
    c = ChanlunEngine().run(bars, d)
    assert len(c['signals']) <= 3, f"strong trend={len(c['signals'])} signals, bi={d['bi_count']}"


# ── Backtest ─────────────────────────────────────
def test_backtest_no_signals():
    bt = run_backtest([], {"signals": []})
    assert bt['num_trades'] == 0
    assert bt['total_return_pct'] == 0.0


def test_backtest_buy_hold():
    bars = [rb(i, 100 + i, 100 + i + 10, 100 + i - 5, 100 + i + 2) for i in range(100)]
    s = [{"type": "bottom_divergence", "bi_index": 10, "price": 110},
         {"type": "top_divergence", "bi_index": 80, "price": 180}]
    bt = run_backtest(bars, {"signals": s})
    assert bt['num_trades'] == 2
    assert bt['total_return_pct'] > 0


def test_backtest_bear_market_nobuy():
    bars = [rb(i, 50000 - i * 50, 50000 - i * 50 + 10, 50000 - i * 50 - 20, 50000 - i * 50 + 2) for i in range(100)]
    s = [{"type": "top_divergence", "bi_index": 50, "price": 47500}]
    bt = run_backtest(bars, {"signals": s})
    assert bt['num_trades'] == 0


def test_backtest_win_rate_perfect():
    bars = [rb(i, 100 + i * 5, 100 + i * 5 + 5, 100 + i * 5 - 5, 100 + i * 5) for i in range(50)]
    s = [{"type": "bottom_divergence", "bi_index": 5, "price": 125},
         {"type": "top_divergence", "bi_index": 20, "price": 200},
         {"type": "bottom_divergence", "bi_index": 25, "price": 225},
         {"type": "top_divergence", "bi_index": 40, "price": 300}]
    bt = run_backtest(bars, {"signals": s})
    assert bt['num_trades'] == 4
    assert bt['win_rate_pct'] == 100.0


# ── Artifact loader ──────────────────────────────
def test_artifact_loader_parquet():
    import tempfile, os as _os
    from internal.chanlun.artifact_loader import load_market_data, to_raw_bars, debug_artifact
    df = pd.DataFrame({
        'dt': pd.date_range('2024-01-01', periods=100, freq='5min'),
        'open': np.random.randn(100) * 10 + 50000,
        'high': np.random.randn(100) * 10 + 50050,
        'low': np.random.randn(100) * 10 + 49950,
        'close': np.random.randn(100) * 10 + 50000,
        'vol': np.ones(100) * 100,
        'amount': np.ones(100) * 5e5,
    })
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        df.to_parquet(f.name)
        path = f.name
    try:
        loaded = load_market_data(path)
        assert len(loaded) == 100
        bars = to_raw_bars(loaded, '5min')
        assert len(bars) == 100
        assert hasattr(bars[0], 'open')
        info = debug_artifact(path)
        assert info['exists']
        assert info['rows'] == 100
    finally:
        _os.unlink(path)


def test_artifact_loader_bad_path():
    from internal.chanlun.artifact_loader import debug_artifact
    assert not debug_artifact('/nonexistent/path.xyz')['exists']


# ── Pangu integration ────────────────────────────
def test_pangu_with_chanlun_output():
    from pangu.reasoner import PanguReasoner
    rr = PanguReasoner().infer(0.85, {'cd8_mem_ratio': 0.31, 'auc_delta': 0.06, 'rscore': 2.8, 'nr_score': -16.8})
    assert rr['state_code'] in ('OSC_BUY_DIVERGENCE', 'OSC_SELL_DIVERGENCE', 'OSC_NEUTRAL')
    assert 0 <= rr['confidence'] <= 1.0


def test_pangu_risk_hold():
    from pangu.reasoner import PanguReasoner
    from pangu.arbiter import Arbiter
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        yy = PanguReasoner().infer(0.5, {})
        v = Arbiter(tmp).adjudicate(yy)
        assert v['risk'] in ('LOW', 'MEDIUM', 'HIGH')
        assert v['action'] in ('BUY', 'SELL', 'HOLD', 'PAPER_TRADE')
