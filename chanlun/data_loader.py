"""K 线数据加载 — CSV 标准库 + 可选 Parquet（pyarrow）。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Sequence, Tuple

from .models import Bar


def bars_from_rows(rows: Sequence[Tuple[float, float, float, float]]) -> List[Bar]:
    bars: List[Bar] = []
    for i, (o, h, l, c) in enumerate(rows):
        bars.append(Bar(index=i, open=o, high=h, low=l, close=c))
    return bars


def _parse_row(row: dict, index: int) -> Bar:
    return Bar(
        index=index,
        open=float(row.get("open", row.get("Open", 0))),
        high=float(row["high"] if "high" in row else row["High"]),
        low=float(row["low"] if "low" in row else row["Low"]),
        close=float(row["close"] if "close" in row else row["Close"]),
        volume=float(row.get("volume", row.get("Volume", 0)) or 0),
    )


def load_csv(path: str | Path) -> List[Bar]:
    """流式读取 CSV（逐行，避免重复缓冲）。"""
    path = Path(path)
    bars: List[Bar] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            bars.append(_parse_row(row, i))
    return bars


def load_parquet(path: str | Path) -> List[Bar]:
    """读取 Parquet artifact（需要 pyarrow）。"""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("pyarrow required for parquet: pip install pyarrow") from exc

    table = pq.read_table(str(path))
    cols = {name: table.column(name).to_pylist() for name in table.column_names}
    n = len(table)
    index_col = cols.get("index") or list(range(n))
    volume_col = cols.get("volume") or [0.0] * n
    bars: List[Bar] = []
    for i in range(n):
        bars.append(
            Bar(
                index=int(index_col[i]),
                open=float(cols["open"][i]),
                high=float(cols["high"][i]),
                low=float(cols["low"][i]),
                close=float(cols["close"][i]),
                volume=float(volume_col[i]),
            )
        )
    return bars


def load_market(path: str | Path) -> List[Bar]:
    """按扩展名自动选择 CSV / Parquet。"""
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        return load_parquet(path)
    return load_csv(path)


def save_csv(bars: List[Bar], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for b in bars:
            writer.writerow(
                {
                    "index": b.index,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
            )


def save_parquet(bars: List[Bar], path: str | Path) -> None:
    """写入 Parquet artifact（需要 pyarrow）。"""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("pyarrow required for parquet: pip install pyarrow") from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "index": [b.index for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    pq.write_table(table, str(path))


def save_market(bars: List[Bar], path: str | Path, prefer_parquet: bool = True) -> str:
    """保存 artifact，优先 parquet（失败则回退 csv）。返回实际路径。"""
    path = Path(path)
    if prefer_parquet:
        pq_path = path if path.suffix == ".parquet" else path.with_suffix(".parquet")
        try:
            save_parquet(bars, pq_path)
            return str(pq_path)
        except ImportError:
            pass
    csv_path = path if path.suffix == ".csv" else path.with_suffix(".csv")
    save_csv(bars, csv_path)
    return str(csv_path)
