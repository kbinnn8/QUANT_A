# QUANT_A

和 Claude 一起研究 MT5 EA 的工作室。MT5 負責執行回測與交易，這個 app 負責判斷：這個結果可不可信、問題出在哪。

## 頁面
- **研究紀錄**：所有回測（MT5 + Python 快速測試），依 EA 統計嘗試次數與 DSR
- **回測分析**：總覽、淨值與回撤、交易分析、可信度檢驗、交易明細，每張圖附「怎麼看」
- **比較**：多次回測並排，標出各指標最佳者與參數差異
- **快速測試**：Python 事件驅動回測引擎，寫 EA 前先驗證想法
- **圖表**：TradingView 即時圖表
- **說明**：研究流程、策略寫法、名詞解釋

## 結構
```
app.py                 進入點（頂部導覽）
qa/runs.py             回測紀錄格式（JSON），MT5 與 Python 共用
qa/robust.py           可信度檢驗：蒙地卡羅、移除最佳交易、成本敏感度、滾動指標、DSR
qa/engine.py           Python 回測引擎（下一根開盤成交、停損停利、滑價、日誌、前視偏差檢查）
qa/report.py           績效統計（MT5 報告的全部項目＋延伸）
qa/ta.py               技術指標
qa/templates/          策略範本
qa/ui/                 介面（theme 採 TradingView 深色配色）
runs/                  永久保存的回測紀錄
mql5/Include/QuantA_Export.mqh   MT5 匯出模組（EA 加 4 行就能把回測結果輸出給 app）
mql5/Experts/QuantA/             測試用 EA
bridge/quanta_uploader.py        電腦端上傳小程式（監看 MT5 共用資料夾 → GitHub runs/）
```

## MT5 → app 自動上傳
1. EA 引入 `QuantA_Export.mqh`，在 `OnInit` 呼叫 `QA_Init` / `QA_Param`、`OnTick` 第一行 `QA_OnTick()`、`OnTester` 呼叫 `QA_Export()`
2. 單次回測結束時，EA 把結果寫到 `%APPDATA%\MetaQuotes\Terminal\Common\Files\QuantA\`
3. 上傳小程式（只用 Python 標準函式庫）把檔案上傳到這個 repo 的 `runs/`
4. Streamlit 偵測到 repo 更新，`研究紀錄`就會出現這筆回測

MetaEditor 用的檔案請用 UTF-16 存（安裝包裡已經轉好），否則中文註解可能變亂碼。

## 安全
快速測試會在伺服器上執行策略程式碼：請把 Streamlit app 設為私人，或在 Secrets 設定 `APP_PASSWORD`。
