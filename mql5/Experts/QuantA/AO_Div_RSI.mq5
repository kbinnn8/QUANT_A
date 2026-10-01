//+------------------------------------------------------------------+
//| AO_Div_RSI.mq5                                                   |
//| AO 背離 + RSI 極端（B 版，逆勢）＋ 對照實驗模式                        |
//|                                                                  |
//| 做多：價格創更低的擺動低點，AO 在對應位置卻比前一個低點高（看漲背離），  |
//|       而且兩個低點之間 RSI 曾經 ≤ InpRSILow（預設 20）。              |
//| 做空：價格創更高的擺動高點，AO 卻比前一個高點低（看跌背離），           |
//|       而且兩個高點之間 RSI 曾經 ≥ InpRSIHigh（預設 80）。             |
//| 擺動點要等右邊 N 根 K 棒收盤才能確認 → 確認後的下一根開盤進場。         |
//| 停損：擺動點外 0.5 倍 ATR；停利：停損距離 × 2；每筆風險 1% 淨值。       |
//|                                                                  |
//| InpEntryMode（對照實驗，出場規則全部一樣）：                          |
//|   背離 + RSI（完整版）／只有背離／只有 RSI／隨機進場                   |
//| 只有 RSI、隨機進場的停損放在最近 7 根 K 棒的高低點外 0.5 倍 ATR。        |
//|                                                                  |
//| 與 QUANT_A 快速測試的 Python 版（ao_divergence_rsi.py）規則逐條相同，  |
//| 隨機進場用同一個雜湊公式：同一根 K 棒、同一個種子會得到同一個亂數。      |
//+------------------------------------------------------------------+
#property copyright   "QUANT_A"
#property version     "1.10"
#property description "AO 背離 + RSI 極端（B 版），含對照實驗模式"

#include <Trade\Trade.mqh>
#include <QuantA_Export.mqh>              // ★ QUANT_A

enum ENUM_ENTRY_MODE
  {
   ENTRY_DIV_RSI  = 0,   // 背離 + RSI（完整版）
   ENTRY_DIV_ONLY = 1,   // 只有背離
   ENTRY_RSI_ONLY = 2,   // 只有 RSI（剛進入 20 / 80 就進場）
   ENTRY_RANDOM   = 3    // 隨機進場（沒有優勢的基準）
  };

input group "=== 進場模式（對照實驗）==="
input ENUM_ENTRY_MODE InpEntryMode = ENTRY_DIV_RSI; // 進場模式
input double InpRandomProb    = 0.01;     // 隨機模式：空手時每根 K 棒進場的機率
input int    InpSeed          = 1;        // 隨機模式：亂數種子（換種子 = 換一組隨機進場）

input group "=== 擺動點與背離 ==="
input int    InpPivotLeft     = 3;        // 擺動點：左邊幾根 K 棒
input int    InpPivotRight    = 3;        // 擺動點：右邊幾根 K 棒（確認要等的 K 棒數）
input int    InpMinGap        = 5;        // 兩個擺動點最少相隔幾根
input int    InpMaxGap        = 60;       // 兩個擺動點最多相隔幾根

input group "=== RSI ==="
input int    InpRSIPeriod     = 14;       // RSI 週期
input double InpRSILow        = 20.0;     // 偏多：RSI ≤ 此值
input double InpRSIHigh       = 80.0;     // 偏空：RSI ≥ 此值

input group "=== 停損、停利、部位 ==="
input int    InpATRPeriod     = 14;       // ATR 週期
input double InpSLBufferATR   = 0.5;      // 停損放在擺動點外 N 倍 ATR
input double InpRR            = 2.0;      // 停利 = 停損距離 × N
input double InpRiskPct       = 1.0;      // 每筆風險（淨值 %）；0 = 用固定手數
input double InpFixedLots     = 0.10;     // 固定手數（InpRiskPct = 0 時使用）
input double InpMaxLeverage   = 30.0;     // 部位上限：名目金額最多為淨值的幾倍
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
string ModeLabel()
  {
   switch(InpEntryMode)
     {
      case ENTRY_DIV_RSI:  return("背離+RSI");
      case ENTRY_DIV_ONLY: return("只有背離");
      case ENTRY_RSI_ONLY: return("只有RSI");
      case ENTRY_RANDOM:   return("隨機進場 #" + IntegerToString(InpSeed));
     }
   return("模式" + IntegerToString((int)InpEntryMode));
  }

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

   QA_Init("AO_Div_RSI");                 // ★ QUANT_A：登記參數（名稱和 Python 版一樣）
   QA_Variant(ModeLabel());
   QA_Param("entry_mode", (int)InpEntryMode);
   QA_Param("random_prob", InpRandomProb);
   QA_Param("seed", InpSeed);
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
   QA_Param("max_leverage", InpMaxLeverage);
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

// s2 剛被確認為擺動點時，是否和前一個擺動點形成背離（use_rsi = 是否要求 RSI 到過極端）
bool Divergence(const double &px[], const double &ao[], const double &rsi[], int s2, int n, bool is_low, bool use_rsi)
  {
   if(!IsPivot(px, s2, n, is_low))
      return(false);
   int s1 = PreviousPivot(px, s2, n, is_low);
   if(s1 < 0)
      return(false);
   if(is_low)
     {
      if(!(px[s2] < px[s1] && ao[s2] > ao[s1]))
         return(false);
      return(!use_rsi || RangeMin(rsi, s2, s1) <= InpRSILow);
     }
   if(!(px[s2] > px[s1] && ao[s2] < ao[s1]))
      return(false);
   return(!use_rsi || RangeMax(rsi, s2, s1) >= InpRSIHigh);
  }

// 可重現的亂數（splitmix64）：和 Python 版的 bar_random() 完全一樣
double BarRandom(datetime t, int seed, bool &go_long)
  {
   ulong z = (ulong)t + (ulong)seed * 0x9E3779B97F4A7C15;
   z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9;
   z = (z ^ (z >> 27)) * 0x94D049BB133111EB;
   z = z ^ (z >> 31);
   go_long = ((z & 1) == 1);
   return((double)(z >> 11) / 9007199254740992.0);   // 2^53
  }

// 依風險計算手數：停損時虧掉淨值的 InpRiskPct%，名目金額不超過淨值 × InpMaxLeverage
double CalcLots(double risk_price, double price)
  {
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double tv    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double eq    = AccountInfoDouble(ACCOUNT_EQUITY);
   double lots  = InpFixedLots;
   if(InpRiskPct > 0.0)
     {
      if(tv <= 0.0 || ts <= 0.0 || risk_price <= 0.0)
         return(0.0);
      lots = eq * InpRiskPct / 100.0 / (risk_price / ts * tv);
     }
   if(InpMaxLeverage > 0.0 && tv > 0.0 && ts > 0.0)
     {
      double notional_per_lot = price / ts * tv;      // 一手的名目金額（帳戶幣別）
      if(notional_per_lot > 0.0)
         lots = MathMin(lots, eq * InpMaxLeverage / notional_per_lot);
     }
   if(vstep > 0.0)
      lots = MathFloor(lots / vstep + 1e-9) * vstep;
   if(lots < vmin)
     {
      Print("算出的手數低於最小手數，略過這個訊號");
      return(0.0);
     }
   int vdig = (vstep > 0.0) ? (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9)) : 2;
   return(NormalizeDouble(MathMin(lots, vmax), vdig));
  }

// 下單；回傳 true = 這個訊號有效（風險 > 0），不論實際有沒有下單
bool Enter(bool is_long, double sl, string why)
  {
   double price = is_long ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   sl = NormalizeDouble(sl, _Digits);
   double risk = is_long ? price - sl : sl - price;
   if(risk <= 0.0)
      return(false);
   PrintFormat("%s 訊號：%s，價格 %.5f，停損 %.5f", ModeLabel(), why, price, sl);
   if(!TradingOn())
      return(true);
   double tp   = NormalizeDouble(is_long ? price + InpRR * risk : price - InpRR * risk, _Digits);
   double lots = CalcLots(risk, price);
   if(lots <= 0.0)
      return(true);
   bool ok = is_long ? trade.Buy(lots, _Symbol, price, sl, tp, why) : trade.Sell(lots, _Symbol, price, sl, tp, why);
   if(!ok)
      Print(is_long ? "買單失敗：" : "賣單失敗：", trade.ResultRetcodeDescription());
   return(true);
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
   if(atr[1] == EMPTY_VALUE || atr[1] <= 0.0)
      return;

   double buf = InpSLBufferATR * atr[1];

   //--- 模式 0、1：背離（模式 0 另外要求 RSI 到過極端）
   if(InpEntryMode == ENTRY_DIV_RSI || InpEntryMode == ENTRY_DIV_ONLY)
     {
      int  s2      = 1 + InpPivotRight;     // 剛好在上一根收盤時被確認的擺動點
      bool use_rsi = (InpEntryMode == ENTRY_DIV_RSI);
      if(InpAllowLong && Divergence(lo, ao, rsi, s2, need, true, use_rsi))
         if(Enter(true, lo[s2] - buf, use_rsi ? StringFormat("看漲背離 RSI<=%.0f", InpRSILow) : "看漲背離"))
            return;
      if(InpAllowShort && Divergence(hi, ao, rsi, s2, need, false, use_rsi))
         Enter(false, hi[s2] + buf, use_rsi ? StringFormat("看跌背離 RSI>=%.0f", InpRSIHigh) : "看跌背離");
      return;
     }

   //--- 模式 2、3：停損放在最近 7 根 K 棒（跟擺動點同寬）的高低點外
   int    w        = InpPivotLeft + InpPivotRight + 1;
   double sl_long  = RangeMin(lo, 1, w) - buf;
   double sl_short = RangeMax(hi, 1, w) + buf;

   if(InpEntryMode == ENTRY_RSI_ONLY)     // RSI 剛進入極端區就進場
     {
      double r = rsi[1], r0 = rsi[2];
      if(r == EMPTY_VALUE || r0 == EMPTY_VALUE)
         return;
      if(InpAllowLong && r <= InpRSILow && InpRSILow < r0)
         if(Enter(true, sl_long, StringFormat("RSI 跌破 %.0f", InpRSILow)))
            return;
      if(InpAllowShort && r >= InpRSIHigh && InpRSIHigh > r0)
         Enter(false, sl_short, StringFormat("RSI 突破 %.0f", InpRSIHigh));
      return;
     }

   if(InpEntryMode == ENTRY_RANDOM)       // 隨機進場
     {
      bool   go_long = false;
      double u = BarRandom(iTime(_Symbol, _Period, 1), InpSeed, go_long);
      if(u < InpRandomProb)
        {
         if(go_long && InpAllowLong)
            Enter(true, sl_long, "隨機做多");
         else if(!go_long && InpAllowShort)
            Enter(false, sl_short, "隨機做空");
        }
     }
  }
//+------------------------------------------------------------------+
