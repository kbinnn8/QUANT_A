"""說明：整體流程、策略寫法、名詞解釋。"""
from __future__ import annotations

import streamlit as st

from . import theme as T

FLOW = """
### 研究流程

1. **先寫下假設**：你認為市場有什麼規律？為什麼會有這個規律？沒有假設的策略，通常只是在歷史資料上湊出來的
2. **快速測試**：用 Python 引擎幾分鐘內跑完，看值不值得繼續。大部分想法在這一步就該淘汰
3. **寫成 EA，在 MT5 回測**：用 XM 的真實報價驗證，結果會自動出現在「研究紀錄」*（自動上傳建置中）*
4. **可信度檢驗**：蒙地卡羅、拿掉最佳交易、成本敏感度、DSR。好看的回測不等於真的有效
5. **模擬盤**：在 XM 模擬帳戶跑一段時間，實際結果要落在回測預期的範圍內
6. **少量實盤**：到這一步才考慮真錢

每一步都可能回到第 1 步。**果斷放棄一個想法，本身就是很重要的能力。**
"""

API = """
### 快速測試的策略寫法

```python
class MyStrategy(Strategy):
    params = {"n": 20, "sl_pct": 0.02}      # 可調參數

    def init(self):                          # 只跑一次：先算指標
        self.ma = self.I(ta.sma(self.close, self.p.n), "MA")

    def next(self):                          # 每根 K 棒收盤後跑一次
        i = self.i
        if self.is_flat and self.close[i] > self.ma[i]:
            self.buy(sl_pct=self.p.sl_pct)   # 下一根開盤成交
        elif self.is_long and self.close[i] < self.ma[i]:
            self.close_position("跌破均線")
```

- **資料**：`self.open` `self.high` `self.low` `self.close` `self.volume`、`self.i`、`self.time`、`self.p.參數名`
- **下單**（下一根開盤成交）：`self.buy(size=None, sl=, tp=, sl_pct=, tp_pct=, tag=)`、`self.sell(...)`、
  `self.close_position()`、`self.set_sl(價格)`、`self.set_tp(價格)`、`self.log(...)`
- **狀態**：`self.is_flat` `self.is_long` `self.is_short` `self.entry_price` `self.bars_in_trade` `self.equity`
- **指標**（`ta.`）：`sma` `ema` `rsi` `macd` `bollinger` `atr` `highest` `lowest` `stdev` `roc` `zscore` `shift`、
  `ta.crossover(a, b, i)` / `ta.crossunder(a, b, i)`
- **成交規則**：停損停利用最高 / 最低價判斷，跳空以開盤價成交；同一根同時碰到停損和停利，保守假設先停損
"""

GLOSSARY = """
### 名詞解釋

| 名詞 | 意思 | 參考標準 |
|---|---|---|
| 獲利因子 | 毛利 ÷ 毛損 | > 1 才賺錢；1.3 以上比較有餘裕 |
| 期望收益 | 平均每筆交易的損益 | 要明顯大於每筆的交易成本 |
| 回復因子 | 淨利 ÷ 最大回撤金額 | 越大越好，代表「賺的錢」相對「受的苦」 |
| Sharpe | 年化報酬 ÷ 年化波動 | > 1 不錯；> 2 要懷疑是不是過擬合 |
| Sortino | 同 Sharpe，但只把下跌算成風險 | 比 Sharpe 高很多，代表波動多半是往上 |
| 最大回撤 | 淨值從高點跌下來最深的幅度 | 決定你撐不撐得住 |
| 餘額 vs 淨值 | 餘額只算已平倉；淨值含未平倉 | 差距大代表持倉期間浮動很大 |
| MFE / MAE | 持倉期間最大浮盈 / 最大浮虧 | 用來決定停利、停損放哪 |
| Z 分數 | 輸贏是否成串出現 | \\|Z\\| > 2 代表有顯著連續性 |
| AHPR / GHPR | 每筆交易的算術 / 幾何平均持有期報酬 | > 1 才賺錢 |
| LR 相關係數 | 淨值曲線和直線有多像 | 越接近 1 越平穩 |
| SQN | 交易品質分數（Van Tharp） | > 2 不錯 |
| PSR | 真實 Sharpe > 0 的機率 | 只看單次結果 |
| DSR | 把「試了幾次」考慮進去後的 PSR | > 95% 才算有說服力 |
| 前視偏差 | 回測時不小心用到未來的資料 | 一定要避免；app 會自動檢查 |
"""


def render():
    st.markdown(T.header("說明", "研究流程、策略寫法、報告裡的名詞。"), unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["研究流程", "策略寫法", "名詞解釋"])
    with t1:
        st.markdown(FLOW)
    with t2:
        st.markdown(API)
    with t3:
        st.markdown(GLOSSARY)
