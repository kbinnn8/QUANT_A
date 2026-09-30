"""回測紀錄（Run）：不論來自 MT5 還是 Python 快速測試，都整理成同一種格式。

一筆 Run = 基本資料（EA、標的、週期、參數、設定）＋ 交易紀錄 ＋ 淨值曲線（＋ 選用的餘額、K 線）。
存成一個 JSON 檔：放在 repo 的 runs/ 資料夾就會永久保存，也可以在 app 裡上傳 / 下載。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import report

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"
TRADE_COLS = ["方向", "數量", "進場時間", "進場價", "出場時間", "出場價", "損益", "報酬率", "手續費",
              "持有K棒", "最大有利波動", "最大不利波動", "進場標籤", "出場原因", "餘額"]
MAX_POINTS = 20_000   # 淨值曲線最多存幾個點（太長會抽樣）


@dataclass
class Run:
    id: str
    name: str
    source: str                  # "python" / "mt5"
    ea: str                      # EA / 策略名稱（用來統計同一個 EA 試了幾次）
    symbol: str
    timeframe: str
    cash: float
    equity: pd.Series
    trades: pd.DataFrame
    params: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    created: str = ""
    note: str = ""
    balance: pd.Series | None = None
    exposure: pd.Series | None = None
    ohlc: pd.DataFrame | None = None       # 選用：畫 K 線與進出場用
    indicators: list = field(default_factory=list)
    lookahead: tuple | None = None
    persisted: bool = False                # True = 來自 repo 的 runs/（永久保存）

    # ── 統計 ──
    def stats(self) -> dict:
        close = self.ohlc["Close"] if self.ohlc is not None else None
        s = report.compute(self.equity, self.trades, close, self.exposure, self.cash)
        x = report.extended(dict(equity=self.equity, balance=self.balance if self.balance is not None
                                 else self.derived_balance(), trades=self.trades, cash=self.cash))
        return {**x, **s}

    def derived_balance(self) -> pd.Series:
        """沒有餘額曲線時，用交易紀錄推算（每筆平倉時更新）。"""
        if self.trades.empty:
            return pd.Series(self.cash, index=self.equity.index)
        steps = self.trades.groupby("出場時間")["損益"].sum().cumsum() + self.cash
        return steps.reindex(self.equity.index, method="ffill").fillna(self.cash)

    @property
    def period(self) -> str:
        return f"{self.equity.index[0]:%Y-%m-%d} → {self.equity.index[-1]:%Y-%m-%d}"

    @property
    def label(self) -> str:
        return f"{self.name} · {self.created[:16].replace('T', ' ')}"

    # ── 存取 ──
    def to_json(self) -> str:
        eq = _thin(self.equity)
        d = dict(
            version=1, id=self.id, name=self.name, source=self.source, ea=self.ea, symbol=self.symbol,
            timeframe=self.timeframe, cash=self.cash, params=_plain(self.params), settings=_plain(self.settings),
            created=self.created, note=self.note,
            equity=dict(t=[t.isoformat() for t in eq.index], v=[round(float(v), 6) for v in eq.values]),
            trades=_trades_to_records(self.trades),
        )
        if self.balance is not None:
            b = self.balance.reindex(eq.index, method="ffill")
            d["balance"] = [round(float(v), 6) for v in b.values]
        if self.lookahead is not None:
            d["lookahead"] = list(self.lookahead)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str, persisted: bool = False) -> "Run":
        d = json.loads(text)
        idx = pd.to_datetime(d["equity"]["t"])
        equity = pd.Series(d["equity"]["v"], index=idx, dtype=float, name="淨值")
        balance = pd.Series(d["balance"], index=idx, dtype=float, name="餘額") if d.get("balance") else None
        trades = pd.DataFrame(d.get("trades") or [])
        for c in ["進場時間", "出場時間"]:
            if c in trades:
                trades[c] = pd.to_datetime(trades[c])
        return cls(id=d["id"], name=d.get("name", d["id"]), source=d.get("source", "mt5"), ea=d.get("ea", "未命名"),
                   symbol=d.get("symbol", "?"), timeframe=d.get("timeframe", "?"), cash=float(d.get("cash", equity.iloc[0])),
                   equity=equity, trades=trades, params=d.get("params", {}), settings=d.get("settings", {}),
                   created=d.get("created", ""), note=d.get("note", ""), balance=balance,
                   lookahead=tuple(d["lookahead"]) if d.get("lookahead") else None, persisted=persisted)


def new_id(*parts) -> str:
    now = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    h = hashlib.md5(repr(parts).encode()).hexdigest()[:6]
    return f"{now}-{h}"


def from_engine(res: dict, ea: str, symbol: str, timeframe: str, name: str | None = None) -> Run:
    """把 Python 引擎（engine.run）的結果轉成 Run。"""
    created = dt.datetime.now().isoformat(timespec="seconds")
    return Run(id=new_id(ea, symbol, timeframe, res["params"]), name=name or f"{ea} · {symbol} · {timeframe}",
               source="python", ea=ea, symbol=symbol, timeframe=timeframe, cash=res["cash"],
               equity=res["equity"], trades=res["trades"], params=res["params"], settings=res.get("settings", {}),
               created=created, balance=res.get("balance"), exposure=res.get("exposure"), ohlc=res["data"],
               indicators=res.get("indicators", []), lookahead=res.get("lookahead"))


def load_dir(path: Path = RUNS_DIR) -> list[Run]:
    """讀取 repo 裡 runs/ 資料夾的所有紀錄（壞掉的檔案略過）。"""
    out = []
    if path.exists():
        for f in sorted(path.glob("*.json")):
            try:
                out.append(Run.from_json(f.read_text(encoding="utf-8"), persisted=True))
            except Exception:
                continue
    return out


# ── 工具 ──
def _thin(s: pd.Series) -> pd.Series:
    if len(s) <= MAX_POINTS:
        return s
    step = int(np.ceil(len(s) / MAX_POINTS))
    keep = s.iloc[::step]
    return pd.concat([keep, s.iloc[[-1]]]).loc[lambda x: ~x.index.duplicated(keep="last")]


def _plain(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = float(v)
        elif isinstance(v, (np.bool_,)):
            v = bool(v)
        elif not isinstance(v, (int, float, str, bool, type(None))):
            v = str(v)
        out[k] = v
    return out


def _trades_to_records(t: pd.DataFrame) -> list[dict]:
    if t is None or t.empty:
        return []
    t = t[[c for c in TRADE_COLS if c in t.columns]].copy()
    for c in ["進場時間", "出場時間"]:
        if c in t:
            t[c] = pd.to_datetime(t[c]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    recs = t.to_dict(orient="records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                r[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                r[k] = None if not np.isfinite(v) else round(float(v), 8)
    return recs
