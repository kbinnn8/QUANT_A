//+------------------------------------------------------------------+
//|                                              AO_RSI_Signal.mq5   |
//|  Awesome Oscillator + RSI 條件達成：提示 / 自動下單 EA (MQL5)      |
//+------------------------------------------------------------------+
#property version   "1.01"
#property description "AO 與 RSI 同時達成條件時發出提示，可選擇自動下單"

#include <Trade\Trade.mqh>
#include <QuantA_Export.mqh>          // ★ QUANT_A：回測結果自動輸出

//--- AO 訊號模式
enum ENUM_AO_MODE
  {
   AO_ZERO_CROSS   = 0,   // AO 穿越零軸
   AO_COLOR_CHANGE = 1,   // AO 柱體變色（紅轉綠 / 綠轉紅）
   AO_ABOVE_BELOW  = 2    // AO 位於零軸之上 / 之下
  };

//--- 輸入參數
input group "=== Awesome Oscillator ==="
input ENUM_AO_MODE       AO_Mode        = AO_ZERO_CROSS; // AO 條件模式

input group "=== RSI ==="
input int                RSI_Period     = 14;            // RSI 週期
input ENUM_APPLIED_PRICE RSI_Price      = PRICE_CLOSE;   // RSI 價格
input double             RSI_BuyLevel   = 50.0;          // 買進：RSI 高於此值
input double             RSI_SellLevel  = 50.0;          // 賣出：RSI 低於此值

input group "=== 交易 ==="
input bool   EnableTrading  = false;      // 啟用自動下單
input double Lots           = 0.10;       // 手數
input int    StopLossPts    = 300;        // 停損（點，0 = 不設）
input int    TakeProfitPts  = 600;        // 停利（點，0 = 不設）
input bool   CloseOpposite  = true;       // 反向訊號時平掉相反部位
input ulong  MagicNumber    = 20261001;   // 魔術號碼
input string InpNote        = "";         // 備註：這次改了什麼（會顯示在研究紀錄）

input group "=== 通知 ==="
input bool EnableAlert = true;            // 彈出 Alert
input bool EnablePush  = false;           // 推播到手機 MT5

//--- 全域變數
int      hAO         = INVALID_HANDLE;
int      hRSI        = INVALID_HANDLE;
datetime lastBarTime = 0;
CTrade   trade;

//+------------------------------------------------------------------+
int OnInit()
  {
   hAO  = iAO(_Symbol, _Period);
   hRSI = iRSI(_Symbol, _Period, RSI_Period, RSI_Price);

   if(hAO == INVALID_HANDLE || hRSI == INVALID_HANDLE)
     {
      Print("建立指標失敗，錯誤碼：", GetLastError());
      return(INIT_FAILED);
     }

   trade.SetExpertMagicNumber(MagicNumber);

   // ★ QUANT_A：登記 EA 名稱與參數（列舉用文字記錄，比較好讀）
   QA_Init("AO_RSI_Signal");
   QA_Note(InpNote);
   QA_Param("AO_Mode", EnumToString(AO_Mode));
   QA_Param("RSI_Period", RSI_Period);
   QA_Param("RSI_Price", EnumToString(RSI_Price));
   QA_Param("RSI_BuyLevel", RSI_BuyLevel);
   QA_Param("RSI_SellLevel", RSI_SellLevel);
   QA_Param("Lots", Lots);
   QA_Param("StopLossPts", StopLossPts);
   QA_Param("TakeProfitPts", TakeProfitPts);
   QA_Param("CloseOpposite", CloseOpposite);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(hAO  != INVALID_HANDLE) IndicatorRelease(hAO);
   if(hRSI != INVALID_HANDLE) IndicatorRelease(hRSI);
  }

//+------------------------------------------------------------------+
double OnTester()
  {
   QA_Export();                       // ★ QUANT_A：回測結束時輸出
   return(0.0);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   QA_OnTick();                       // ★ QUANT_A：記錄淨值（每根新 K 棒一次）

   //--- 只在新 K 棒開盤時判斷（用已收盤的 K 棒，避免訊號閃爍）
   datetime curBar = iTime(_Symbol, _Period, 0);
   if(curBar == lastBarTime)
      return;

   double ao[], rsi[];
   ArraySetAsSeries(ao,  true);
   ArraySetAsSeries(rsi, true);

   // ao[0] = 前一根(已收盤) K 棒, ao[1] = 前兩根, ao[2] = 前三根
   if(CopyBuffer(hAO,  0, 1, 3, ao)  != 3) return;
   if(CopyBuffer(hRSI, 0, 1, 1, rsi) != 1) return;

   lastBarTime = curBar;

   bool buySignal  = AOBullish(ao) && rsi[0] > RSI_BuyLevel;
   bool sellSignal = AOBearish(ao) && rsi[0] < RSI_SellLevel;

   if(buySignal)
     {
      Notify("買進", ao[0], rsi[0]);
      if(TradingOn()) OpenTrade(ORDER_TYPE_BUY);
     }
   else if(sellSignal)
     {
      Notify("賣出", ao[0], rsi[0]);
      if(TradingOn()) OpenTrade(ORDER_TYPE_SELL);
     }
  }

//+------------------------------------------------------------------+
//| 是否下單：策略測試器裡一定下單（只提示不下單的話回測沒有意義）           |
//+------------------------------------------------------------------+
bool TradingOn()
  {
   return(EnableTrading || MQLInfoInteger(MQL_TESTER) != 0);
  }

//+------------------------------------------------------------------+
//| AO 多方條件                                                       |
//+------------------------------------------------------------------+
bool AOBullish(const double &ao[])
  {
   switch(AO_Mode)
     {
      case AO_ZERO_CROSS:   return(ao[1] <= 0.0 && ao[0] > 0.0);           // 由下往上穿越零軸
      case AO_COLOR_CHANGE: return(ao[1] <= ao[2] && ao[0] > ao[1]);       // 紅柱轉綠柱
      case AO_ABOVE_BELOW:  return(ao[0] > 0.0);                           // 位於零軸之上
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| AO 空方條件                                                       |
//+------------------------------------------------------------------+
bool AOBearish(const double &ao[])
  {
   switch(AO_Mode)
     {
      case AO_ZERO_CROSS:   return(ao[1] >= 0.0 && ao[0] < 0.0);           // 由上往下穿越零軸
      case AO_COLOR_CHANGE: return(ao[1] >= ao[2] && ao[0] < ao[1]);       // 綠柱轉紅柱
      case AO_ABOVE_BELOW:  return(ao[0] < 0.0);                           // 位於零軸之下
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| 提示                                                              |
//+------------------------------------------------------------------+
void Notify(const string side, const double aoVal, const double rsiVal)
  {
   string msg = StringFormat("%s %s %s條件達成 | AO=%.5f  RSI=%.2f",
                             _Symbol, EnumToString(_Period), side, aoVal, rsiVal);
   Print(msg);
   if(MQLInfoInteger(MQL_TESTER))      // 回測時不跳視窗、不推播（會拖慢速度、洗版）
      return;
   if(EnableAlert) Alert(msg);
   if(EnablePush)  SendNotification(msg);
  }

//+------------------------------------------------------------------+
//| 是否已有此 EA 的指定方向部位                                       |
//+------------------------------------------------------------------+
bool HasPosition(const ENUM_POSITION_TYPE type)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == type)
         return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| 平掉此 EA 的指定方向部位                                           |
//+------------------------------------------------------------------+
void ClosePositions(const ENUM_POSITION_TYPE type)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == type)
         trade.PositionClose(ticket);
     }
  }

//+------------------------------------------------------------------+
//| 下單                                                              |
//+------------------------------------------------------------------+
void OpenTrade(const ENUM_ORDER_TYPE type)
  {
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   if(type == ORDER_TYPE_BUY)
     {
      if(CloseOpposite) ClosePositions(POSITION_TYPE_SELL);
      if(HasPosition(POSITION_TYPE_BUY)) return;

      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double sl  = StopLossPts   > 0 ? NormalizeDouble(ask - StopLossPts   * _Point, digits) : 0.0;
      double tp  = TakeProfitPts > 0 ? NormalizeDouble(ask + TakeProfitPts * _Point, digits) : 0.0;

      if(!trade.Buy(Lots, _Symbol, ask, sl, tp, "AO+RSI Buy"))
         Print("買單失敗：", trade.ResultRetcodeDescription());
     }
   else
     {
      if(CloseOpposite) ClosePositions(POSITION_TYPE_BUY);
      if(HasPosition(POSITION_TYPE_SELL)) return;

      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double sl  = StopLossPts   > 0 ? NormalizeDouble(bid + StopLossPts   * _Point, digits) : 0.0;
      double tp  = TakeProfitPts > 0 ? NormalizeDouble(bid - TakeProfitPts * _Point, digits) : 0.0;

      if(!trade.Sell(Lots, _Symbol, bid, sl, tp, "AO+RSI Sell"))
         Print("賣單失敗：", trade.ResultRetcodeDescription());
     }
  }
//+------------------------------------------------------------------+
