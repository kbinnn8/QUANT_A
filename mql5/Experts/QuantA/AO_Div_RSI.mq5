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
//| 多商品：在「商品清單」填 EURUSD,GBPUSD,… 就會在同一次測試裡，           |
//| 對每個商品各自套用同一套規則（共用一個帳戶）；空白 = 只跑圖表商品。      |
//|                                                                  |
//| 與 Python 參考版（ao_divergence_rsi.py）規則逐條相同，                 |
//| 隨機進場用同一個雜湊公式：同一根 K 棒、同一個種子會得到同一個亂數。      |
//+------------------------------------------------------------------+
#property copyright   "QUANT_A"
#property version     "1.20"
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

input group "=== 商品 ==="
input string InpSymbols       = "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD"; // 商品清單（逗號分隔；空白 = 只跑圖表商品）
input int    InpMaxOpen       = 0;        // 所有商品合計最多同時幾筆部位（0 = 不限）

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
input string InpNote          = "";       // 備註：這次改了什麼（會顯示在研究紀錄）

// 每個商品各自的指標與狀態
struct SymState
  {
   string   name;
   int      hAO;
   int      hRSI;
   int      hATR;
   datetime last_bar;
  };

CTrade   trade;
SymState S[];
int      nsym = 0;

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
   if(!SetupSymbols())
      return(INIT_FAILED);
   trade.SetExpertMagicNumber(InpMagic);
   EventSetTimer(60);                     // 非圖表商品也能準時檢查新 K 棒

   QA_Init("AO_Div_RSI");                 // ★ QUANT_A：登記參數（名稱和 Python 版一樣）
   QA_Variant(ModeLabel());
   QA_Note(InpNote);
   if(nsym > 1)
      QA_SymbolLabel(IntegerToString(nsym) + " 個商品");
   QA_Param("symbols", SymbolList());
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
   EventKillTimer();
   for(int i = 0; i < nsym; i++)
     {
      if(S[i].hAO  != INVALID_HANDLE) IndicatorRelease(S[i].hAO);
      if(S[i].hRSI != INVALID_HANDLE) IndicatorRelease(S[i].hRSI);
      if(S[i].hATR != INVALID_HANDLE) IndicatorRelease(S[i].hATR);
     }
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

// 解析商品清單並建立每個商品的指標；找不到的商品會試著加上圖表商品的後綴（例如 EURUSD → EURUSD#）
bool SetupSymbols()
  {
   string list[];
   int n = 0;
   if(StringLen(InpSymbols) > 0)
      n = StringSplit(InpSymbols, ',', list);
   if(n <= 0)
     {
      ArrayResize(list, 1);
      list[0] = _Symbol;
      n = 1;
     }
   string suffix = (StringLen(_Symbol) > 6) ? StringSubstr(_Symbol, 6) : "";
   ArrayResize(S, 0);
   nsym = 0;
   for(int k = 0; k < n; k++)
     {
      string name = list[k];
      StringTrimLeft(name);
      StringTrimRight(name);
      if(name == "")
         continue;
      if(!SymbolSelect(name, true))
        {
         if(suffix != "" && SymbolSelect(name + suffix, true))
            name = name + suffix;
         else
           {
            Print("找不到商品，略過：", name);
            continue;
           }
        }
      bool dup = false;
      for(int j = 0; j < nsym; j++)
         if(S[j].name == name)
            dup = true;
      if(dup)
         continue;
      ArrayResize(S, nsym + 1);
      S[nsym].name     = name;
      S[nsym].hAO      = iAO(name, _Period);
      S[nsym].hRSI     = iRSI(name, _Period, InpRSIPeriod, PRICE_CLOSE);
      S[nsym].hATR     = iATR(name, _Period, InpATRPeriod);
      S[nsym].last_bar = 0;
      if(S[nsym].hAO == INVALID_HANDLE || S[nsym].hRSI == INVALID_HANDLE || S[nsym].hATR == INVALID_HANDLE)
        {
         Print("建立指標失敗：", name, "，錯誤碼：", GetLastError());
         return(false);
        }
      nsym++;
     }
   if(nsym == 0)
     {
      Print("商品清單裡沒有可用的商品");
      return(false);
     }
   PrintFormat("AO_Div_RSI：%d 個商品（%s），週期 %s", nsym, SymbolList(), EnumToString(_Period));
   return(true);
  }

string SymbolList()
  {
   string s = "";
   for(int i = 0; i < nsym; i++)
      s += (i > 0 ? "," : "") + S[i].name;
   return(s);
  }

bool HasMyPosition(string sym)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == sym && (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return(true);
     }
   return(false);
  }

int CountMyPositions()
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) == InpMagic)
         c++;
     }
   return(c);
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
double CalcLots(string sym, double risk_price, double price)
  {
   double vmin  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double tv    = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double ts    = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
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
      Print(sym, "：算出的手數低於最小手數，略過這個訊號");
      return(0.0);
     }
   int vdig = (vstep > 0.0) ? (int)MathMax(0.0, MathCeil(-MathLog10(vstep) - 1e-9)) : 2;
   return(NormalizeDouble(MathMin(lots, vmax), vdig));
  }

// 下單；回傳 true = 這個訊號有效（風險 > 0），不論實際有沒有下單
bool Enter(string sym, bool is_long, double sl, string why)
  {
   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double price  = is_long ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   sl = NormalizeDouble(sl, digits);
   double risk = is_long ? price - sl : sl - price;
   if(risk <= 0.0)
      return(false);
   PrintFormat("%s %s 訊號：%s，價格 %.5f，停損 %.5f", sym, ModeLabel(), why, price, sl);
   if(!TradingOn())
      return(true);
   double tp   = NormalizeDouble(is_long ? price + InpRR * risk : price - InpRR * risk, digits);
   double lots = CalcLots(sym, risk, price);
   if(lots <= 0.0)
      return(true);
   bool ok = is_long ? trade.Buy(lots, sym, price, sl, tp, why) : trade.Sell(lots, sym, price, sl, tp, why);
   if(!ok)
      Print(sym, is_long ? " 買單失敗：" : " 賣單失敗：", trade.ResultRetcodeDescription());
   return(true);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   QA_OnTick();                           // ★ QUANT_A：記錄淨值
   for(int i = 0; i < nsym; i++)
      ProcessSymbol(i);
  }

void OnTimer()
  {
   for(int i = 0; i < nsym; i++)
      ProcessSymbol(i);
  }

//+------------------------------------------------------------------+
//| 一個商品：只在它自己的新 K 棒開盤時判斷一次                            |
//+------------------------------------------------------------------+
void ProcessSymbol(int i)
  {
   string   sym = S[i].name;
   datetime bar = iTime(sym, _Period, 0);
   if(bar == 0 || bar == S[i].last_bar)
      return;

   int need = 1 + InpPivotRight + InpMaxGap + InpPivotLeft + 2;
   double lo[], hi[], ao[], rsi[], atr[];
   ArraySetAsSeries(lo, true);
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(ao, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   if(CopyLow(sym, _Period, 0, need, lo) != need) return;
   if(CopyHigh(sym, _Period, 0, need, hi) != need) return;
   if(CopyBuffer(S[i].hAO, 0, 0, need, ao) != need) return;
   if(CopyBuffer(S[i].hRSI, 0, 0, need, rsi) != need) return;
   if(CopyBuffer(S[i].hATR, 0, 0, 2, atr) != 2) return;
   S[i].last_bar = bar;

   if(HasMyPosition(sym))
      return;                             // 每個商品一次只持有一個部位，出場只靠停損 / 停利
   if(InpMaxOpen > 0 && CountMyPositions() >= InpMaxOpen)
      return;
   if(atr[1] == EMPTY_VALUE || atr[1] <= 0.0)
      return;

   double buf = InpSLBufferATR * atr[1];

   //--- 模式 0、1：背離（模式 0 另外要求 RSI 到過極端）
   if(InpEntryMode == ENTRY_DIV_RSI || InpEntryMode == ENTRY_DIV_ONLY)
     {
      int  s2      = 1 + InpPivotRight;     // 剛好在上一根收盤時被確認的擺動點
      bool use_rsi = (InpEntryMode == ENTRY_DIV_RSI);
      if(InpAllowLong && Divergence(lo, ao, rsi, s2, need, true, use_rsi))
         if(Enter(sym, true, lo[s2] - buf, use_rsi ? StringFormat("看漲背離 RSI<=%.0f", InpRSILow) : "看漲背離"))
            return;
      if(InpAllowShort && Divergence(hi, ao, rsi, s2, need, false, use_rsi))
         Enter(sym, false, hi[s2] + buf, use_rsi ? StringFormat("看跌背離 RSI>=%.0f", InpRSIHigh) : "看跌背離");
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
         if(Enter(sym, true, sl_long, StringFormat("RSI 跌破 %.0f", InpRSILow)))
            return;
      if(InpAllowShort && r >= InpRSIHigh && InpRSIHigh > r0)
         Enter(sym, false, sl_short, StringFormat("RSI 突破 %.0f", InpRSIHigh));
      return;
     }

   if(InpEntryMode == ENTRY_RANDOM)       // 隨機進場
     {
      bool   go_long = false;
      double u = BarRandom(iTime(sym, _Period, 1), InpSeed, go_long);
      if(u < InpRandomProb)
        {
         if(go_long && InpAllowLong)
            Enter(sym, true, sl_long, "隨機做多");
         else if(!go_long && InpAllowShort)
            Enter(sym, false, sl_short, "隨機做空");
        }
     }
  }
//+------------------------------------------------------------------+
