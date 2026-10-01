"""改良前後對比：選一筆舊版、一筆新版，看哪裡變好、哪裡變差、改善是不是真的。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import improve as I
from . import charts as C
from . import state as S
from . import theme as T


def _defaults(lib: dict) -> tuple[str, str]:
    saved = st.session_state.get("improve_ids") or []
    if len(saved) == 2 and all(i in lib for i in saved):
        return saved[0], saved[1]
    ids = list(lib)                                   # 新 → 舊
    new = ids[0]
    same = [i for i in ids[1:] if lib[i].ea == lib[new].ea and lib[i].symbol == lib[new].symbol]
    old = same[0] if same else ids[1]
    return old, new


def _fmt(v, fmt):
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return "—"
    if fmt == "money":
        return S.money(v)
    if fmt == "pct":
        return S.pct(v)
    if fmt == "int":
        return f"{int(v)}"
    return S.num(v)


def _delta(a, b, fmt):
    if any(x is None or pd.isna(x) for x in (a, b)):
        return "—", None
    d = float(b) - float(a)
    if fmt == "pct":
        txt = f"{d * 100:+.1f} 個百分點"
    elif fmt == "money":
        txt = f"{d:+,.0f}"
    elif fmt == "int":
        txt = f"{d:+.0f}"
    else:
        txt = f"{d:+.2f}"
    return txt, d


def render():
    st.markdown(T.header("改良前後對比", "選一筆舊版、一筆新版：哪裡變好、哪裡變差、改善是真的還是運氣。"),
                unsafe_allow_html=True)
    lib = S.library()
    if len(lib) < 2:
        st.markdown(T.empty("至少需要兩筆回測", "在 MT5 跑完改良前、改良後各一次，結果上傳後就能在這裡對比。"),
                    unsafe_allow_html=True)
        return

    ids = list(lib)
    old0, new0 = _defaults(lib)
    c1, c2 = st.columns(2)
    old_id = c1.selectbox("舊版（改良前）", ids, index=ids.index(old0), format_func=lambda i: lib[i].label, key="imp_old")
    new_id = c2.selectbox("新版（改良後）", ids, index=ids.index(new0), format_func=lambda i: lib[i].label, key="imp_new")
    st.session_state["improve_ids"] = [old_id, new_id]
    if old_id == new_id:
        st.info("請選兩筆不同的回測。")
        return
    a, b = lib[old_id], lib[new_id]
    sa, sb = S.stats_of(a), S.stats_of(b)

    issues = I.same_setup(a, b)
    if issues:
        st.markdown(T.status("warn", "測試條件不一樣：" + "、".join(issues) + "。數字差異可能來自條件不同，不一定是 EA 改良的效果。"),
                    unsafe_allow_html=True)
    else:
        st.markdown(T.status("ok", f"測試條件相同：{a.symbol} · {a.timeframe} · {a.period}"), unsafe_allow_html=True)

    # ── 改了什麼 ──
    st.markdown(T.section("改了什麼"), unsafe_allow_html=True)
    notes = [(n, r.note) for n, r in (("舊版", a), ("新版", b)) if r.note]
    for who, note in notes:
        st.markdown(f'<div class="hint"><b>{who}備註</b>：{T.esc(note)}</div>', unsafe_allow_html=True)
    pdiff = I.param_diff(a.params, b.params)
    if not pdiff.empty:
        st.dataframe(pdiff.astype(str), hide_index=True)
    else:
        st.markdown('<div class="hint">參數完全一樣：差異來自 EA 程式本身的修改（或測試設定）。'
                    '建議在 EA 的「備註」參數寫下這次改了什麼，紀錄裡就看得到。</div>', unsafe_allow_html=True)

    # ── 數字變化 ──
    st.markdown(T.section("數字變化"), unsafe_allow_html=True)
    cards = []
    for label, key, fmt, higher in I.METRICS[:5]:
        txt, d = _delta(sa.get(key), sb.get(key), fmt)
        trend = None if d is None or d == 0 or higher is None else ("up" if (d > 0) == higher else "down")
        cards.append(dict(label=label, value=_fmt(sb.get(key), fmt), delta=f"{txt}（舊 {_fmt(sa.get(key), fmt)}）",
                          trend=trend))
    st.markdown(T.kpi_cards(cards), unsafe_allow_html=True)
    rows_better, rows_worse, rows_same = [], [], []
    for label, key, fmt, higher in I.METRICS:
        txt, d = _delta(sa.get(key), sb.get(key), fmt)
        row = (label, f"{_fmt(sa.get(key), fmt)} → {_fmt(sb.get(key), fmt)}（{txt}）")
        if d is None or d == 0 or higher is None:
            rows_same.append((*row, None))
        elif (d > 0) == higher:
            rows_better.append((*row, "up"))
        else:
            rows_worse.append((*row, "down"))
    sections = [(f"變好（{len(rows_better)}）", rows_better or [("—", "", None)]),
                (f"變差（{len(rows_worse)}）", rows_worse or [("—", "", None)])]
    if rows_same:
        sections.append(("其他", rows_same))
    st.markdown(T.report_table(sections), unsafe_allow_html=True)

    # ── 差異從哪裡來 ──
    m = I.match(a.trades, b.trades)
    st.markdown(T.section("差異從哪裡來"), unsafe_allow_html=True)
    rem, add, com_o, com_n = m["removed"], m["added"], m["common_old"], m["common_new"]

    def win(t):
        return S.pct((t["損益"] > 0).mean()) if len(t) else "—"

    st.markdown(T.kpi_cards([
        dict(label="被濾掉的單（只在舊版）", value=f"{len(rem)} 筆", delta=f"合計 {S.money(rem['損益'].sum())} · 勝率 {win(rem)}",
             trend=S.sign(-rem["損益"].sum()) if len(rem) else None),
        dict(label="新增的單（只在新版）", value=f"{len(add)} 筆", delta=f"合計 {S.money(add['損益'].sum())} · 勝率 {win(add)}",
             trend=S.sign(add["損益"].sum()) if len(add) else None),
        dict(label="兩版都有的單", value=f"{len(com_n)} 筆",
             delta=f"出場不同造成 {com_n['損益'].sum() - com_o['損益'].sum():+,.0f}",
             trend=S.sign(com_n["損益"].sum() - com_o["損益"].sum())),
    ]), unsafe_allow_html=True)
    st.plotly_chart(C.waterfall(I.waterfall(m)), theme=None)
    st.markdown(T.explain(
        "用進場時間把兩版的單配對。<b>被濾掉的單</b>合計是負的，代表新的條件擋掉了壞單；是正的，代表把好單也擋掉了。"
        "<b>兩版都有的單</b>如果損益不同，是停損、停利或出場規則改變造成的。"
        "部位大小會隨淨值變化，所以同一筆單在兩版的金額可能略有不同。"), unsafe_allow_html=True)

    # ── 改善是真的嗎 ──
    st.markdown(T.section("改善是真的嗎"), unsafe_allow_html=True)
    if I.is_filter(m):
        ft = I.filter_test(a.trades, rem)
        if np.isnan(ft["p"]):
            st.markdown(T.status("warn", "交易太少，沒辦法判斷。"), unsafe_allow_html=True)
        else:
            p = ft["p"]
            extra = f"（另外新增 {len(add)} 筆，多半是舊版當時正在持倉、新版空手才進的單，不列入這個檢定）" if len(add) else ""
            msg = (f"新版像是加了過濾條件：從舊版的 {ft['n']} 筆裡拿掉 {ft['k']} 筆{extra}。"
                   f"如果隨機拿掉同樣多筆，有 {p:.0%} 的機率結果會一樣好或更好。")
            kind = "ok" if p < 0.05 else "warn" if p < 0.2 else "bad"
            verdict = ("這個過濾條件很可能真的有用。" if p < 0.05 else
                       "有一點跡象，但還不夠確定，需要更多資料（更長期間或更多商品）。" if p < 0.2 else
                       "跟隨機拿掉差不多，這個條件可能只是在減少交易次數。")
            st.markdown(T.status(kind, msg + verdict), unsafe_allow_html=True)
            st.markdown(T.explain(
                f"被濾掉的單平均每筆 {S.pct(ft['removed_mean'], 2)}，留下的平均每筆 {S.pct(ft['kept_mean'], 2)}"
                f"（舊版全部平均 {S.pct(ft['all_mean'], 2)}，以佔帳戶的比例計）。"
                "這叫<b>置換檢定</b>：好的過濾條件應該專門擋掉壞單，效果要明顯好過「隨便拿掉幾筆」。"
                "一般用 5% 當門檻。"), unsafe_allow_html=True)
    else:
        bt = I.bootstrap_better(a.trades, b.trades)
        if np.isnan(bt["prob"]):
            st.markdown(T.status("warn", "交易太少，沒辦法判斷。"), unsafe_allow_html=True)
        else:
            p = bt["prob"]
            kind = "ok" if p >= 0.95 else "warn" if p >= 0.8 else "bad"
            verdict = ("新版每筆的平均表現很可能真的比較好。" if p >= 0.95 else
                       "新版可能比較好，但還不夠確定。" if p >= 0.8 else
                       "看不出新版比較好，差異在運氣的範圍內。")
            st.markdown(T.status(kind, f"把兩版的交易各自重新抽樣 5,000 次，新版每筆平均報酬較高的機率是 {p:.0%}。" + verdict),
                        unsafe_allow_html=True)
            st.markdown(T.explain(
                f"每筆平均（佔帳戶）：舊版 {S.pct(bt['old_mean'], 2)}、新版 {S.pct(bt['new_mean'], 2)}。"
                "這叫 <b>bootstrap</b>：把交易當成樣本反覆重抽，看差異會不會因為抽到不同的單就消失。一般要 95% 以上才算有把握。"),
                unsafe_allow_html=True)

    # ── 圖 ──
    st.markdown(T.section("圖表"), unsafe_allow_html=True)
    names = ["舊版", "新版"]
    a2, b2 = _renamed(a, "舊版"), _renamed(b, "新版")
    mode = st.segmented_control("淨值顯示", ["報酬率", "金額"], default="報酬率", key="imp_mode") or "報酬率"
    st.plotly_chart(C.compare_equity([a2, b2], mode), theme=None)
    st.plotly_chart(C.compare_dd([a2, b2]), theme=None)
    c1, c2 = st.columns(2)
    c1.plotly_chart(C.yearly_compare(I.yearly(a.trades), I.yearly(b.trades), names), theme=None)
    c2.plotly_chart(C.dist_compare(I.acct_returns(a.trades), I.acct_returns(b.trades), names), theme=None)
    st.markdown(T.explain(
        "<b>每年損益</b>：好的改良應該大部分年份都變好，而不是只靠某一年特別好。"
        "<b>每筆報酬分布</b>：過濾條件有效時，新版左邊（虧損那側）的柱子會變矮。"), unsafe_allow_html=True)

    c1, c2, _ = st.columns([1, 1, 2])
    if c1.button("分析新版", type="primary"):
        S.open_run(new_id)
    if c2.button("分析舊版"):
        S.open_run(old_id)


class _renamed:
    """畫圖用：只換名字的 Run 代理。"""

    def __init__(self, run, name):
        self._run, self.name = run, name

    def __getattr__(self, k):
        return getattr(self._run, k)
