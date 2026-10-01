"""一籃子回測：同一個策略、同一組參數，分別在多個商品上跑，再把交易和損益合在一起。

就像在 MT5 同一個帳戶開好幾張圖、每張圖掛同一個 EA：每個商品各自按淨值的 risk% 下單，
帳戶損益 = 各商品損益加總。好處是交易筆數多很多，判斷「訊號有沒有用」可靠得多。
"""
from __future__ import annotations

import pandas as pd

from . import engine


def run(cls, datasets: dict[str, pd.DataFrame], params: dict, cash: float, cost_bps: float,
        lookahead: bool = True, **opts) -> dict:
    """datasets：{商品: OHLCV}。回傳和 engine.run 相同格式的 dict（data = None，畫不了單一 K 線）。"""
    eqs, bals, exps, trades, la_ok, la_bad, settings = [], [], [], [], True, 0, {}
    for sym, df in datasets.items():
        res = engine.run(cls, df, params, cash, cost_bps, **opts)
        settings = res.get("settings", settings)
        eqs.append((res["equity"] - cash).rename(sym))
        bals.append((res["balance"] - cash).rename(sym))
        exps.append((res["exposure"].abs() > 0).astype(float).rename(sym))
        t = res["trades"].copy()
        if not t.empty:
            t["商品"] = sym
            trades.append(t)
        if lookahead:
            ok, bad = engine.lookahead_check(cls, df, params, cash, cost_bps, **opts)
            la_ok, la_bad = la_ok and ok, la_bad + bad

    def combine(parts):
        frame = pd.concat(parts, axis=1).sort_index().ffill().fillna(0.0)
        return frame.sum(axis=1)

    equity = (cash + combine(eqs)).rename("淨值")
    balance = (cash + combine(bals)).rename("餘額")
    exposure = (pd.concat(exps, axis=1).sort_index().ffill().fillna(0.0).max(axis=1)).rename("持倉")
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    if not tr.empty:
        tr = tr.sort_values("出場時間", kind="stable").reset_index(drop=True)
        tr["餘額"] = cash + tr["損益"].cumsum()
    out = dict(data=None, equity=equity, balance=balance, exposure=exposure, trades=tr, journal=[], indicators=[],
               orders=[], params=dict(params), cash=cash,
               settings={**settings, "商品數": len(datasets), "商品": "、".join(datasets)})
    if lookahead:
        out["lookahead"] = (la_ok, la_bad)
    return out
