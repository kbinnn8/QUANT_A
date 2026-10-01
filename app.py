"""QUANT_A：MT5 EA 的研究紀錄、改良前後對比與視覺化（回測在 MT5 跑）。

本機執行：streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from qa.ui import p_analysis, p_chart, p_compare, p_docs, p_improve, p_runs
from qa.ui import state as S
from qa.ui import theme as T

st.set_page_config(page_title="QUANT_A", page_icon=":material/monitoring:", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(T.CSS, unsafe_allow_html=True)


def password_gate():
    """在 Streamlit 的 Secrets 設定 APP_PASSWORD 就會要求密碼（回測紀錄屬於私人資料）。"""
    try:
        pw = st.secrets.get("APP_PASSWORD")
    except Exception:
        pw = None
    if not pw or st.session_state.get("authed"):
        return
    st.markdown(T.header("QUANT_A"), unsafe_allow_html=True)
    typed = st.text_input("密碼", type="password")
    if typed and typed == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif typed:
        st.error("密碼錯誤")
    st.stop()


password_gate()

pages = {
    "研究紀錄": st.Page(p_runs.render, title="研究紀錄", icon=":material/list_alt:", url_path="runs", default=True),
    "回測分析": st.Page(p_analysis.render, title="回測分析", icon=":material/insights:", url_path="analysis"),
    "改良對比": st.Page(p_improve.render, title="改良對比", icon=":material/difference:", url_path="improve"),
    "比較": st.Page(p_compare.render, title="多筆比較", icon=":material/compare_arrows:", url_path="compare"),
    "圖表": st.Page(p_chart.render, title="圖表", icon=":material/candlestick_chart:", url_path="chart"),
    "說明": st.Page(p_docs.render, title="說明", icon=":material/menu_book:", url_path="docs"),
}
S.PAGES.update(pages)

try:
    nav = st.navigation(list(pages.values()), position="top")
except TypeError:            # 舊版 Streamlit 沒有頂部導覽：退回側欄
    nav = st.navigation(list(pages.values()))
nav.run()
