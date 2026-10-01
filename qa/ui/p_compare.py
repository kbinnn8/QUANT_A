"""比較：多次回測並排。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import charts as C
from . import state as S
from . import theme as T

METRICS = [  # (名稱, key, 格式, 越大越好?)
    ("淨利", "淨利", "money", True), ("總報酬", "總報酬", "pct", True), ("年化報酬", "年化報酬", "pct", True),
    ("Sharpe", "Sharpe", "num", True), ("Sortino", "Sortino", "num", True), ("最大回撤", "最大回撤", "pct", True),
    ("獲利因子", "獲利因子", "num", True), ("回復因子", "回復因子", "num", True), ("勝率", "勝率", "pct", True),
    ("交易次數", "交易次數", "int", None), ("平均每筆報酬", "平均每筆報酬", "pct2", True),
    ("最長回撤天數", "最長回撤天數", "int", False),
]


def render():
    st.markdown(T.header("多筆比較", "對照實驗、換商品、換參數：多筆回測並排，差在哪裡一眼看出來。"), unsafe_allow_html=True)
    lib = S.library()
    if len(lib) < 2:
        st.markdown(T.empty("至少需要兩筆回測", "在 MT5 多跑幾次，結果上傳後就能並排比較。"), unsafe_allow_html=True)
        return
    default = [i for i in st.session_state.get("compare_ids", []) if i in lib] or list(lib)[:2]
    ids = st.multiselect("選擇要比較的回測（最多 8 筆）", list(lib), default=default, max_selections=8,
                         format_func=lambda i: lib[i].label, key="compare_pick")
    st.session_state["compare_ids"] = ids
    if len(ids) < 2:
        st.info("請至少選兩筆。")
        return
    runs_ = [lib[i] for i in ids]
    stats = [S.stats_of(r) for r in runs_]

    rows = {}
    for label, key, fmt, higher in METRICS:
        vals = [s.get(key) for s in stats]
        rows[label] = [fmt_val(v, fmt) for v in vals]
        valid = [(k, v) for k, v in enumerate(vals) if v is not None and pd.notna(v)]
        if higher is not None and len(valid) >= 2:
            best = max(valid, key=lambda kv: kv[1] if higher else -kv[1])[0]
            rows[label][best] = "★ " + rows[label][best]
    names = [f"{k + 1}. {r.name}" for k, r in enumerate(runs_)]
    table = pd.DataFrame(rows, index=names).T
    st.dataframe(table)
    st.markdown('<div class="hint">★ 標示各指標最好的一筆（最大回撤以「跌最少」為最好）。</div>', unsafe_allow_html=True)

    params = pd.DataFrame([r.params for r in runs_], index=names).T
    if not params.empty:
        st.markdown(T.section("參數差異"), unsafe_allow_html=True)
        diff = params[params.nunique(axis=1) > 1] if len(params.columns) > 1 else params
        st.dataframe(diff.astype(str) if not diff.empty else params.astype(str))

    mode = st.segmented_control("淨值顯示", ["報酬率", "金額"], default="報酬率", key="compare_mode") or "報酬率"
    st.plotly_chart(C.compare_equity(runs_, mode), theme=None)
    st.plotly_chart(C.compare_dd(runs_), theme=None)
    st.markdown(T.explain(
        "比較時注意兩件事：<b>期間要一樣</b>（不同期間的市場環境不同，比較沒有意義），以及<b>不要只挑最好的那一筆</b>。"
        "如果改一點參數結果就差很多，代表策略對參數很敏感，實盤時很容易失效；幾組參數都差不多好，反而比較可靠。"),
        unsafe_allow_html=True)


def fmt_val(v, fmt):
    if fmt == "money":
        return S.money(v)
    if fmt == "pct":
        return S.pct(v)
    if fmt == "pct2":
        return S.pct(v, 2)
    if fmt == "int":
        return "—" if v is None or pd.isna(v) else f"{int(v)}"
    return S.num(v)
