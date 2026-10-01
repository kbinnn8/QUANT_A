# QUANT_A

和 Claude 一起研究 MT5 EA 的工作室。**回測在 MT5 跑**，這個 app 負責紀錄、對比和判斷：EA 改了之後有沒有真的變好、結果可不可信、問題出在哪。

## 頁面
- **研究紀錄**：所有 MT5 回測自動列出；依 EA 統計嘗試次數與 DSR；版本演進圖
- **回測分析**：總覽、淨值與回撤、交易分析（含依商品）、可信度檢驗、交易明細，每張圖附「怎麼看」
- **改良對比**：舊版 vs 新版——數字變化、參數差異、被濾掉 / 新增的交易、淨利瀑布圖、改善是不是運氣（置換檢定 / bootstrap）
- **多筆比較**：對照實驗等多筆回測並排
- **圖表**：TradingView 即時圖表
- **說明**：研究流程、MT5 怎麼接、名詞解釋

## 結構
```
app.py                 進入點（頂部導覽）
qa/runs.py             回測紀錄格式（JSON）
qa/report.py           績效統計（MT5 報告的全部項目＋延伸）
qa/robust.py           可信度檢驗：蒙地卡羅、移除最佳交易、成本敏感度、滾動指標、DSR
qa/improve.py          改良前後對比：交易配對、瀑布圖、置換檢定、bootstrap
qa/ui/                 介面（theme 採 TradingView 深色配色）
runs/                  永久保存的回測紀錄（上傳小工具寫進來）
mql5/Include/QuantA_Export.mqh   MT5 匯出模組
mql5/Experts/QuantA/             EA（AO 背離 + RSI、費波那契黃金區域、測試用均線 EA）
bridge/quanta_uploader.py        電腦端上傳小程式（監看 MT5 共用資料夾 → GitHub runs/）

qa/engine.py、qa/templates/ 等   Python 參考實作：Claude 用來逐條對照 EA 規則，app 不會用到
```

## MT5 → app 自動上傳
1. EA 引入 `QuantA_Export.mqh`，在 `OnInit` 呼叫 `QA_Init` / `QA_Param`（選用 `QA_Note`、`QA_Variant`）、`OnTick` 第一行 `QA_OnTick()`、`OnTester` 呼叫 `QA_Export()`
2. 單次回測結束時，EA 把結果寫到 `%APPDATA%\MetaQuotes\Terminal\Common\Files\QuantA\`
3. 上傳小程式（只用 Python 標準函式庫）把檔案上傳到這個 repo 的 `runs/`
4. Streamlit 偵測到 repo 更新，`研究紀錄`就會出現這筆回測

MetaEditor 用的檔案請用 UTF-16 存（安裝包裡已經轉好），否則中文註解可能變亂碼。

## 安全
回測紀錄是私人資料：請把 Streamlit app 設為私人，或在 Secrets 設定 `APP_PASSWORD`。
