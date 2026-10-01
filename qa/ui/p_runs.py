"""研究紀錄：所有回測的總表，依 EA 統計嘗試次數。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import report, robust
from .. import runs as R
from . import charts as C
from . import state as S
from . import theme as T


def render():
    st.markdown(T.header("研究紀錄", "每一次 MT5 回測都會自動留在這裡：EA 改了什麼、結果變好還是變差，一目了然。"),
                unsafe_allow_html=True)
    lib = S.library()

    with st.expander("上傳回測紀錄（.json）", expanded=not lib):
        ups = st.file_uploader("回測紀錄檔", type=["json"], accept_multiple_files=True, label_visibility="collapsed",
                               key="runs_upload")
        if ups:
            added = 0
            for f in ups:
                try:
                    S.add_run(R.Run.from_json(f.getvalue().decode("utf-8")))
                    added += 1
                except Exception as e:
                    st.error(f"{f.name}：無法讀取（{e}）")
            if added:
                st.success(f"已加入 {added} 筆。")
                lib = S.library()
        st.markdown('<div class="hint">之後 MT5 回測完會自動上傳到 GitHub 的 runs/ 資料夾，這裡就會直接看到，不用手動上傳。</div>',
                    unsafe_allow_html=True)

    if not lib:
        st.markdown(T.empty("還沒有任何回測紀錄",
                            "在 MT5 策略測試器跑一次（單次測試），上傳小工具會自動把結果送到這裡。也可以手動上傳 .json 紀錄檔。"),
                    unsafe_allow_html=True)
        return

    rows = []
    for r in lib.values():
        s = S.stats_of(r)
        rows.append({"id": r.id, "時間": r.created[:16].replace("T", " "), "來源": "MT5" if r.source == "mt5" else "Python",
                     "EA": r.ea, "標的": r.symbol, "週期": r.timeframe, "期間": r.period,
                     "淨利": s.get("淨利"), "總報酬": s.get("總報酬"), "Sharpe": s.get("Sharpe"), "最大回撤": s.get("最大回撤"),
                     "獲利因子": s.get("獲利因子"), "交易數": s.get("交易次數", 0),
                     "備註": r.note or "",
                     "參數": ", ".join(f"{k}={v}" for k, v in r.params.items()),
                     "保存": "永久" if r.persisted else "這次連線"})
    df = pd.DataFrame(rows)

    n_ea = df["EA"].nunique()
    st.markdown(T.kpi_cards([
        dict(label="回測總數", value=f"{len(df)}"),
        dict(label="EA / 策略數", value=f"{n_ea}"),
        dict(label="MT5 / Python", value=f"{(df['來源'] == 'MT5').sum()} / {(df['來源'] == 'Python').sum()}"),
        dict(label="最近一次", value=df["時間"].iloc[0][5:], delta=df["EA"].iloc[0]),
    ]), unsafe_allow_html=True)

    st.markdown(T.section("全部回測"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 2, 1])
    ea_pick = c1.multiselect("EA", sorted(df["EA"].unique()), placeholder="全部 EA", key="runs_ea")
    sym_pick = c2.multiselect("標的", sorted(df["標的"].unique()), placeholder="全部標的", key="runs_sym")
    src_pick = c3.selectbox("來源", ["全部", "MT5", "Python"], key="runs_src")
    view = df.copy()
    if ea_pick:
        view = view[view["EA"].isin(ea_pick)]
    if sym_pick:
        view = view[view["標的"].isin(sym_pick)]
    if src_pick != "全部":
        view = view[view["來源"] == src_pick]

    show = view.drop(columns=["id"]).copy()
    show["淨利"] = show["淨利"].map(S.money)
    show["總報酬"] = show["總報酬"].map(S.pct)
    show["最大回撤"] = show["最大回撤"].map(S.pct)
    show["Sharpe"] = show["Sharpe"].map(S.num)
    show["獲利因子"] = show["獲利因子"].map(S.num)
    event = st.dataframe(show, hide_index=True, on_select="rerun", selection_mode="multi-row", key="runs_table")
    picked = [view["id"].iloc[i] for i in (event.selection.rows if event and event.selection else [])]

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    if c1.button("分析", type="primary", disabled=len(picked) != 1, help="勾選一筆後按這裡"):
        S.open_run(picked[0])
    if c2.button("改良對比", disabled=len(picked) != 2, help="勾選兩筆：較早的當舊版、較新的當新版"):
        pair = sorted(picked, key=lambda i: lib[i].created)
        S.improve(pair[0], pair[1])
    if c3.button("多筆比較", disabled=len(picked) < 2, help="勾選 2–8 筆後按這裡"):
        S.compare(picked[:8])
    if picked and len(picked) == 1:
        r = lib[picked[0]]
        c4.download_button("下載這筆紀錄（.json）", r.to_json().encode("utf-8"), file_name=f"{r.id}.json",
                           mime="application/json")
    st.markdown('<div class="hint">在表格左側勾選：勾一筆可以分析；勾兩筆可以做改良前後對比；勾更多筆可以並排比較。</div>',
                unsafe_allow_html=True)

    # ── 依 EA 統計：試了幾次 ──
    st.markdown(T.section("依 EA 統計"), unsafe_allow_html=True)
    ea_rows = []
    for ea, g in df.groupby("EA"):
        best = g.loc[g["Sharpe"].astype(float).idxmax()] if g["Sharpe"].notna().any() else g.iloc[0]
        srs = []
        for rid in g["id"]:
            dr = report.daily_returns(lib[rid].equity)
            if len(dr) > 2 and dr.std(ddof=1) > 0:
                srs.append(float(dr.mean() / dr.std(ddof=1)))
        best_run = lib[best["id"]]
        d = robust.deflated_sharpe(report.daily_returns(best_run.equity), len(g), srs)
        ea_rows.append({"EA": ea, "嘗試次數": len(g), "標的數": g["標的"].nunique(),
                        "最佳 Sharpe": S.num(best["Sharpe"]), "最佳那次": best["時間"],
                        "只看最佳（PSR）": S.pct(d["psr"], 0), "考慮試了幾次（DSR）": S.pct(d["dsr"], 0)})
    st.dataframe(pd.DataFrame(ea_rows), hide_index=True)
    st.markdown(T.explain(
        "同一個 EA 試越多次，「最好的那次」就越可能只是運氣。<b>PSR</b> 是只看最佳那次時，它的真實 Sharpe 大於 0 的機率；"
        "<b>DSR</b>（Deflated Sharpe Ratio）把「試了幾次」考慮進去後的機率。兩者差很多，代表好結果有不少是試出來的。"
        "一般會希望 DSR 超過 95% 才算有說服力。"), unsafe_allow_html=True)

    # ── 版本演進：同一個 EA 一路改下來，數字怎麼變 ──
    st.markdown(T.section("版本演進"), unsafe_allow_html=True)
    c1, c2 = st.columns([2, 2])
    eas = sorted(df["EA"].unique())
    ea_one = c1.selectbox("EA", eas, key="evo_ea")
    metric = c2.selectbox("指標", list(EVO_METRICS), key="evo_metric")
    key, fmt = EVO_METRICS[metric]
    g = df[df["EA"] == ea_one].copy()
    if len(g) < 2:
        st.markdown('<div class="hint">這個 EA 目前只有一筆紀錄。每改一次就在 MT5 再跑一次，這裡會畫出一路的變化。</div>',
                    unsafe_allow_html=True)
    else:
        g["值"] = [S.stats_of(lib[i]).get(key) for i in g["id"]]
        g["名稱"] = [lib[i].name for i in g["id"]]
        g["時間"] = pd.to_datetime(g["時間"])
        st.plotly_chart(C.evolution(g, metric, fmt), theme=None)
        st.markdown(T.explain(
            "每個點是一次回測，依時間排列，滑鼠移上去可以看名稱和備註。不同顏色是不同商品。"
            "只有在<b>同一個商品、同一段期間</b>上比較才有意義；某一次突然特別好，先到「改良對比」確認是不是運氣。"),
            unsafe_allow_html=True)


EVO_METRICS = {"獲利因子": ("獲利因子", "num"), "淨利": ("淨利", "money"), "最大回撤": ("最大回撤", "pct"),
               "Sharpe": ("Sharpe", "num"), "勝率": ("勝率", "pct"), "交易次數": ("交易次數", "int"),
               "每筆期望收益": ("期望收益", "money")}
