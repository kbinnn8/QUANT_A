//+------------------------------------------------------------------+
//| AO_Div_RSI.mq5                                                   |
//| AO 背離 + RSI 極端（B 版，逆勢）                                     |
//|                                                                  |
//| 做多：價格創更低的擺動低點，AO 在對應位置卻比前一個低點高（看漲背離），  |
//|       而且兩個低點之間 RSI 曾經 ≤ InpRSILow（預設 20）。              |
//| 做空：價格創更高的擺動高點，AO 卻比前一個高點低（看跌背離），           |
//|       而且兩個高點之間 RSI 曾經 ≥ InpRSIHigh（預設 80）。             |
//| 擺動點要等右邊 N 根 K 棒收盤才能確認 → 確認後的下一根開盤進場。         |
//| 停損：第二個擺動點外 0.5 倍 ATR；停利：停損距離 × 2；每筆風險 1% 淨值。  |
//|                                                                  |
//| 與 QUANT_A 快速測試的 Python 版（ao_divergence_rsi.py）規則逐條相同。  |
//+------------------------------------------------------------------+
#property copyright   "QUANT_A"
#property version     "1.00"
#property description "AO 背離 + RSI 極端（B 版）"

#include <Trade\Trade.mqh>
#include <QuantA_Export.mqh>              // ★ QUANT_A

input group "=== 擺動點與背離 ==="
input int    InpPivotLeft     = 3;        // 擺動點：左邊幾根 K 棒
input int    InpPivotRight    = 3;        // 擺動點：右邊幾根 K 棒（確認要等的 K 棒數）
input int    InpMinGap        = 5;        // 兩個擺動點最少相隔幾根
input int    InpMaxGap        = 60;       // 兩個擺動點最多相隔幾根

input group "=== RSI ==="
input int    InpRSIPeriod     = 14;       // RSI 週期
input double InpRSILow        = 20.0;     // 偏多：兩低點之間 RSI 曾經 ≤ 此值
input double InpRSIHigh       = 80.0;     // 偏空：兩高點之間 RSI 曾經 ≥ 此值

input group "=== 停損、停利、部位 ==="
input int    InpATRPeriod     = 14;       // ATR 週期
input double InpSLBufferATR   = 0.5;      // 停損放在擺動點外 N 倍 ATR
input double InpRR            = 2.0;      // 停利 = 停損距離 × N
input double InpRiskPct       = 1.0;      // 每筆風險（淨值 %）；0 = 用固定手數
input double InpFixedLots     = 0.10;     // 固定手數（InpRiskPct = 0 時使用）
input bool   InpAllowLong     = true;     // 允許做多
input bool   InpAllowShort    = true;     // 允許做空

input group "=== 其他 ==="
input bool   InpEnableTrading = false;    // 實盤自動下單（策略測試器中一律下單）
input ulong  InpMagic         = 20261002; // EA 識別碼

CTrade   trade;
int      hAO  = INVALID_HANDLE;
int      hRSI = INVALID_HANDLE;
int      hATR = INVALID_HANDLE;
datetime last_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpPivotLeft < 1 || InpPivotRight < 1 || InpMinGap < 1 || InpMaxGap <= InpMinGap)
     {
      Print("參數錯誤：擺動點左右至少 1 根，且最多相隔要大於最少相隔");
      return(INIT_PARAMETERS_INCORRECT);
     }
   hAO  = iAO(_Symbol, _Period);
   hRSI = iRSI(_Symbol, _Period, InpRSIPeriod, PRICE_CLOSE);
   hATR = iATR(_Symbol, _Period, InpATRPeriod);
   if(hAO == INVALID_HANDLE || hRSI == INVALID_HANDLE || hATR == INVALID_HANDLE)
     {
      Print("建立指標失敗，錯誤碼：", GetLastError());
      return(INIT_FAILED);
     }
   trade.SetExpertMagicNumber(InpMagic);

   QA_Init("AO_Div_RSI");                 // ★ QUANT_A：登記參數
   QA_Param("pivot_left", InpPivotLeft);
   QA_Param("pivot_right", InpPivotRight);
   QA_Param("min_gap", InpMinGap);
   QA_Param("max_gap", InpMaxGap);
   QA_Param("rsi_period", InpRSIPeriod);
   QA_Param("rsi_low", InpRSILow);
   QA_Param("rsi_high", InpRSIHigh);
   QA_Param("atr_period", InpATRPeriod);
   QA_Param("sl_buffer_atr", InpSLBufferATR);
   QA_Param("rr", InpRR);
   QA_Param("risk_pct", InpRiskPct);
   QA_Param("allow_long", InpAllowLong);
   QA_Param("allow_short", InpAllowShort);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(hAO  != INVALID_HANDLE) IndicatorRelease(hAO);
   if(hRSI != INVALID_HANDLE) IndicatorRelease(hRSI);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
  }

//+------------------------------------------------------------------+
double OnTester()
  {
   QA_Export();                           // ★ QUANT_A：回測結束時輸出
   return(0.0);
  }

//+------------------------------------------------------------------+
//| 工具                                                              |
//+------------------------------------------------------------------+
bool TradingOn()
  {
   return(InpEnableTrading || MQLInfoInteger(MQL_TESTER) != 0);
  }

bool HasMyPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return(true);
     }
   return(false);
  }

// 陣列為時間序列（索引 0 = 正在形成的 K 棒，1 = 剛收盤的 K 棒，數字越大越舊）
// 擺動低點：比左邊（較舊）L 根都低，而且不高於右邊（較新）R 根
bool IsPivot(const double &x[], int s, int n, bool is_low)
  {
   if(s - InpPivotRight < 1 || s + InpPivotLeft >= n)
      return(false);
   for(int k = 1; k <= InpPivotLeft; k++)
     {
      if(is_low && !(x[s] < x[s + k]))
         return(false);
      if(!is_low && !(x[s] > x[s + k]))
         return(false);
     }
   for(int k = 1; k <= InpPivotRight; k++)
     {
      if(is_low && !(x[s] <= x[s - k]))
         return(false);
      if(!is_low && !(x[s] >= x[s - k]))
         return(false);
     }
   return(true);
  }

// 在 s2 之前（更舊）、相隔 InpMinGap 到 InpMaxGap 根之內，最近的一個擺動點
int PreviousPivot(const double &x[], int s2, int n, bool is_low)
  {
   for(int s = s2 + InpMinGap; s <= s2 + InpMaxGap; s++)
      if(IsPivot(x, s, n, is_low))
         return(s);
   return(-1);
  }

double RangeMin(const double &x[], int from, int to)
  {
   double m = DBL_MAX;
   for(int s = from; s <= to; s++)
      if(x[s] != EMPTY_VALUE && x[s] < m)
         m = x[s];
   return(m);
  }

double RangeMax(const double &x[], int from, int to)
  {
   double m = -DBL_MAX;
   for(int s = from; s <= to; s++)
      if(x[s] != EMPTY_VALUE && x[s] > m)
         m = x[s];
   return(m);
  }

// 依風險計算手數：停損時虧掉淨值的 InpRiskPct%
double CalcLots(double risk_price)
  {
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lots  = InpFixedLots;
   if(InpRiskPct > 0.0)
     {
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0.0 || ts <= 0.0 || risk_price <= 0.0)
         return(0.0);
      double money_per_lot = risk_price / ts * tv;
      lots = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPct / 100.0 / money_per_lot;
     }
   if(vstep > 0.0)
      lots = MathFloor(lots / vstep + 1e-9) * vstep;
   if(lots < vmin)
     {
      Print("風險太小，算出的手數低於最小手數，略過這個訊號");
      return(0.0);
     }
   int vdig = (vstep > 0.0) ? (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9)) : 2;
   return(NormalizeDouble(MathMin(lots, vmax), vdig));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   QA_OnTick();                           // ★ QUANT_A：記錄淨值

   datetime bar = iTime(_Symbol, _Period, 0);
   if(bar == last_bar)
      return;

   int need = 1 + InpPivotRight + InpMaxGap + InpPivotLeft + 2;
   double lo[], hi[], ao[], rsi[], atr[];
   ArraySetAsSeries(lo, true);
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(ao, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   if(CopyLow(_Symbol, _Period, 0, need, lo) != need) return;
   if(CopyHigh(_Symbol, _Period, 0, need, hi) != need) return;
   if(CopyBuffer(hAO, 0, 0, need, ao) != need) return;
   if(CopyBuffer(hRSI, 0, 0, need, rsi) != need) return;
   if(CopyBuffer(hATR, 0, 0, 2, atr) != 2) return;
   last_bar = bar;

   if(HasMyPosition())
      return;                             // 一次只持有一個部位，出場只靠停損 / 停利

   int    s2  = 1 + InpPivotRight;         // 剛好在上一根收盤時被確認的擺動點
   double buf = InpSLBufferATR * atr[1];

   //--- 看漲背離
   if(InpAllowLong && IsPivot(lo, s2, need, true))
     {
      int s1 = PreviousPivot(lo, s2, need, true);
      if(s1 > 0 && lo[s2] < lo[s1] && ao[s2] > ao[s1] && RangeMin(rsi, s2, s1) <= InpRSILow)
        {
         double ask  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double sl   = NormalizeDouble(lo[s2] - buf, _Digits);
         double risk = ask - sl;
         PrintFormat("看漲背離：低點 %.5f → %.5f，AO %.6f → %.6f，相隔 %d 根", lo[s1], lo[s2], ao[s1], ao[s2], s1 - s2);
         if(risk > 0.0)
           {
            if(TradingOn())
              {
               double tp   = NormalizeDouble(ask + InpRR * risk, _Digits);
               double lots = CalcLots(risk);
               if(lots > 0.0 && !trade.Buy(lots, _Symbol, ask, sl, tp, StringFormat("看漲背離 RSI<=%.0f", InpRSILow)))
                  Print("買單失敗：", trade.ResultRetcodeDescription());
              }
            return;
           }
        }
     }

   //--- 看跌背離
   if(InpAllowShort && IsPivot(hi, s2, need, false))
     {
      int s1 = PreviousPivot(hi, s2, need, false);
      if(s1 > 0 && hi[s2] > hi[s1] && ao[s2] < ao[s1] && RangeMax(rsi, s2, s1) >= InpRSIHigh)
        {
         double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double sl   = NormalizeDouble(hi[s2] + buf, _Digits);
         double risk = sl - bid;
         PrintFormat("看跌背離：高點 %.5f → %.5f，AO %.6f → %.6f，相隔 %d 根", hi[s1], hi[s2], ao[s1], ao[s2], s1 - s2);
         if(risk > 0.0 && TradingOn())
           {
            double tp   = NormalizeDouble(bid - InpRR * risk, _Digits);
            double lots = CalcLots(risk);
            if(lots > 0.0 && !trade.Sell(lots, _Symbol, bid, sl, tp, StringFormat("看跌背離 RSI>=%.0f", InpRSIHigh)))
               Print("賣單失敗：", trade.ResultRetcodeDescription());
           }
        }
     }
  }
//+------------------------------------------------------------------+
