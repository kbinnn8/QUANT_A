"""可信度檢驗：這個回測結果有多少是運氣？

- 蒙地卡羅：把交易重新抽樣 / 打亂上千次，看淨值、回撤可能的範圍
- 移除最佳交易：拿掉最賺的幾筆，策略還賺錢嗎？
- 成本敏感度：成本增加多少，策略就會開始虧錢？
- 滾動指標：勝率、獲利因子是否隨時間衰退
- Deflated Sharpe Ratio：把「試了幾次」考慮進去後，Sharpe 還剩多少可信度（Bailey & López de Prado）
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
EULER = 0.5772156649


# ── 蒙地卡羅 ──
def _max_dd_pct(paths: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(paths, axis=1)
    return (paths / peak - 1).min(axis=1)


def monte_carlo(pnl: np.ndarray, cash: float, n: int = 1000, seed: int = 7) -> dict:
    """pnl：每筆交易損益（金額）。回傳兩種模擬：
    - bootstrap（有放回抽樣）：交易組成會變 → 看最終損益的可能範圍
    - shuffle（只打亂順序）：最終損益不變 → 看「只是運氣順序不同」時回撤會差多少
    """
    pnl = np.asarray(pnl, dtype=float)
    k = len(pnl)
    rng = np.random.default_rng(seed)
    boot = rng.choice(pnl, size=(n, k), replace=True)
    boot_paths = cash + np.cumsum(boot, axis=1)
    shuf = np.array([rng.permutation(pnl) for _ in range(n)])
    shuf_paths = cash + np.cumsum(shuf, axis=1)
    start = np.full((n, 1), cash)
    boot_paths = np.hstack([start, boot_paths])
    shuf_paths = np.hstack([start, shuf_paths])
    actual = np.concatenate([[cash], cash + np.cumsum(pnl)])
    q = [5, 25, 50, 75, 95]
    return dict(
        bands=np.percentile(boot_paths, q, axis=0), q=q, actual=actual,
        final=boot_paths[:, -1], dd_boot=_max_dd_pct(boot_paths), dd_shuffle=_max_dd_pct(shuf_paths),
        actual_dd=float(_max_dd_pct(actual[None, :])[0]),
        p_loss=float((boot_paths[:, -1] < cash).mean()),
        sample_paths=shuf_paths[:40],
    )


# ── 移除最佳交易 ──
def remove_top(pnl: np.ndarray, counts=(0, 1, 3, 5, 10)) -> pd.DataFrame:
    pnl = np.sort(np.asarray(pnl, dtype=float))[::-1]
    rows = []
    for c in counts:
        if c > len(pnl):
            break
        rest = pnl[c:]
        rows.append(dict(移除=c, 淨利=float(rest.sum()), 剩餘筆數=len(rest)))
    return pd.DataFrame(rows)


def profit_concentration(pnl: np.ndarray) -> float:
    """最賺的 10% 交易貢獻了多少比例的淨利（淨利 ≤ 0 時回傳 NaN）。"""
    pnl = np.sort(np.asarray(pnl, dtype=float))[::-1]
    total = pnl.sum()
    if total <= 0 or len(pnl) == 0:
        return float("nan")
    k = max(1, int(round(len(pnl) * 0.1)))
    return float(pnl[:k].sum() / total)


# ── 成本敏感度 ──
def cost_sensitivity(trades: pd.DataFrame, extra_bps=None) -> tuple[pd.DataFrame, float]:
    """每一邊多付 X bp（進場 + 出場各一次，按成交金額計）後的淨利。回傳（表, 損益兩平的額外成本 bp）。"""
    if extra_bps is None:
        extra_bps = [0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30]
    if "名目金額" in trades and trades["名目金額"].notna().all():
        # MT5：EA 已經用帳戶幣別算好名目金額（USD/JPY 這類報價幣別不同的商品也正確）
        notional = 2 * trades["名目金額"].to_numpy(float)
    else:
        qty = trades["數量"].to_numpy(float)
        notional = qty * (trades["進場價"].to_numpy(float) + trades["出場價"].to_numpy(float))
    base = float(trades["損益"].sum())
    per_bp = float(notional.sum()) / 1e4
    rows = [dict(額外成本bp=b, 淨利=base - b * per_bp) for b in extra_bps]
    breakeven = base / per_bp if per_bp > 0 and base > 0 else 0.0
    return pd.DataFrame(rows), float(breakeven)


# ── 滾動指標 ──
def rolling_stats(trades: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    t = trades.sort_values("出場時間").reset_index(drop=True)
    pnl = t["損益"]
    win = (pnl > 0).astype(float).rolling(window).mean()
    gp = pnl.clip(lower=0).rolling(window).sum()
    gl = (-pnl.clip(upper=0)).rolling(window).sum()
    pf = (gp / gl.replace(0, np.nan)).clip(upper=10)
    return pd.DataFrame({"時間": t["出場時間"], "滾動勝率": win, "滾動獲利因子": pf,
                         "滾動平均損益": pnl.rolling(window).mean()})


# ── Deflated Sharpe Ratio ──
def _moments(r: np.ndarray) -> tuple[float, float, float]:
    r = r[np.isfinite(r)]
    mu, sd = r.mean(), r.std(ddof=1)
    if sd == 0:
        return 0.0, 0.0, 3.0
    z = (r - mu) / sd
    return float(mu / sd), float((z ** 3).mean()), float((z ** 4).mean())


def psr(sr: float, sr_bench: float, n: int, skew: float, kurt: float) -> float:
    """機率型 Sharpe：真實 Sharpe 大於 sr_bench 的機率（sr 為每期、未年化）。"""
    if n < 3:
        return float("nan")
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return float("nan")
    return float(_N.cdf((sr - sr_bench) * math.sqrt(n - 1) / math.sqrt(denom)))


def expected_max_sr(sr_std: float, n_trials: int) -> float:
    """在「所有策略其實都沒有優勢」的假設下，試 n_trials 次所期待的最大 Sharpe（每期）。"""
    if n_trials <= 1 or sr_std <= 0:
        return 0.0
    a = _N.inv_cdf(1 - 1 / n_trials)
    b = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return float(sr_std * ((1 - EULER) * a + EULER * b))


def deflated_sharpe(daily_returns: pd.Series, n_trials: int, trial_srs_daily: list[float] | None = None) -> dict:
    """回傳 PSR（對 0）與 DSR（對「試 n 次的期待最大值」），皆為機率 0–1。
    trial_srs_daily：同一個 EA 其他嘗試的每日 Sharpe，用來估計 Sharpe 的變異；不足時用理論近似。"""
    r = np.asarray(daily_returns, dtype=float)
    n = int(np.isfinite(r).sum())
    sr, skew, kurt = _moments(r)
    if trial_srs_daily and len(trial_srs_daily) >= 3:
        sr_std = float(np.std(trial_srs_daily, ddof=1))
    else:
        sr_std = math.sqrt(1 / max(n - 1, 1))          # 單一 Sharpe 估計的標準誤（近似）
    bench = expected_max_sr(sr_std, n_trials)
    return dict(sr_daily=sr, n=n, skew=skew, kurt=kurt, trials=n_trials, sr_bench=bench,
                psr=psr(sr, 0.0, n, skew, kurt), dsr=psr(sr, bench, n, skew, kurt))
