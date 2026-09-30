"""共用圖表（全部回傳 plotly Figure，樣式統一由 theme.style 處理）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import theme as T

WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def equity(run, height=380):
    fig = go.Figure()
    if run.ohlc is not None and len(run.ohlc):
        close = run.ohlc["Close"]
        bh = close / close.iloc[0] * run.cash
        fig.add_trace(go.Scatter(x=bh.index, y=bh, name="買進持有", line=dict(color=T.MUTED, width=1.2, dash="dot")))
    fig.add_trace(go.Scatter(x=run.equity.index, y=run.equity, name="淨值（含未平倉）",
                             line=dict(color=T.SERIES[3], width=1.3)))
    bal = run.balance if run.balance is not None else run.derived_balance()
    fig.add_trace(go.Scatter(x=bal.index, y=bal, name="餘額（已平倉）", line=dict(color=T.ACCENT, width=2.2, shape="hv")))
    fig.add_hline(y=run.cash, line_color=T.BORDER, line_dash="dash")
    fig.update_yaxes(tickformat=",.0f")
    return T.style(fig, height, "餘額與淨值")


def drawdown(eq: pd.Series, height=230):
    dd = eq / eq.cummax() - 1
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy", line=dict(color=T.DOWN, width=1.1),
                               fillcolor="rgba(239,83,80,0.16)", hovertemplate="%{y:.2%}<extra></extra>"))
    fig.update_yaxes(tickformat=".0%")
    return T.style(fig, height, "回撤（距離淨值高點）", legend=False)


def price_trades(run, height=560):
    data, trades, inds = run.ohlc, run.trades, run.indicators or []
    sub = [d for d in inds if not d.get("overlay", True)]
    fig = make_subplots(rows=2 if sub else 1, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.72, 0.28] if sub else [1.0])
    x = data.index
    if len(data) <= 3000:
        fig.add_trace(go.Candlestick(x=x, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"],
                                     name="K 線", increasing=dict(line=dict(color=T.UP, width=1), fillcolor=T.UP),
                                     decreasing=dict(line=dict(color=T.DOWN, width=1), fillcolor=T.DOWN)), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=x, y=data["Close"], name="收盤價", line=dict(color=T.TEXT, width=1.1)), row=1, col=1)
    for d, color in zip([d for d in inds if d.get("overlay", True)], T.SERIES):
        fig.add_trace(go.Scatter(x=x, y=d["values"], name=d["name"], line=dict(color=color, width=1.2)), row=1, col=1)
    for d, color in zip(sub, T.SERIES):
        fig.add_trace(go.Scatter(x=x, y=d["values"], name=d["name"], line=dict(color=color, width=1.2)), row=2, col=1)
    if len(trades):
        for won, color, name in [(True, T.UP, "獲利交易"), (False, T.DOWN, "虧損交易")]:
            t = trades[(trades["損益"] > 0) == won]
            xs, ys = [], []
            for _, r in t.iterrows():
                xs += [r["進場時間"], r["出場時間"], None]
                ys += [r["進場價"], r["出場價"], None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=name, hoverinfo="skip",
                                     line=dict(color=color, width=1.4, dash="dot")), row=1, col=1)
        span = float(data["High"].max() - data["Low"].min()) or 1.0
        for side, symbol, color in [("多", "triangle-up", T.UP), ("空", "triangle-down", T.DOWN)]:
            t = trades[trades["方向"] == side]
            if len(t):
                lo = data["Low"].reindex(t["進場時間"], method="nearest").to_numpy()
                hi = data["High"].reindex(t["進場時間"], method="nearest").to_numpy()
                y = lo - span * 0.025 if side == "多" else hi + span * 0.025
                fig.add_trace(go.Scatter(
                    x=t["進場時間"], y=y, mode="markers", name=f"{side}單進場",
                    marker=dict(symbol=symbol, size=12, color=color, line=dict(color=T.BG, width=1)),
                    customdata=np.stack([t["報酬率"] * 100, t["進場價"]], axis=1),
                    hovertemplate=f"{side}單進場 %{{customdata[1]:.5g}}<br>此筆報酬 %{{customdata[0]:.2f}}%<extra></extra>"),
                    row=1, col=1)
        fig.add_trace(go.Scatter(x=trades["出場時間"], y=trades["出場價"], mode="markers", name="出場",
                                 marker=dict(symbol="x-thin", size=9, color=T.INK, line=dict(color=T.INK, width=2)),
                                 customdata=trades["損益"],
                                 hovertemplate="出場 %{y:.5g}<br>損益 %{customdata:,.0f}<extra></extra>"), row=1, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False)
    fig = T.style(fig, height + (100 if sub else 0), "K 線與進出場")
    fig.update_layout(legend=dict(orientation="h", y=-0.06, x=0, xanchor="left", yanchor="top"), margin=dict(b=64))
    return fig


def trade_bars(trades, height=270):
    colors = np.where(trades["損益"] > 0, T.UP, T.DOWN)
    fig = go.Figure(go.Bar(x=np.arange(1, len(trades) + 1), y=trades["損益"], marker_color=colors,
                           marker_line_width=0,
                           customdata=np.stack([trades["方向"], trades["報酬率"] * 100], axis=1),
                           hovertemplate="第 %{x} 筆（%{customdata[0]}）<br>損益 %{y:,.0f}"
                                         "<br>%{customdata[1]:.2f}%<extra></extra>"))
    fig.update_xaxes(title_text="交易序號")
    fig = T.style(fig, height, "每筆交易損益", legend=False)
    fig.update_layout(hovermode="closest", bargap=0.2)
    return fig


def scatter(x, y, won, text, title, xt, yt, xfmt=None, yfmt=".1%", height=330):
    fig = go.Figure()
    for flag, color, name in [(True, T.UP, "獲利"), (False, T.DOWN, "虧損")]:
        m = won == flag
        fig.add_trace(go.Scatter(x=np.asarray(x)[m], y=np.asarray(y)[m], mode="markers", name=name,
                                 text=np.asarray(text)[m], hovertemplate="%{text}<extra></extra>",
                                 marker=dict(size=8, color=color, opacity=0.85, line=dict(color=T.PANEL, width=1))))
    fig.add_hline(y=0, line_color=T.BORDER)
    fig.update_xaxes(title_text=xt, tickformat=xfmt)
    fig.update_yaxes(title_text=yt, tickformat=yfmt)
    fig = T.style(fig, height, title)
    fig.update_layout(hovermode="closest")
    return fig


def histogram(values, title, xt, height=330):
    fig = go.Figure(go.Histogram(x=values, nbinsx=30, marker_color=T.ACCENT, marker_line_width=0, opacity=0.9,
                                 hovertemplate="%{x}：%{y} 筆<extra></extra>"))
    fig.add_vline(x=0, line_color=T.MUTED, line_dash="dash")
    fig.update_xaxes(title_text=xt)
    fig = T.style(fig, height, title, legend=False)
    fig.update_layout(hovermode="closest", bargap=0.06)
    return fig


def grouped(trades, keys, labels, title, height=270):
    g = trades.assign(_k=keys).groupby("_k")["損益"].agg(["sum", "count"]).reindex(range(len(labels))).fillna(0)
    fig = go.Figure(go.Bar(x=labels, y=g["sum"], marker_color=np.where(g["sum"] >= 0, T.UP, T.DOWN),
                           marker_line_width=0, customdata=g["count"],
                           hovertemplate="%{x}：損益 %{y:,.0f}（%{customdata:.0f} 筆）<extra></extra>"))
    fig = T.style(fig, height, title, legend=False)
    fig.update_layout(hovermode="closest", bargap=0.3)
    return fig


def hour_weekday(trades, height=330):
    et = pd.to_datetime(trades["進場時間"])
    pv = trades.assign(h=et.dt.hour, w=et.dt.weekday).pivot_table(index="w", columns="h", values="損益",
                                                                  aggfunc="sum").reindex(index=range(7), columns=range(24))
    z = pv.to_numpy(float)
    fin = z[np.isfinite(z)]
    lim = float(np.abs(fin).max()) if fin.size else 1.0
    fig = go.Figure(go.Heatmap(z=z, x=[f"{h:02d}" for h in range(24)], y=WEEKDAYS, colorscale=T.DIVERGING,
                               zmid=0, zmin=-lim, zmax=lim, xgap=2, ygap=2, showscale=False,
                               hovertemplate="%{y} %{x} 時：損益 %{z:,.0f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, title_text="進場時段（資料時區）")
    fig = T.style(fig, height, "星期 × 時段：損益合計", legend=False)
    fig.update_layout(hovermode="closest")
    return fig


def monthly(table: pd.DataFrame):
    z = table.to_numpy(dtype=float)
    fin = z[np.isfinite(z)]
    lim = float(np.abs(fin).max()) if fin.size else 0.01
    text = np.where(np.isnan(z), "", np.char.mod("%.1f%%", np.nan_to_num(z) * 100))
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{m}月" for m in range(1, 13)] + ["全年"], y=[str(y) for y in table.index],
        colorscale=T.DIVERGING, zmid=0, zmin=-lim, zmax=lim, text=text, texttemplate="%{text}",
        textfont=dict(family="JetBrains Mono, monospace", color=T.INK, size=11), xgap=2, ygap=2,
        hovertemplate="%{y} %{x}：%{z:.2%}<extra></extra>", showscale=False))
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    fig = T.style(fig, 80 + 34 * len(table), None, legend=False)
    fig.update_layout(hovermode="closest")
    return fig


def mc_fan(mc: dict, height=400):
    b, x = mc["bands"], np.arange(mc["bands"].shape[1])
    fig = go.Figure()
    for path in mc["sample_paths"]:
        fig.add_trace(go.Scatter(x=x, y=path, mode="lines", line=dict(color="rgba(120,123,134,0.18)", width=1),
                                 hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[b[4], b[0][::-1]], fill="toself",
                             fillcolor="rgba(41,98,255,0.10)", line=dict(width=0), name="90% 範圍", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[b[3], b[1][::-1]], fill="toself",
                             fillcolor="rgba(41,98,255,0.22)", line=dict(width=0), name="50% 範圍", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=b[2], name="中位數", line=dict(color=T.ACCENT, width=1.5, dash="dash")))
    fig.add_trace(go.Scatter(x=x, y=mc["actual"], name="實際結果", line=dict(color=T.WARN, width=2.4)))
    fig.update_xaxes(title_text="交易筆數")
    fig.update_yaxes(tickformat=",.0f")
    return T.style(fig, height, "蒙地卡羅：1,000 種可能的淨值路徑")


def dd_hist(mc: dict, height=320):
    fig = go.Figure(go.Histogram(x=mc["dd_shuffle"] * 100, nbinsx=40, marker_color=T.DOWN, marker_line_width=0,
                                 opacity=0.8, hovertemplate="回撤 %{x:.1f}%：%{y} 次<extra></extra>", name="模擬"))
    fig.add_vline(x=mc["actual_dd"] * 100, line_color=T.WARN, line_width=2,
                  annotation_text="實際", annotation_font=dict(color=T.WARN))
    p95 = float(np.percentile(mc["dd_shuffle"], 5) * 100)
    fig.add_vline(x=p95, line_color=T.MUTED, line_dash="dash",
                  annotation_text="最差 5%", annotation_font=dict(color=T.MUTED), annotation_position="top left")
    fig.update_xaxes(title_text="最大回撤（%）")
    fig = T.style(fig, height, "只打亂交易順序：最大回撤的分布", legend=False)
    fig.update_layout(hovermode="closest", bargap=0.05)
    return fig


def remove_top_bars(df: pd.DataFrame, height=300):
    fig = go.Figure(go.Bar(x=[f"拿掉前 {k} 筆" if k else "原始" for k in df["移除"]], y=df["淨利"],
                           marker_color=np.where(df["淨利"] >= 0, T.UP, T.DOWN), marker_line_width=0,
                           hovertemplate="%{x}：淨利 %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line_color=T.MUTED)
    fig = T.style(fig, height, "拿掉最賺的交易後，還剩多少淨利", legend=False)
    fig.update_layout(hovermode="closest", bargap=0.35)
    return fig


def cost_line(df: pd.DataFrame, breakeven: float, height=300):
    fig = go.Figure(go.Scatter(x=df["額外成本bp"], y=df["淨利"], mode="lines+markers",
                               line=dict(color=T.ACCENT, width=2), marker=dict(size=7),
                               hovertemplate="每邊多 %{x} bp：淨利 %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line_color=T.MUTED)
    if breakeven > 0:
        fig.add_vline(x=breakeven, line_color=T.WARN, line_dash="dash",
                      annotation_text=f"損益兩平 ≈ {breakeven:.1f} bp", annotation_font=dict(color=T.WARN))
    fig.update_xaxes(title_text="每一邊額外成本（bp）")
    fig.update_yaxes(tickformat=",.0f")
    fig = T.style(fig, height, "成本敏感度", legend=False)
    fig.update_layout(hovermode="closest")
    return fig


def rolling(df: pd.DataFrame, overall_wr: float, height=300):
    fig = make_subplots(rows=1, cols=2, subplot_titles=("滾動勝率", "滾動獲利因子"), horizontal_spacing=0.08)
    fig.add_trace(go.Scatter(x=df["時間"], y=df["滾動勝率"], line=dict(color=T.ACCENT, width=1.8), name="勝率",
                             hovertemplate="%{y:.0%}<extra></extra>"), row=1, col=1)
    fig.add_hline(y=overall_wr, line_color=T.MUTED, line_dash="dash", row=1, col=1)
    fig.add_trace(go.Scatter(x=df["時間"], y=df["滾動獲利因子"], line=dict(color=T.SERIES[1], width=1.8),
                             name="獲利因子", hovertemplate="%{y:.2f}<extra></extra>"), row=1, col=2)
    fig.add_hline(y=1, line_color=T.MUTED, line_dash="dash", row=1, col=2)
    fig.update_yaxes(tickformat=".0%", row=1, col=1)
    fig = T.style(fig, height, None, legend=False)
    fig.update_annotations(font=dict(color=T.INK, size=12))
    fig.update_layout(margin=dict(t=36))
    return fig


def compare_equity(runs_: list, mode: str, height=420):
    fig = go.Figure()
    for r, color in zip(runs_, T.SERIES):
        eq = r.equity
        y = (eq / eq.iloc[0] - 1) if mode == "報酬率" else eq
        fig.add_trace(go.Scatter(x=eq.index, y=y, name=r.name, line=dict(color=color, width=1.8)))
    fig.update_yaxes(tickformat=".0%" if mode == "報酬率" else ",.0f")
    return T.style(fig, height, "淨值比較" + ("（起點 = 0%）" if mode == "報酬率" else ""))


def compare_dd(runs_: list, height=260):
    fig = go.Figure()
    for r, color in zip(runs_, T.SERIES):
        dd = r.equity / r.equity.cummax() - 1
        fig.add_trace(go.Scatter(x=dd.index, y=dd, name=r.name, line=dict(color=color, width=1.4)))
    fig.update_yaxes(tickformat=".0%")
    return T.style(fig, height, "回撤比較")
