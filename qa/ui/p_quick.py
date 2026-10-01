"""快速測試：寫 EA 之前，先用 Python 引擎快速驗證想法。結果會加進研究紀錄。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .. import engine
from .. import runs as R
from ..data import INTERVAL_LIMIT_DAYS, load_ohlcv
from ..templates import TEMPLATES, load
from . import state as S
from . import theme as T

INTERVALS = {"日線": "1d", "1 小時": "1h", "30 分": "30m", "15 分": "15m", "5 分": "5m", "週線": "1wk"}
SYMBOLS = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X", "AUD/USD": "AUDUSD=X",
           "黃金（期貨）": "GC=F", "S&P 500": "^GSPC", "SPY": "SPY", "台積電": "2330", "BTC/USD": "BTC-USD"}
MY = "我的策略（上傳）"

API = """
```python
class MyStrategy(Strategy):
    params = {"n": 20, "sl_pct": 0.02}          # 可調參數（會出現在上面的參數區）

    def init(self):                              # 只跑一次：先算指標
        self.ma = self.I(ta.sma(self.close, self.p.n), "MA")

    def next(self):                              # 每根 K 棒收盤後跑一次，下的單在下一根開盤成交
        i = self.i
        if self.is_flat and self.close[i] > self.ma[i]:
            self.buy(sl_pct=self.p.sl_pct)
        elif self.is_long and self.close[i] < self.ma[i]:
            self.close_position("跌破均線")
```
完整寫法請看「說明」頁。
"""


@st.cache_data(ttl=6 * 3600, show_spinner="下載 K 線資料中…", max_entries=64)
def cached_ohlcv(ticker, start, end, interval):
    return load_ohlcv(ticker, start, end, interval)


def code_editor(code: str, key: str) -> str:
    try:
        from streamlit_ace import st_ace
        out = st_ace(value=code, language="python", theme="tomorrow_night", key=key, height=460, font_size=14,
                     tab_size=4, show_gutter=True, wrap=False, auto_update=True)
        return out if out else code
    except Exception:
        return st.text_area("策略程式碼", code, height=460, key=key + "_ta", label_visibility="collapsed")


def on_upload():
    up = st.session_state.get("qt_upload")
    if up is None:
        return
    st.session_state.setdefault("qt_codes", {})[MY] = up.getvalue().decode("utf-8", errors="replace")
    st.session_state.setdefault("qt_ver", {})[MY] = st.session_state.get("qt_ver", {}).get(MY, 0) + 1
    st.session_state["qt_tpl"] = MY


def render():
    st.markdown(T.header("快速測試", "寫 EA 之前，先用 Python 快速驗證想法：幾分鐘內知道值不值得繼續。"),
                unsafe_allow_html=True)
    codes = st.session_state.setdefault("qt_codes", {})
    vers = st.session_state.setdefault("qt_ver", {})
    today = dt.date.today()

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        names = list(TEMPLATES) + ([MY] if MY in codes else [])
        tpl = c1.selectbox("策略", names, key="qt_tpl")
        sym_name = c2.selectbox("標的", list(SYMBOLS) + ["自訂…"], key="qt_sym")
        iv = c3.selectbox("週期", list(INTERVALS), key="qt_iv")
        years = c4.selectbox("期間", ["1 年", "2 年", "5 年", "10 年"], index=2, key="qt_years")
        symbol = SYMBOLS.get(sym_name) or st.text_input("自訂代號（Yahoo 格式）", "EURUSD=X", key="qt_custom",
                                                         help="外匯 EURUSD=X、期貨 GC=F、台股 2330、美股 SPY")
        c1, c2, c3, c4 = st.columns(4)
        cash = c1.number_input("初始資金", min_value=1000.0, value=10_000.0, step=1000.0, format="%.0f", key="qt_cash")
        size = c2.number_input("部位（淨值比例）", min_value=0.01, value=1.0, step=0.1, format="%g", key="qt_size",
                               help="1 = 每筆用 100% 淨值。外匯可以用大於 1 的數字模擬槓桿。")
        comm = c3.number_input("手續費（bp / 邊）", min_value=0.0, value=0.5, step=0.5, format="%g", key="qt_comm",
                               help="1 bp = 0.01%。主要外匯的點差約 0.5–1 bp / 邊；台股約 25–30 bp。")
        slip = c4.number_input("滑價（bp / 邊）", min_value=0.0, value=0.5, step=0.5, format="%g", key="qt_slip")

    interval = INTERVALS[iv]
    start = today - dt.timedelta(days=int(years.split()[0]) * 365)
    if interval in INTERVAL_LIMIT_DAYS:
        st.caption(f"Yahoo 的{iv}最多只有約 {INTERVAL_LIMIT_DAYS[interval]} 天歷史，會自動縮短。"
                   "長期的分鐘資料之後會改用 MT5 匯出。")

    if tpl not in codes:
        codes[tpl] = load(tpl)
    with st.expander("策略程式碼", expanded=False):
        codes[tpl] = code_editor(codes[tpl], key=f"qt_ace::{tpl}::{vers.get(tpl, 0)}")
        b1, b2, b3 = st.columns([1, 1, 2])
        b1.download_button("下載 .py", codes[tpl].encode("utf-8"), file_name=f"{tpl}.py", mime="text/x-python")
        if b2.button("還原範本", disabled=tpl == MY):
            codes[tpl] = load(tpl)
            vers[tpl] = vers.get(tpl, 0) + 1
            st.rerun()
        b3.file_uploader("上傳 .py", type=["py", "txt"], label_visibility="collapsed", key="qt_upload",
                         on_change=on_upload)
        st.markdown(API, unsafe_allow_html=False)

    try:
        cls = engine.load_strategy(codes[tpl])
    except engine.StrategyError as e:
        st.error(f"策略程式碼有錯誤：\n\n```\n{e}\n```")
        return

    with st.container(border=True):
        st.markdown(f'<div class="hint"><b>{T.esc(cls.__name__)}</b> — {T.esc((cls.__doc__ or "").strip())}</div>',
                    unsafe_allow_html=True)
        params = {}
        items = list(cls.params.items())
        if items:
            cols = st.columns(min(4, len(items)))
            for k, (name, default) in enumerate(items):
                c = cols[k % len(cols)]
                key = f"qt_p::{tpl}::{name}"
                if isinstance(default, bool):
                    params[name] = c.toggle(name, value=default, key=key)
                elif isinstance(default, int):
                    params[name] = int(c.number_input(name, value=int(default), step=1, key=key))
                elif isinstance(default, float):
                    step = 0.01 if abs(default) < 1 else 0.1 if abs(default) < 10 else 1.0
                    params[name] = float(c.number_input(name, value=float(default), step=step, format="%g", key=key))
                else:
                    params[name] = c.text_input(name, value=str(default), key=key)
        experiment = getattr(cls, "experiment", None) or []
        if experiment:
            b1, b2 = st.columns([1, 1])
            start_clicked = _wide_button(b1, "▶  開始回測", "qt_start", primary=True)
            exp_clicked = _wide_button(b2, f"對照實驗（{len(experiment)} 組）", "qt_exp", icon=":material/science:",
                                       help="同樣的出場規則，只換進場方式各跑一次（含隨機進場基準），跑完直接並排比較。"
                                            "用的是上面這組參數，只覆蓋實驗要改的那幾個。")
        else:
            start_clicked, exp_clicked = _wide_button(st, "▶  開始回測", "qt_start", primary=True), False

    if start_clicked or exp_clicked:
        try:
            data, used = cached_ohlcv(symbol, start, today + dt.timedelta(days=1), interval)
        except Exception as e:
            st.error(f"資料下載失敗：{e}")
            return
        if data.empty:
            st.error(f"抓不到 {symbol} 的{iv}資料。")
            return
        opts = dict(slippage_bps=slip, sizing_mode="淨值比例", sizing_value=size, lot_size=0)
        variants = [{**params, **ov} for ov in experiment] if exp_clicked else [params]
        ids = []
        try:
            with st.spinner("回測中…" if len(variants) == 1 else f"對照實驗：共 {len(variants)} 組，回測中…"):
                for p in variants:
                    res = engine.run(cls, data, p, cash, comm, **opts)
                    res["lookahead"] = engine.lookahead_check(cls, data, p, cash, comm, **opts)
                    run = R.from_engine(res, cls.__name__, used, iv, name=_run_name(cls, p, used, iv))
                    run.settings = {**run.settings, "期間": years}
                    S.add_run(run)
                    ids.append(run.id)
        except engine.StrategyError as e:
            st.error(f"回測時發生錯誤：\n\n```\n{e}\n```")
            return
        st.session_state["qt_last"] = ids[0]
        if exp_clicked:
            S.compare(ids)

    last = st.session_state.get("qt_last")
    lib = S.library()
    if last and last in lib:
        run = lib[last]
        s = S.stats_of(run)
        st.markdown(T.section("剛剛的結果"), unsafe_allow_html=True)
        st.markdown(T.chips([run.ea, run.symbol, run.timeframe, run.period] +
                            [f"{k}={v}" for k, v in run.params.items()]), unsafe_allow_html=True)
        st.markdown(T.kpi_cards([
            dict(label="淨利", value=S.money(s.get("淨利")), delta=f"總報酬 {S.pct(s.get('總報酬'))}",
                 trend=S.sign(s.get("淨利"))),
            dict(label="Sharpe", value=S.num(s.get("Sharpe"))),
            dict(label="最大回撤", value=S.pct(s.get("最大回撤"))),
            dict(label="獲利因子", value=S.num(s.get("獲利因子"))),
            dict(label="交易次數", value=f"{s.get('交易次數', 0)}", delta=f"勝率 {S.pct(s.get('勝率'))}"),
        ]), unsafe_allow_html=True)
        ok = run.lookahead[0] if run.lookahead else True
        if not ok:
            st.markdown(T.status("bad", "前視偏差檢查失敗：策略可能偷看了未來資料，結果不可信"), unsafe_allow_html=True)
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("查看完整分析", type="primary", key="qt_open"):
            S.open_run(run.id)
        c2.download_button("下載紀錄（.json）", run.to_json().encode("utf-8"), file_name=f"{run.id}.json",
                           mime="application/json", key="qt_dl")
        st.markdown('<div class="hint">這筆結果已加入「研究紀錄」（這次連線有效）。想永久保存，可以下載後交給我放進 repo 的 runs/ 資料夾。</div>',
                    unsafe_allow_html=True)


def _run_name(cls, params, symbol, iv) -> str:
    """策略可以定義 variant(params) 回傳模式標籤，會顯示在紀錄名稱裡（例如對照實驗的各組）。"""
    label = ""
    fn = getattr(cls, "variant", None)
    if callable(fn):
        try:
            label = str(fn(params) or "")
        except Exception:
            label = ""
    ea = cls.__name__ + (f" [{label}]" if label else "")
    return f"{ea} · {symbol} · {iv}"


def _wide_button(where, label, key, primary=False, help=None, icon=None):
    kw = dict(type="primary" if primary else "secondary", key=key, help=help)
    if icon:
        kw["icon"] = icon
    if _has_width():
        return where.button(label, width="stretch", **kw)
    return where.button(label, use_container_width=True, **kw)


def _has_width() -> bool:
    import inspect
    try:
        return "width" in inspect.signature(st.button).parameters
    except (TypeError, ValueError):
        return False
