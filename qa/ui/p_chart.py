"""TradingView 圖表（參考用）。"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from . import theme as T

QUICK = {"EUR/USD": "FX:EURUSD", "GBP/USD": "FX:GBPUSD", "USD/JPY": "FX:USDJPY", "AUD/USD": "FX:AUDUSD",
         "黃金": "OANDA:XAUUSD", "白銀": "OANDA:XAGUSD", "美國 500": "OANDA:SPX500USD", "那斯達克 100": "OANDA:NAS100USD",
         "原油（WTI）": "TVC:USOIL", "美元指數": "TVC:DXY", "台股加權": "TWSE:TAIEX", "BTC/USD": "BITSTAMP:BTCUSD"}
INTERVALS = {"1 分": "1", "5 分": "5", "15 分": "15", "30 分": "30", "1 小時": "60", "4 小時": "240", "日": "D", "週": "W"}
STUDIES = {"均線（SMA）": "STD;SMA", "指數均線（EMA）": "STD;EMA", "布林通道": "STD;Bollinger_Bands", "RSI": "STD;RSI",
           "MACD": "STD;MACD", "Awesome Oscillator": "STD;Awesome_Oscillator", "KD": "STD;Stochastic",
           "ATR": "STD;Average_True_Range"}


def widget(symbol: str, interval: str, studies: list[str]) -> str:
    cfg = {"autosize": True, "symbol": symbol, "interval": interval, "timezone": "Asia/Taipei", "theme": "dark",
           "style": "1", "locale": "zh_TW", "backgroundColor": T.BG, "gridColor": "rgba(42,46,57,0.55)",
           "allow_symbol_change": True, "hide_side_toolbar": False, "withdateranges": True, "save_image": True,
           "details": False, "calendar": False, "studies": studies, "support_host": "https://www.tradingview.com"}
    # TradingView 會把容器高度設成 100%，所以 html / body 也必須是 100%，否則圖會縮成 150px
    return f"""
<style>html,body{{margin:0;padding:0;height:100%;background:{T.BG};overflow:hidden;}}
.tradingview-widget-container,.tradingview-widget-container__widget{{height:100%!important;width:100%!important;}}</style>
<div class="tradingview-widget-container"><div class="tradingview-widget-container__widget"></div>
<script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
{json.dumps(cfg)}
</script></div>"""


def render():
    st.markdown(T.header("圖表", "TradingView 即時圖表：左側工具列畫線，上方「指標」加指標。僅供看盤參考。"),
                unsafe_allow_html=True)
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        pick = c1.selectbox("商品", list(QUICK), key="tv_pick")
        custom = c2.text_input("或輸入 TradingView 代號", key="tv_custom", placeholder="例如 OANDA:GBPJPY、TWSE:2330")
        iv = c3.selectbox("週期", list(INTERVALS), index=4, key="tv_iv")
        height = c4.selectbox("高度", [600, 750, 900, 1100], index=2, key="tv_h")
        studies = st.multiselect("預設指標", list(STUDIES), default=["Awesome Oscillator", "RSI"], key="tv_studies")
    symbol = (custom.strip().upper() or QUICK[pick])
    components.html(widget(symbol, INTERVALS[iv], [STUDIES[s] for s in studies]), height=height)
    c1, _ = st.columns([1, 3])
    c1.link_button("在 TradingView 全螢幕開啟 ↗", f"https://www.tradingview.com/chart/?symbol={symbol}")
    st.markdown('<div class="hint">報價來自 TradingView，和 XM / MT5 的報價會有些微差異。免費嵌入版重新整理後畫的線不會保留；'
                '想保留請用上面的按鈕到 TradingView 網站開啟（登入後自動儲存）。</div>', unsafe_allow_html=True)
