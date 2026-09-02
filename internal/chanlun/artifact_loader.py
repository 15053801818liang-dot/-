"""从 myth002 DAG artifact（Parquet/CSV）加载 czsc RawBar 序列。"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
from czsc import Freq, RawBar

FREQ_MAP = {"1m": Freq.F1, "5m": Freq.F5, "30m": Freq.F30}
INTERVAL_MINUTES = {"1m": 1, "5m": 5, "30m": 30}


def _read_market_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    return df.sort_values(
        "open_time" if "open_time" in df.columns else ("timestamp" if "timestamp" in df.columns else "index")
    ).reset_index(drop=True)


def _resolve_open_time(df: pd.DataFrame, freq_key: str) -> pd.Series:
    if "open_time" in df.columns:
        return pd.to_datetime(df["open_time"])
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"])
    minutes = INTERVAL_MINUTES.get(freq_key, 5)
    base = pd.Timestamp("2024-01-01T00:00:00")
    idx = df["index"] if "index" in df.columns else pd.Series(range(len(df)))
    return base + pd.to_timedelta(idx.astype(int) * minutes, unit="m")


def load_bars_from_artifact(path: str | Path, symbol: str, freq_key: str = "5m") -> List[RawBar]:
    """读取上游 load_market_data artifact，兼容 myth002 与 PR 库两种列格式。"""
    path = Path(path)
    df = _read_market_frame(path)
    freq = FREQ_MAP.get(freq_key, Freq.F5)
    open_times = _resolve_open_time(df, freq_key)

    quote_volume = df["quote_volume"] if "quote_volume" in df.columns else df["volume"] * df["close"]

    bars: List[RawBar] = []
    for i in range(len(df)):
        row = df.iloc[i]
        bars.append(
            RawBar(
                symbol=symbol,
                id=i,
                dt=open_times.iloc[i].to_pydatetime(),
                freq=freq,
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                vol=float(row["volume"]),
                amount=float(quote_volume.iloc[i]),
            )
        )
    return bars
