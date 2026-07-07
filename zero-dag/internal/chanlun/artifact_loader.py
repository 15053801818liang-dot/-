"""myth002 ↔ czsc 桥接层 — DataFrame → RawBar 格式转换"""
import pandas as pd
from czsc import RawBar, Freq


def load_market_data(path: str) -> pd.DataFrame:
    """从 artifact 路径加载 K 线数据，支持 parquet/csv/json"""
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    elif path.endswith(".csv"):
        df = pd.read_csv(path)
        # 标准化列名
        col_map = {
            "timestamp": "dt", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "vol",
        }
        df.rename(columns={v: k for k, v in col_map.items() if v in df.columns}, inplace=True)
        return df
    elif path.endswith(".json"):
        return pd.read_json(path)
    else:
        raise ValueError(f"unsupported format: {path}")


def to_raw_bars(df: pd.DataFrame, freq: str = "5min") -> list:
    """将标准 K 线 DataFrame 转为 czsc 的 RawBar 列表"""
    df = df.copy()
    # 确保列名符合 RawBar 格式
    required = ["dt", "open", "high", "low", "close", "vol"]
    for col in required:
        if col not in df.columns:
            df[col] = 0

    # 按时间排序
    if "dt" in df.columns:
        df = df.sort_values("dt")

    freq_map = {"1min": Freq.F1, "5min": Freq.F5, "15min": Freq.F15,
                "30min": Freq.F30, "60min": Freq.F60, "1h": Freq.F60,
                "4h": Freq.F240, "1d": Freq.D, "1w": Freq.W}
    czsc_freq = freq_map.get(freq, Freq.F5)

    bars = []
    for _, row in df.iterrows():
        bar = RawBar(
            symbol="BTCUSDT",
            id=len(bars),
            dt=row["dt"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row.get("vol", 0),
            amount=row.get("amount", row.get("vol", 0) * row["close"]),
            freq=czsc_freq,
        )
        bars.append(bar)
    return bars


def debug_artifact(path: str) -> dict:
    """快速诊断 artifact 文件格式"""
    import os
    if not os.path.exists(path):
        return {"exists": False, "path": path}
    df = load_market_data(path)
    cols = list(df.columns)
    dtypes = {c: str(df[c].dtype) for c in cols}
    return {
        "exists": True,
        "path": path,
        "rows": len(df),
        "columns": cols,
        "dtypes": dtypes,
        "head": df.head(3).to_dict(orient="records"),
        "date_range": f"{df['dt'].min()} → {df['dt'].max()}" if "dt" in df.columns else "N/A",
    }
