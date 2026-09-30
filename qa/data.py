"""抓 K 線（Yahoo Finance）。快速測試用；MT5 的資料則來自回測報告或 EA 輸出。"""
from __future__ import annotations

import datetime as dt

import pandas as pd

# Yahoo 對分鐘 / 小時線有歷史長度限制（天）
INTERVAL_LIMIT_DAYS = {"1m": 7, "5m": 59, "15m": 59, "30m": 59, "1h": 729}


def _one(ticker: str, start, end, interval: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, interval=interval, auto_adjust=True,
                      progress=False, threads=False)
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):     # 新版 yfinance 單一標的也回傳 (欄位, 代號)
        raw = raw.xs(ticker, axis=1, level=-1) if ticker in raw.columns.get_level_values(-1) \
            else raw.droplevel(-1, axis=1)
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
    df = raw[cols].copy()
    if "Volume" not in df:
        df["Volume"] = 0.0
    idx = pd.to_datetime(df.index)
    df.index = idx.tz_localize(None) if idx.tz is not None else idx
    df.index.name = None
    return df.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()


def load_ohlcv(ticker: str, start, end, interval: str = "1d") -> tuple[pd.DataFrame, str]:
    """回傳（OHLCV, 實際代號）。台股數字代號自動判斷上市 / 上櫃；分鐘線自動縮短起始日。"""
    if interval in INTERVAL_LIMIT_DAYS:
        earliest = dt.date.today() - dt.timedelta(days=INTERVAL_LIMIT_DAYS[interval])
        start = max(pd.Timestamp(start).date(), earliest)
    t = ticker.strip().upper()
    candidates = [f"{t}.TW", f"{t}.TWO"] if t.isdigit() else [t]
    for sym in candidates:
        df = _one(sym, start, end, interval)
        if not df.empty:
            return df, sym
    return pd.DataFrame(), candidates[0]
