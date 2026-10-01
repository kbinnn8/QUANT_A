"""回測分析：單一回測的完整報告，每張圖都附「怎麼看」。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import report, robust
from . import charts as C
from . import state as S
from . import theme as T


def render():
    lib = S.library()
    if not lib:
        st.markdown(T.header("回測分析"), unsafe_allow_html=True)
        st.markdown(T.empty("還沒有回測可以分析", "在 MT5 跑一次單次測試，或在「研究紀錄」上傳 .json 紀錄檔。"), unsafe_allow_html=True)
        return
    ids = list(lib)
    active = st.session_state.get("active_run")
    idx = ids.index(active) if active in ids else 0
    rid = st.selectbox("選擇回測", ids, index=idx, format_func=lambda i: lib[i].label, key="analysis_pick",
                       label_visibility="collapsed")
    st.session_state["active_run"] = rid
    run = lib[rid]
    s = S.stats_of(run)

    st.markdown(T.header(run.name, tag="MT5" if run.source == "mt5" else "Python"), unsafe_allow_html=True)
    st.markdown(T.chips([(("MT5" if run.source == "mt5" else "Python"), f"src-{run.source}"),
                         run.ea, run.symbol, run.timeframe, run.period, f"{s.get('K棒數', len(run.equity)):,} 根 K 棒"] +
                        [f"{k}={v}" for k, v in run.params.items()]), unsafe_allow_html=True)
    if run.note:
        st.markdown(f'<div class="hint"><b>備註</b>：{T.esc(run.note)}</div>', unsafe_allow_html=True)
    if run.lookahead is not None:
        ok, bad = run.lookahead
        st.markdown(T.status("ok", "前視偏差檢查通過：截斷未來資料重跑，每一根的下單都相同") if ok else
                    T.status("bad", f"前視偏差檢查失敗：{bad} 根 K 棒的下單在截斷未來資料後改變了，策略可能偷看了未來"),
                    unsafe_allow_html=True)

    tabs = st.tabs(["總覽", "淨值與回撤", "交易分析", "可信度檢驗", "交易明細"])
    with tabs[0]:
        overview(run, s)
    with tabs[1]:
        equity_tab(run, s)
    with tabs[2]:
        trades_tab(run, s)
    with tabs[3]:
        robustness_tab(run, s, lib)
    with tabs[4]:
        trade_list(run)


# ───────────────────────── 總覽 ─────────────────────────
def overview(run, s):
    g = s.get
    bh = g("買進持有報酬")
    st.markdown(T.kpi_cards([
        dict(label="淨利", value=S.money(g("淨利")), delta=f"總報酬 {S.pct(g('總報酬'))}", trend=S.sign(g("淨利"))),
        dict(label="年化報酬", value=S.pct(g("年化報酬")),
             delta=f"買進持有 {S.pct(bh)}" if bh is not None else None,
             trend=S.sign(g("總報酬") - bh) if bh is not None else None),
        dict(label="獲利因子", value=S.num(g("獲利因子")), delta=f"期望收益 {S.money(g('期望收益'))} / 筆"),
        dict(label="Sharpe", value=S.num(g("Sharpe")), delta=f"Sortino {S.num(g('Sortino'))}"),
        dict(label="最大回撤", value=S.pct(g("最大回撤")), delta=S.money(g("最大回撤金額"))),
        dict(label="交易次數", value=f"{g('交易次數', 0)}", delta=f"勝率 {S.pct(g('勝率'))}"),
    ]), unsafe_allow_html=True)
    st.markdown(T.report_table([
        ("收益", [
            ("初始資金", S.money(run.cash)), ("最終淨值", S.money(g("最終淨值"))),
            ("淨利", S.money(g("淨利")), S.sign(g("淨利"))), ("毛利 / 毛損", f"{S.money(g('毛利'))} / {S.money(g('毛損'))}"),
            ("總報酬", S.pct(g("總報酬")), S.sign(g("總報酬"))), ("年化報酬", S.pct(g("年化報酬"))),
            ("買進持有", S.pct(bh)), ("總手續費", S.money(g("總手續費"))),
        ]),
        ("風險", [
            ("淨值最大回撤", f"{S.money(g('最大回撤金額'))}（{S.pct(g('最大回撤'))}）"),
            ("餘額最大回撤", f"{S.money(g('餘額最大回撤金額'))}（{S.pct(g('餘額最大回撤'))}）"),
            ("最長回撤（日曆天）", f"{g('最長回撤天數', 0)}"), ("年化波動", S.pct(g("年化波動"))),
            ("Sharpe / Sortino", f"{S.num(g('Sharpe'))} / {S.num(g('Sortino'))}"), ("Calmar", S.num(g("Calmar"))),
            ("回復因子", S.num(g("回復因子"))),
        ]),
        ("交易", [
            ("交易次數", f"{g('交易次數', 0)}"),
            ("勝率", S.pct(g("勝率"))),
            ("多單（勝率）", f"{g('多單次數', 0)}（{S.pct(g('多單勝率'), 0)}）"),
            ("空單（勝率）", f"{g('空單次數', 0)}（{S.pct(g('空單勝率'), 0)}）"),
            ("平均獲利 / 平均虧損", f"{S.money(g('平均獲利'))} / {S.money(g('平均虧損'))}"),
            ("盈虧比", S.num(g("盈虧比"))), ("最大單筆獲利 / 虧損", f"{S.money(g('最大單筆獲利'))} / {S.money(g('最大單筆虧損'))}"),
            ("最多連續獲利 / 虧損", f"{g('最大連續獲利次數', 0)} / {g('最大連續虧損次數', 0)} 筆"),
        ]),
        ("統計", [
            ("Z 分數（信賴度）", f"{S.num(g('Z 分數'))}（{S.pct(g('Z 信賴度'), 0)}）"),
            ("AHPR / GHPR", f"{S.num(g('AHPR'), 4)} / {S.num(g('GHPR'), 4)}"),
            ("LR 相關係數", S.num(g("LR 相關係數"))), ("SQN", S.num(g("SQN"))),
            ("平均持有", report._fmt_td(g("平均持有時間"))),
        ]),
    ]), unsafe_allow_html=True)
    st.markdown(T.explain(
        "先看三件事：<b>獲利因子</b>（毛利 ÷ 毛損，1.3 以上才比較有餘裕扣掉實盤的額外成本）、"
        "<b>最大回撤</b>（你實際要忍受的最痛時刻）、<b>交易次數</b>（少於 30 筆，任何統計都很不穩）。"
        "年化報酬輸給買進持有並不代表策略沒用，如果它的回撤小很多，風險調整後可能更好，這時看 Sharpe 比較公平。"),
        unsafe_allow_html=True)


# ───────────────────────── 淨值與回撤 ─────────────────────────
def equity_tab(run, s):
    if run.ohlc is not None and len(run.ohlc):
        st.plotly_chart(C.price_trades(run), theme=None)
        st.markdown(T.explain("▲ / ▼ 是進場、✕ 是出場，綠色虛線是賺錢的交易、紅色是賠錢的。"
                              "看看虧損的單集中在什麼行情：盤整？急跌？這通常是改進策略的第一個線索。"),
                    unsafe_allow_html=True)
    st.plotly_chart(C.equity(run), theme=None)
    st.markdown(T.explain(
        "<b>餘額</b>只在平倉時變動，<b>淨值</b>含未平倉損益。兩條線差很多，代表持倉期間的浮動損益很大，"
        "例如常常先大幅浮虧再轉賺。理想的曲線是穩定向右上，而不是靠一兩次大跳升。"), unsafe_allow_html=True)
    st.plotly_chart(C.drawdown(run.equity), theme=None)
    st.markdown(T.explain(
        f"每個時間點離淨值高點跌了多少。最深 {S.pct(s.get('最大回撤'))}，最長花了 {s.get('最長回撤天數', 0)} 天才回到高點。"
        "問自己：實盤時如果連續幾個月都在這個坑裡，你會不會中途放棄？"), unsafe_allow_html=True)
    mt = report.monthly_returns(run.equity)
    st.markdown(T.section("月報酬"), unsafe_allow_html=True)
    st.plotly_chart(C.monthly(mt), theme=None)
    st.markdown(T.explain("綠色賺、紅色賠。好的策略各年份都有不少綠格；如果利潤全集中在某一年，要懷疑是不是剛好碰上特殊行情。"),
                unsafe_allow_html=True)


# ───────────────────────── 交易分析 ─────────────────────────
def trades_tab(run, s):
    t = run.trades
    if t.empty:
        st.info("沒有交易。")
        return
    st.plotly_chart(C.trade_bars(t), theme=None)
    won = (t["損益"] > 0).to_numpy()
    text = [f"第 {k + 1} 筆 · {r['方向']}單 · 報酬 {r['報酬率']:.2%}" for k, r in t.reset_index(drop=True).iterrows()]
    if {"最大有利波動", "最大不利波動"} <= set(t.columns) and t["最大有利波動"].notna().any():
        c1, c2 = st.columns(2)
        c1.plotly_chart(C.scatter(t["最大有利波動"], t["報酬率"], won, text, "MFE：最大浮盈 vs 最終報酬",
                                  "持有期間最大浮盈", "最終報酬", ".0%"), theme=None)
        c2.plotly_chart(C.scatter(t["最大不利波動"], t["報酬率"], won, text, "MAE：最大浮虧 vs 最終報酬",
                                  "持有期間最大浮虧", "最終報酬", ".0%"), theme=None)
        st.markdown(T.explain(
            "<b>MFE 圖</b>：右下角的紅點代表「曾經大賺、最後卻虧錢」的單，數量多的話，可以考慮停利或移動停損。"
            "<b>MAE 圖</b>：看綠點（最後賺錢的單）的最大浮虧通常不超過多少，停損設在那附近，就能砍掉壞單而不誤殺好單。"),
            unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if "持有K棒" in t and t["持有K棒"].notna().any():
        c1.plotly_chart(C.scatter(t["持有K棒"], t["報酬率"], won, text, "持有時間 vs 報酬", "持有 K 棒數", "報酬"),
                        theme=None)
    c2.plotly_chart(C.histogram(t["報酬率"] * 100, "每筆報酬分布", "報酬（%）"), theme=None)
    st.markdown(T.explain(
        "左圖：虧損的單是不是都抱很久？如果是，可以加上「時間停損」。右圖：理想的分布是右尾比左尾長，"
        "也就是小虧多次、偶爾大賺（趨勢策略），或大多小賺、偶爾小虧（均值回歸）。如果左尾很長，代表偶爾會有大虧。"),
        unsafe_allow_html=True)

    et = pd.to_datetime(t["進場時間"])
    intraday = (et.dt.hour != 0).any()
    if intraday:
        st.plotly_chart(C.hour_weekday(t), theme=None)
        st.markdown(T.explain(
            "外匯最有用的一張圖。亞洲盤（台灣時間早上）、倫敦盤（下午到晚上）、紐約盤（晚上到凌晨）的特性很不一樣，"
            "常會發現策略只在某些時段賺錢，其他時段一直在送錢。注意時間是資料本身的時區（MT5 通常是券商伺服器時間）。"),
            unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(C.grouped(t, et.dt.weekday, C.WEEKDAYS, "依進場星期：損益合計"), theme=None)
    c2.plotly_chart(C.grouped(t, et.dt.month - 1, [f"{m}月" for m in range(1, 13)], "依進場月份：損益合計"), theme=None)
    if "商品" in t and t["商品"].nunique() > 1:
        g = t.groupby("商品")["損益"]
        gp = g.apply(lambda v: v[v > 0].sum())
        gl = g.apply(lambda v: -v[v < 0].sum())
        st.markdown(T.section("依商品"), unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({"筆數": g.count(), "損益合計": g.sum().map(S.money), "平均損益": g.mean().map(S.money),
                                   "勝率": g.apply(lambda v: (v > 0).mean()).map(S.pct),
                                   "獲利因子": (gp / gl.where(gl > 0)).map(S.num)}).sort_values("筆數", ascending=False))
        st.markdown(T.explain(
            "一籃子測試時，看優勢是不是「大部分商品都有」。如果只有一兩個商品賺錢、其他都虧，"
            "比較像是運氣或那個商品剛好的行情，不是策略本身的優勢。"), unsafe_allow_html=True)
    if "出場原因" in t and t["出場原因"].notna().any():
        g = t.groupby("出場原因")["損益"]
        st.markdown(T.section("依出場原因"), unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({"筆數": g.count(), "損益合計": g.sum().map(S.money),
                                   "平均損益": g.mean().map(S.money), "勝率": g.apply(lambda v: (v > 0).mean()).map(S.pct)}))


# ───────────────────────── 可信度檢驗 ─────────────────────────
def robustness_tab(run, s, lib):
    t = run.trades
    if len(t) < 5:
        st.info("交易太少（少於 5 筆），可信度檢驗沒有意義。")
        return
    pnl = t["損益"].to_numpy(float)
    mc = robust.monte_carlo(pnl, run.cash)
    dd95 = float(np.percentile(mc["dd_shuffle"], 5))
    same_ea = [r for r in lib.values() if r.ea == run.ea]
    srs = []
    for r in same_ea:
        dr = report.daily_returns(r.equity)
        if len(dr) > 2 and dr.std(ddof=1) > 0:
            srs.append(float(dr.mean() / dr.std(ddof=1)))
    d = robust.deflated_sharpe(report.daily_returns(run.equity), len(same_ea), srs)
    conc = robust.profit_concentration(pnl)
    cs, be = robust.cost_sensitivity(t)
    st.markdown(T.kpi_cards([
        dict(label="虧錢機率（重抽樣）", value=S.pct(mc["p_loss"], 0)),
        dict(label="最差 5% 的回撤", value=S.pct(dd95), delta=f"實際 {S.pct(mc['actual_dd'])}"),
        dict(label="前 10% 交易貢獻", value=S.pct(conc, 0), delta="佔淨利"),
        dict(label="成本兩平點", value=f"{be:.1f} bp" if be > 0 else "—", delta="每邊可多承受"),
        dict(label="DSR", value=S.pct(d["dsr"], 0), delta=f"同 EA 試了 {len(same_ea)} 次"),
    ]), unsafe_allow_html=True)

    st.plotly_chart(C.mc_fan(mc), theme=None)
    st.markdown(T.explain(
        f"把你的 {len(pnl)} 筆交易重新抽樣 1,000 次，畫出可能的淨值路徑。藍色帶是 50% 和 90% 的範圍，橘線是實際結果。"
        f"有 <b>{S.pct(mc['p_loss'], 0)}</b> 的模擬最後是虧錢的。這個比例越高，代表目前的獲利越可能只是運氣好。"),
        unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(C.dd_hist(mc), theme=None)
    c1.markdown(T.explain(
        f"同樣的交易，只是順序不同，最大回撤就可能從很淺變成很深。最差 5% 的情況是 <b>{S.pct(dd95)}</b>。"
        "實盤時你遇到的順序是隨機的，資金和心理準備應該以這個數字為準，而不是回測報告上那一個。"), unsafe_allow_html=True)
    rt = robust.remove_top(pnl)
    c2.plotly_chart(C.remove_top_bars(rt), theme=None)
    c2.markdown(T.explain(
        f"最賺的 10% 交易貢獻了 <b>{S.pct(conc, 0)}</b> 的淨利。如果拿掉前幾筆就轉虧，代表策略靠少數大單撐起來，"
        "那幾筆沒出現（或實盤剛好錯過）結果就完全不同。這種策略很脆弱。"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(C.cost_line(cs, be), theme=None)
    c1.markdown(T.explain(
        "如果實際成本比回測假設的高（點差變寬、滑價），淨利會掉多少？損益兩平點越小越危險。外匯短線策略的兩平點"
        "如果只有 1–2 bp，一遇到新聞時段的點差就可能整個虧掉。（近似值：假設部位大小不變）"), unsafe_allow_html=True)
    win = min(20, max(5, len(t) // 5))
    rs = robust.rolling_stats(t, win).dropna()
    if len(rs):
        c2.plotly_chart(C.rolling(rs, s.get("勝率", 0)), theme=None)
        c2.markdown(T.explain(
            f"每 {win} 筆交易算一次勝率和獲利因子。如果越往右越低，代表策略的優勢可能正在消失。市場結構會變，"
            "很多策略只在某段時間有效。"), unsafe_allow_html=True)

    st.markdown(T.section("Sharpe 可信度"), unsafe_allow_html=True)
    st.markdown(T.report_table([("考慮「試了幾次」", [
        ("每日 Sharpe（未年化）", S.num(d["sr_daily"], 4)), ("交易日數", f"{d['n']}"),
        ("偏態 / 峰態", f"{S.num(d['skew'])} / {S.num(d['kurt'])}"),
        ("同 EA 嘗試次數", f"{d['trials']}"), ("試這麼多次的「運氣門檻」", S.num(d["sr_bench"], 4)),
        ("PSR（真實 Sharpe > 0 的機率）", S.pct(d["psr"], 1)),
        ("DSR（扣掉試誤後的機率）", S.pct(d["dsr"], 1), "up" if d["dsr"] >= 0.95 else "down"),
    ])]), unsafe_allow_html=True)
    st.markdown(T.explain(
        "就算策略完全沒有優勢，試了很多組參數後，「最好的那組」Sharpe 也會很漂亮，這就是過擬合。"
        "<b>運氣門檻</b>是「試這麼多次、純靠運氣也能達到的 Sharpe」；DSR 是你的結果超過這個門檻的機率。"
        "DSR 超過 95% 才算有說服力。所以<b>少試、想清楚再試</b>，本身就會讓結果更可信。"), unsafe_allow_html=True)


# ───────────────────────── 交易明細 ─────────────────────────
def trade_list(run):
    t = run.trades
    if t.empty:
        st.info("沒有交易。")
        return
    show = t.copy()
    show.insert(0, "#", range(1, len(show) + 1))
    for c in ["損益", "手續費", "餘額"]:
        if c in show:
            show[c] = show[c].map(S.money)
    for c in ["報酬率", "最大有利波動", "最大不利波動"]:
        if c in show:
            show[c] = show[c].map(lambda v: S.pct(v, 2))
    st.dataframe(show, hide_index=True)
    st.download_button("下載交易明細（CSV）", t.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{run.id}_trades.csv", mime="text/csv")
