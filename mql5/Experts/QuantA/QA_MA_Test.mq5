//+------------------------------------------------------------------+
//| QA_MA_Test.mq5                                                   |
//| 測試用 EA：均線交叉。目的是驗證「MT5 回測 → 自動上傳 → app」這條路，    |
//| 不是拿來賺錢的策略。標有 ★ 的四處就是接上 QUANT_A 需要加的程式碼。       |
//+------------------------------------------------------------------+
#property copyright "QUANT_A"
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <QuantA_Export.mqh>          // ★ 1. 引入匯出模組

input int    InpFast     = 20;        // 短均線週期
input int    InpSlow     = 50;        // 長均線週期
input double InpLots     = 0.10;      // 每筆手數
input int    InpSLPoints = 300;       // 停損（點，0 = 不設）
input int    InpTPPoints = 600;       // 停利（點，0 = 不設）
input long   InpMagic    = 20261001;  // EA 識別碼

CTrade trade;
int    hFast = INVALID_HANDLE;
int    hSlow = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
  {
   hFast = iMA(_Symbol, _Period, InpFast, 0, MODE_SMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, _Period, InpSlow, 0, MODE_SMA, PRICE_CLOSE);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE)
      return INIT_FAILED;
   trade.SetExpertMagicNumber(InpMagic);

   QA_Init("QA_MA_Test");             // ★ 2. 初始化，並登記參數
   QA_Param("InpFast", InpFast);
   QA_Param("InpSlow", InpSlow);
   QA_Param("InpLots", InpLots);
   QA_Param("InpSLPoints", InpSLPoints);
   QA_Param("InpTPPoints", InpTPPoints);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(hFast);
   IndicatorRelease(hSlow);
  }

//+------------------------------------------------------------------+
double OnTester()
  {
   QA_Export();                       // ★ 4. 回測結束時輸出
   return 0.0;
  }

//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE type)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetInteger(POSITION_TYPE) == type)
         return true;
     }
   return false;
  }

void ClosePositions(ENUM_POSITION_TYPE type)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetInteger(POSITION_TYPE) == type)
         trade.PositionClose(ticket);
     }
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   QA_OnTick();                       // ★ 3. 每個 tick 的第一行

   // 只在新 K 棒開始時判斷一次，而且只看「已經收盤」的 K 棒（避免偷看未來）
   static datetime last_bar = 0;
   datetime bar = iTime(_Symbol, _Period, 0);
   if(bar == last_bar)
      return;
   last_bar = bar;

   double f[2], s[2];
   if(CopyBuffer(hFast, 0, 1, 2, f) != 2 || CopyBuffer(hSlow, 0, 1, 2, s) != 2)
      return;
   // f[0] = 前兩根、f[1] = 前一根（剛收盤）
   bool cross_up   = f[0] <= s[0] && f[1] > s[1];
   bool cross_down = f[0] >= s[0] && f[1] < s[1];

   if(cross_up)
     {
      ClosePositions(POSITION_TYPE_SELL);
      if(!HasPosition(POSITION_TYPE_BUY))
        {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double sl  = (InpSLPoints > 0) ? NormalizeDouble(ask - InpSLPoints * _Point, _Digits) : 0.0;
         double tp  = (InpTPPoints > 0) ? NormalizeDouble(ask + InpTPPoints * _Point, _Digits) : 0.0;
         trade.Buy(InpLots, _Symbol, ask, sl, tp, "MA 黃金交叉");
        }
     }
   else if(cross_down)
     {
      ClosePositions(POSITION_TYPE_BUY);
      if(!HasPosition(POSITION_TYPE_SELL))
        {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double sl  = (InpSLPoints > 0) ? NormalizeDouble(bid + InpSLPoints * _Point, _Digits) : 0.0;
         double tp  = (InpTPPoints > 0) ? NormalizeDouble(bid - InpTPPoints * _Point, _Digits) : 0.0;
         trade.Sell(InpLots, _Symbol, bid, sl, tp, "MA 死亡交叉");
        }
     }
  }
//+------------------------------------------------------------------+
