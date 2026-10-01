"""改良前後對比：兩筆回測差在哪裡、改善是不是真的。

- match：用（商品, 方向, 進場時間）把兩版的交易配對 → 共同 / 被濾掉 / 新增
- waterfall：舊版淨利 → 拿掉被濾掉的 → 加上新增的 → 共同交易出場不同 → 新版淨利（加總完全對得上）
- 顯著性：
  * 新版只是「少做一些單」（過濾條件）：隨機拿掉同樣多筆，有多少機率比這次好 → 置換檢定
  * 其他改動：兩版每筆報酬重新抽樣，新版平均比舊版好的機率 → bootstrap
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (顯示名稱, stats 的 key, 格式, 越大越好?)；最大回撤是負數，越大（越接近 0）越好
METRICS = [
    ("淨利", "淨利", "money", True),
    ("獲利因子", "獲利因子", "num", True),
    ("勝率", "勝率", "pct", True),
    ("每筆期望收益", "期望收益", "money", True),
    ("交易次數", "交易次數", "int", None),
    ("最大回撤", "最大回撤", "pct", True),
    ("最大回撤金額", "最大回撤金額", "money", True),
    ("Sharpe", "Sharpe", "num", True),
    ("回復因子", "回復因子", "num", True),
    ("盈虧比", "盈虧比", "num", True),
    ("最大連續虧損次數", "最大連續虧損次數", "int", False),
    ("最長回撤天數", "最長回撤天數", "int", False),
]


def trade_key(t: pd.DataFrame) -> pd.Series:
    sym = t["商品"].astype(str) if "商品" in t else pd.Series("", index=t.index)
    when = pd.to_datetime(t["進場時間"]).dt.floor("min").dt.strftime("%Y-%m-%d %H:%M")
    return sym + "|" + t["方向"].astype(str) + "|" + when


def _clean(t) -> pd.DataFrame:
    if t is None or "損益" not in getattr(t, "columns", []):
        return pd.DataFrame({"方向": pd.Series(dtype=str), "進場時間": pd.Series(dtype="datetime64[ns]"),
                             "出場時間": pd.Series(dtype="datetime64[ns]"), "損益": pd.Series(dtype=float)})
    return t


def match(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """回傳 dict(common_old, common_new, removed, added)：四個交易表。"""
    old, new = _clean(old), _clean(new)
    if old.empty or new.empty:
        return dict(common_old=old.iloc[0:0], common_new=new.iloc[0:0], removed=old, added=new)
    ko, kn = trade_key(old), trade_key(new)
    common = set(ko) & set(kn)
    return dict(common_old=old[ko.isin(common)], common_new=new[kn.isin(common)],
                removed=old[~ko.isin(common)], added=new[~kn.isin(common)])


def waterfall(m: dict) -> list[tuple[str, float]]:
    """[(步驟, 金額)]：第一和最後是總額，中間是變化量。"""
    old_total = float(m["common_old"]["損益"].sum() + m["removed"]["損益"].sum())
    new_total = float(m["common_new"]["損益"].sum() + m["added"]["損益"].sum())
    return [
        ("舊版淨利", old_total),
        ("拿掉被濾掉的單", -float(m["removed"]["損益"].sum())),
        ("加上新增的單", float(m["added"]["損益"].sum())),
        ("共同的單出場不同", float(m["common_new"]["損益"].sum() - m["common_old"]["損益"].sum())),
        ("新版淨利", new_total),
    ]


def acct_series(t: pd.DataFrame) -> pd.Series:
    """每筆交易佔帳戶的報酬（損益 ÷ 進場前餘額），和交易表同一個索引；沒有餘額欄位時退回價格報酬率。"""
    if t is None or t.empty:
        return pd.Series(dtype=float)
    if "餘額" in t and t["餘額"].notna().all():
        pnl = t["損益"].astype(float)
        before = t["餘額"].astype(float) - pnl
        if (before > 0).all():
            return pnl / before
        return pnl / float(before.iloc[0]) if before.iloc[0] > 0 else pnl / pnl.abs().mean()   # 帳戶曾經虧到負數
    return t["報酬率"].astype(float)


def acct_returns(t: pd.DataFrame) -> np.ndarray:
    return acct_series(t).dropna().to_numpy(float)


def is_filter(m: dict) -> bool:
    """新版主要是「少做一些單」→ 視為加了過濾條件。
    允許少量新增：舊版當時正在持倉、沒辦法進的單，新版空手時就會進（一次只持有一筆的 EA 很常見）。"""
    n_new = len(m["common_new"]) + len(m["added"])
    n_add, n_rem = len(m["added"]), len(m["removed"])
    return n_rem > 0 and n_add <= max(2, 0.15 * n_new) and n_rem >= 3 * n_add


def filter_test(old: pd.DataFrame, removed: pd.DataFrame, n_sims: int = 5000, seed: int = 7) -> dict:
    """置換檢定：從舊版隨機拿掉同樣多筆，剩下的平均報酬 ≥ 這次的機率（越小越好）。"""
    rs = acct_series(old)
    mask = rs.index.isin(removed.index)
    ok = rs.notna().to_numpy()
    r, mask = rs.to_numpy(float)[ok], mask[ok]
    k, n = int(mask.sum()), len(r)
    if k == 0 or k >= n or n < 10:
        return dict(p=float("nan"), k=k, n=n, kept_mean=float("nan"), removed_mean=float("nan"), all_mean=float("nan"))
    actual = r[~mask].mean()
    rng = np.random.default_rng(seed)
    total = r.sum()
    sims = np.array([(total - r[rng.choice(n, k, replace=False)].sum()) / (n - k) for _ in range(n_sims)])
    return dict(p=float((sims >= actual - 1e-15).mean()), k=k, n=n, kept_mean=float(actual),
                removed_mean=float(r[mask].mean()), all_mean=float(r.mean()))


def bootstrap_better(old: pd.DataFrame, new: pd.DataFrame, n_sims: int = 5000, seed: int = 7) -> dict:
    """新版每筆平均報酬大於舊版的機率（兩邊各自重新抽樣）。"""
    a, b = acct_returns(old), acct_returns(new)
    if len(a) < 5 or len(b) < 5:
        return dict(prob=float("nan"), old_mean=float("nan"), new_mean=float("nan"))
    rng = np.random.default_rng(seed)
    ma = rng.choice(a, size=(n_sims, len(a)), replace=True).mean(axis=1)
    mb = rng.choice(b, size=(n_sims, len(b)), replace=True).mean(axis=1)
    return dict(prob=float((mb > ma).mean()), old_mean=float(a.mean()), new_mean=float(b.mean()))


def yearly(t: pd.DataFrame) -> pd.Series:
    if t is None or t.empty or "損益" not in t:
        return pd.Series(dtype=float)
    years = pd.to_datetime(t["出場時間"]).dt.year.values
    return t["損益"].groupby(years).sum()


def same_setup(a, b) -> list[str]:
    """兩筆回測的測試條件差異（不同就不能直接比）。"""
    issues = []
    if a.symbol != b.symbol:
        issues.append(f"商品不同（{a.symbol} / {b.symbol}）")
    if a.timeframe != b.timeframe:
        issues.append(f"週期不同（{a.timeframe} / {b.timeframe}）")
    tol = pd.Timedelta(days=3)
    if abs(a.equity.index[0] - b.equity.index[0]) > tol or abs(a.equity.index[-1] - b.equity.index[-1]) > tol:
        issues.append(f"期間不同（{a.period} / {b.period}）")
    if abs(float(a.cash) - float(b.cash)) > 1e-6:
        issues.append(f"初始資金不同（{a.cash:,.0f} / {b.cash:,.0f}）")
    return issues


def param_diff(a: dict, b: dict) -> pd.DataFrame:
    keys = list(dict.fromkeys(list(a or {}) + list(b or {})))
    rows = [(k, (a or {}).get(k, "—"), (b or {}).get(k, "—")) for k in keys
            if str((a or {}).get(k, "—")) != str((b or {}).get(k, "—"))]
    return pd.DataFrame(rows, columns=["參數", "舊版", "新版"])
