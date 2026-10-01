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


# ── MT5 匯出的 K 線（檢視 → 商品 → K 線 → 匯出）──
def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 1 and raw[1:2] == b"\x00"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def timeframe_label(index: pd.DatetimeIndex) -> str:
    """從 K 棒間隔推算週期（M1 / M5 / M15 / M30 / H1 / H4 / D1 / W1）。"""
    if len(index) < 3:
        return "?"
    step = pd.Series(index).diff().dropna().median()
    mins = step.total_seconds() / 60
    for m, name in [(1, "M1"), (5, "M5"), (15, "M15"), (30, "M30"), (60, "H1"), (240, "H4"), (1440, "D1"), (10080, "W1")]:
        if mins <= m * 1.01:
            return name
    return "MN1"


def parse_bars(raw: bytes, filename: str = "") -> tuple[pd.DataFrame, str, str]:
    """讀 MT5 匯出的 K 線 CSV（也接受一般的 Date,Time,Open,High,Low,Close 格式）。
    回傳（OHLCV, 商品名稱, 週期）。商品名稱取自檔名底線前面那段，例如 EURUSD_H1_….csv → EURUSD。"""
    import io

    text = _decode(raw)
    first = text.splitlines()[0] if text else ""
    sep = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep)
    df.columns = [str(c).strip().strip("<>").strip().lower() for c in df.columns]
    if "date" not in df.columns:
        raise ValueError("找不到日期欄位。請用 MT5「商品 → K 線 → 匯出」產生的檔案。")
    stamp = df["date"].astype(str) + (" " + df["time"].astype(str) if "time" in df.columns else "")
    idx = pd.to_datetime(stamp.str.replace(".", "-", regex=False), errors="coerce")
    need = {"open": "Open", "high": "High", "low": "Low", "close": "Close"}
    missing = [k for k in need if k not in df.columns]
    if missing:
        raise ValueError(f"缺少欄位：{', '.join(missing)}")
    out = pd.DataFrame({v: pd.to_numeric(df[k], errors="coerce").values for k, v in need.items()}, index=idx)
    vol = next((c for c in ["tickvol", "vol", "volume"] if c in df.columns), None)
    out["Volume"] = pd.to_numeric(df[vol], errors="coerce").fillna(0).values if vol else 0.0
    if "spread" in df.columns:
        out["Spread"] = pd.to_numeric(df["spread"], errors="coerce").values
    out = out[out.index.notna()].dropna(subset=["Open", "High", "Low", "Close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.index.name = None
    if out.empty:
        raise ValueError("檔案裡沒有可用的 K 線。")
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
    symbol = stem.split("_")[0] or "上傳資料"
    return out, symbol, timeframe_label(out.index)
