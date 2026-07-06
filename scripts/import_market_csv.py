#!/usr/bin/env python3
"""导入外部百万级 CSV 到 data/ 目录（列名标准化）。"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def normalize(src: Path, dst: Path) -> int:
    with src.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("empty csv")
        field_map = {k.lower(): k for k in reader.fieldnames}
        required = ["open", "high", "low", "close"]
        for r in required:
            if r not in field_map and r.capitalize() not in reader.fieldnames:
                raise ValueError(f"missing column: {r}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with dst.open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            for i, row in enumerate(reader):
                def g(name: str) -> str:
                    if name in row:
                        return row[name]
                    for k, v in row.items():
                        if k.lower() == name:
                            return v
                    return "0"

                writer.writerow(
                    {
                        "timestamp": g("timestamp") or g("time") or str(i),
                        "open": g("open"),
                        "high": g("high"),
                        "low": g("low"),
                        "close": g("close"),
                        "volume": g("volume") or "0",
                    }
                )
                count += 1
    return count


def main() -> None:
    p = argparse.ArgumentParser(description="Import external market CSV")
    p.add_argument("source", help="path to external csv")
    p.add_argument("-o", "--output", default="data/BTCUSDT_5m.csv")
    p.add_argument("--copy-only", action="store_true", help="copy without rewrite")
    args = p.parse_args()

    src = Path(args.source)
    dst = Path(args.output)
    if args.copy_only:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied -> {dst}")
        return

    n = normalize(src, dst)
    print(f"imported {n} rows -> {dst.resolve()}")


if __name__ == "__main__":
    main()
