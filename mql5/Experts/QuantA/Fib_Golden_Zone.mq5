//+------------------------------------------------------------------+
//| Fib_Golden_Zone.mq5                                              |
//| 費波那契黃金區域回檔（順勢）＋ 對照實驗模式                            |
//|                                                                  |
//| 背景：大週期（預設 H4）收盤在 EMA200 之上只做多、之下只做空              |
//|       （只用已收盤的大週期 K 棒）。                                   |
//| 波段：最近一個確認的擺動高點 B，和它之前最近的擺動低點 A；               |
//|       A→B 要是乾淨的一波（中間沒有更高 / 更低），長度 ≥ 3 倍 ATR。        |
//| 位置：回檔到 0.382–0.618 的黃金區域。                                |
//| 時機：區域內 AO 由紅轉綠（做空：由綠轉紅），收盤還在 0.382 之內才進場。    |
//| 出場：停損 0.786 外 0.2 倍 ATR，停利回到 B；報酬風險比 < 1 不做。        |
//|       每一波只做一次；回檔先碰到 0.786 或先創新高，這一波就作廢。         |
//|                                                                  |
//| 與 QUANT_A 快速測試的 Python 版（fib_golden_zone.py）規則逐條相同。    |
//+------------------------------------------------------------------+
#property copyright   "QUANT_A"
#property version     "1.00"
#property description "費波那契黃金區域回檔（順勢），含對照實驗模式"

#include <Trade\Trade.mqh>
#include <QuantA_Export.mqh>              // ★ QUANT_A

enum ENUM_FIB_MODE
  {
   FIB_FULL      = 0,   // 完整版（趨勢 + 黃金區域 + AO 轉向）
   FIB_NO_TREND  = 1,   // 不看趨勢
   FIB_NO_TRIG   = 2,   // 不等確認（一碰到區域就進）
   FIB_RANDOM    = 3    // 隨機進場（順趨勢方向，沒有優勢的基準）
  };

input group "=== 進場模式（對照實驗）==="
input ENUM_FIB_MODE InpEntryMode   = FIB_FULL; // 進場模式
input double InpRandomProb    = 0.01;     // 隨機模式：每根 K 棒進場的機率
input double InpRandomSLATR   = 1.5;      // 隨機模式：停損幾倍 ATR（停利 = 2 倍停損距離）
input int    InpSeed          = 1;        // 隨機模式：亂數種子

input group "=== 趨勢（大週期）==="
input ENUM_TIMEFRAMES InpHTF  = PERIOD_H4; // 大週期（小於等於圖表週期時，直接用圖表週期）
input int    InpTrendEMA      = 200;      // 大週期 EMA 長度

input group "=== 波段 ==="
input int    InpPivotLeft     = 3;        // 擺動點：左邊幾根
input int    InpPivotRight    = 3;        // 擺動點：右邊幾根（確認要等的 K 棒數）
input int    InpMaxLeg        = 100;      // A 到 B 最多幾根
input double InpMinLegATR     = 3.0;      // 波段長度至少幾倍 ATR
input int    InpMaxWait       = 40;       // B 之後最多等幾根回檔

input group "=== 黃金區域與出場 ==="
input double InpZoneShallow   = 0.382;    // 黃金區域淺的一端
input double InpZoneDeep      = 0.618;    // 黃金區域深的一端
input double InpSLBeyond      = 0.168;    // 停損：深端再過去幾倍波段（0.618 + 0.168 = 0.786）
input double InpSLBufferATR   = 0.2;      // 停損再多留幾倍 ATR
input double InpTPLevel       = 0.0;      // 停利位置（回檔比例）：0 = 回到 B；-0.272 = 1.272 延伸
input double InpMinRR         = 1.0;      // 報酬風險比至少多少才進場
input int    InpATRPeriod     = 14;       // ATR 週期

input group "=== 部位 ==="
input double InpRiskPct       = 1.0;      // 每筆風險（淨值 %）；0 = 用固定手數
input double InpFixedLots     = 0.10;     // 固定手數（InpRiskPct = 0 時使用）
input double InpMaxLeverage   = 30.0;     // 部位上限：名目金額最多為淨值的幾倍
input bool   InpAllowLong     = true;     // 允許做多
input bool   InpAllowShort    = true;     // 允許做空

input group "=== 其他 ==="
input bool   InpEnableTrading = false;    // 實盤自動下單（策略測試器中一律下單）
input ulong  InpMagic         = 20261003; // EA 識別碼

CTrade          trade;
int             hAO  = INVALID_HANDLE;
int             hATR = INVALID_HANDLE;
int             hEMA = INVALID_HANDLE;
ENUM_TIMEFRAMES trend_tf;
datetime        last_bar   = 0;
datetime        used_long  = 0;           // 已經做過的上漲波段（B 的時間）
datetime        used_short = 0;           // 已經做過的下跌波段（B 的時間）

// 找到的波段
struct FibSetup
  {
   int      sb;          // B 的位置（shift）
   datetime tb;          // B 的時間
   double   B;
   double   leg;
   bool     reached;     // 回檔是否已經到過區域淺端
   bool     first_touch; // 是否剛好在上一根第一次碰到
  };

//+------------------------------------------------------------------+
string ModeLabel()
  {
   string s;
   switch(InpEntryMode)
     {
      case FIB_FULL:     s = "完整版";   break;
      case FIB_NO_TREND: s = "不看趨勢"; break;
      case FIB_NO_TRIG:  s = "不等確認"; break;
      case FIB_RANDOM:   return("隨機進場 #" + IntegerToString(InpSeed));
      default:           s = "模式" + IntegerToString((int)InpEntryMode);
     }
   if(MathAbs(InpZoneShallow - 0.382) > 1e-9 || MathAbs(InpZoneDeep - 0.618) > 1e-9)
      s += StringFormat(" 區間 %g–%g", InpZoneShallow, InpZoneDeep);
   return(s);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpPivotLeft < 1 || InpPivotRight < 1 || InpMaxWait <= InpPivotRight || InpMaxLeg < 2 ||
      InpZoneDeep <= InpZoneShallow)
     {
      Print("參數錯誤：請檢查擺動點、等待根數與黃金區域設定");
      return(INIT_PARAMETERS_INCORRECT);
     }
   trend_tf = (PeriodSeconds(InpHTF) > PeriodSeconds(_Period)) ? InpHTF : _Period;
   hAO  = iAO(_Symbol, _Period);
   hATR = iATR(_Symbol, _Period, InpATRPeriod);
   hEMA = iMA(_Symbol, trend_tf, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hAO == INVALID_HANDLE || hATR == INVALID_HANDLE || hEMA == INVALID_HANDLE)
     {
      Print("建立指標失敗，錯誤碼：", GetLastError());
      return(INIT_FAILED);
     }
   trade.SetExpertMagicNumber(InpMagic);

   QA_Init("Fib_Golden_Zone");            // ★ QUANT_A：登記參數（名稱和 Python 版一樣）
   QA_Variant(ModeLabel());
   QA_Param("entry_mode", (int)InpEntryMode);
   QA_Param("htf_hours", PeriodSeconds(InpHTF) / 3600);
   QA_Param("trend_ema", InpTrendEMA);
   QA_Param("pivot_left", InpPivotLeft);
   QA_Param("pivot_right", InpPivotRight);
   QA_Param("max_leg", InpMaxLeg);
   QA_Param("min_leg_atr", InpMinLegATR);
   QA_Param("max_wait", InpMaxWait);
   QA_Param("zone_shallow", InpZoneShallow);
   QA_Param("zone_deep", InpZoneDeep);
   QA_Param("sl_beyond", InpSLBeyond);
   QA_Param("sl_buffer_atr", InpSLBufferATR);
   QA_Param("tp_level", InpTPLevel);
   QA_Param("min_rr", InpMinRR);
   QA_Param("atr_period", InpATRPeriod);
   QA_Param("risk_pct", InpRiskPct);
   QA_Param("max_leverage", InpMaxLeverage);
   QA_Param("random_prob", InpRandomProb);
   QA_Param("random_sl_atr", InpRandomSLATR);
   QA_Param("seed", InpSeed);
   QA_Param("allow_long", InpAllowLong);
   QA_Param("allow_short", InpAllowShort);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(hAO  != INVALID_HANDLE) IndicatorRelease(hAO);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hEMA != INVALID_HANDLE) IndicatorRelease(hEMA);
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

// 大週期趨勢：最後一根「已收盤」的大週期 K 棒，收盤在 EMA 之上 = +1，之下 = -1
int Trend()
  {
   double e[];
   if(CopyBuffer(hEMA, 0, 1, 1, e) != 1 || e[0] == EMPTY_VALUE || e[0] <= 0.0)
      return(0);
   double c = iClose(_Symbol, trend_tf, 1);
   if(c <= 0.0)
      return(0);
   if(c > e[0]) return(1);
   if(c < e[0]) return(-1);
   return(0);
  }

// 陣列為時間序列（索引 0 = 正在形成的 K 棒，1 = 剛收盤，數字越大越舊）
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

// 回檔 r 的價位：做多（上漲波段）往下算，做空往上算
double Lvl(const FibSetup &st, bool up, double r)
  {
   return(up ? st.B - r * st.leg : st.B + r * st.leg);
  }

// 找出目前有效的波段；up = true：A 低 → B 高（等回檔做多）
bool FindSetup(const double &lo[], const double &hi[], const double &atr[], int n, bool up, FibSetup &st)
  {
   //--- B：最近一個確認的擺動點（右邊 R 根已收盤），最多往回找 InpMaxWait 根
   int sb = -1;
   for(int s = 1 + InpPivotRight; s <= 1 + InpMaxWait; s++)
      if(up ? IsPivot(hi, s, n, false) : IsPivot(lo, s, n, true))
        {
         sb = s;
         break;
        }
   if(sb < 0)
      return(false);
   datetime tb = iTime(_Symbol, _Period, sb);
   if(tb == (up ? used_long : used_short))
      return(false);                      // 這一波已經做過

   //--- A：B 之前最近的反向擺動點
   int sa = -1;
   for(int s = sb + 1; s <= sb + InpMaxLeg; s++)
      if(up ? IsPivot(lo, s, n, true) : IsPivot(hi, s, n, false))
        {
         sa = s;
         break;
        }
   if(sa < 0)
      return(false);

   double A = up ? lo[sa] : hi[sa];
   double B = up ? hi[sb] : lo[sb];
   //--- 乾淨的一波：A 到 B 之間沒有比 B 更極端、也沒有比 A 更極端的價格
   for(int s = sb; s <= sa; s++)
     {
      if(up && (hi[s] > B || lo[s] < A))
         return(false);
      if(!up && (lo[s] < B || hi[s] > A))
         return(false);
     }
   double leg = MathAbs(B - A);
   if(atr[sb] == EMPTY_VALUE || atr[sb] <= 0.0 || leg < InpMinLegATR * atr[sb])
      return(false);

   st.sb  = sb;
   st.tb  = tb;
   st.B   = B;
   st.leg = leg;

   //--- B 之後的走勢（shift sb-1 到 1）
   double extreme = up ? DBL_MAX : -DBL_MAX;
   double prev_extreme = up ? DBL_MAX : -DBL_MAX;    // 不含剛收盤那一根
   for(int s = sb - 1; s >= 1; s--)
     {
      if(up && hi[s] > B)
         return(false);                   // 先創新高：這一波還沒結束
      if(!up && lo[s] < B)
         return(false);
      double v = up ? lo[s] : hi[s];
      extreme = up ? MathMin(extreme, v) : MathMax(extreme, v);
      if(s >= 2)
         prev_extreme = up ? MathMin(prev_extreme, v) : MathMax(prev_extreme, v);
     }
   double shallow = Lvl(st, up, InpZoneShallow);
   double stop    = Lvl(st, up, InpZoneDeep + InpSLBeyond);
   if(up ? extreme < stop : extreme > stop)
      return(false);                      // 已經回到停損位置：這一波作廢
   st.reached     = up ? extreme <= shallow : extreme >= shallow;
   st.first_touch = st.reached && (up ? prev_extreme > shallow : prev_extreme < shallow);
   return(true);
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
      double notional_per_lot = price / ts * tv;
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

// 下單；回傳 true = 訊號有效（風險、報酬風險比都符合），不論實際有沒有下單
// ref = 剛收盤那根的收盤價：報酬風險比用它判斷（和 Python 版相同，決策發生在收盤時）
bool Enter(bool up, double sl, double tp, string why, datetime setup_time, double ref)
  {
   double price  = up ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);
   double ref_risk   = up ? ref - sl : sl - ref;
   double ref_reward = up ? tp - ref : ref - tp;
   if(ref_risk <= 0.0 || ref_reward <= 0.0 || ref_reward / ref_risk < InpMinRR)
      return(false);
   double risk   = up ? price - sl : sl - price;      // 實際成交價的風險（算手數用）
   double reward = up ? tp - price : price - tp;
   if(risk <= 0.0 || reward <= 0.0)
     {
      Print("開盤價已經越過停損或停利，略過這個訊號");
      return(false);
     }
   if(setup_time > 0)
     {
      if(up) used_long = setup_time;
      else   used_short = setup_time;
     }
   string tag = why + StringFormat("（%.1fR）", reward / risk);
   PrintFormat("%s 訊號：%s，價格 %.5f，停損 %.5f，停利 %.5f", ModeLabel(), tag, price, sl, tp);
   if(!TradingOn())
      return(true);
   double lots = CalcLots(risk, price);
   if(lots <= 0.0)
      return(true);
   bool ok = up ? trade.Buy(lots, _Symbol, price, sl, tp, tag) : trade.Sell(lots, _Symbol, price, sl, tp, tag);
   if(!ok)
      Print(up ? "買單失敗：" : "賣單失敗：", trade.ResultRetcodeDescription());
   return(true);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   QA_OnTick();                           // ★ QUANT_A：記錄淨值

   datetime bar = iTime(_Symbol, _Period, 0);
   if(bar == last_bar)
      return;

   int need = 1 + InpPivotRight + InpMaxWait + InpMaxLeg + InpPivotLeft + 3;
   double lo[], hi[], cl[], ao[], atr[];
   ArraySetAsSeries(lo, true);
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(cl, true);
   ArraySetAsSeries(ao, true);
   ArraySetAsSeries(atr, true);
   if(CopyLow(_Symbol, _Period, 0, need, lo) != need) return;
   if(CopyHigh(_Symbol, _Period, 0, need, hi) != need) return;
   if(CopyClose(_Symbol, _Period, 0, need, cl) != need) return;
   if(CopyBuffer(hAO, 0, 0, 4, ao) != 4) return;
   if(CopyBuffer(hATR, 0, 0, need, atr) != need) return;
   last_bar = bar;

   if(HasMyPosition())
      return;                             // 一次只持有一個部位，出場只靠停損 / 停利
   if(atr[1] == EMPTY_VALUE || atr[1] <= 0.0)
      return;

   int trend = Trend();

   //--- 隨機進場：順著大週期趨勢方向
   if(InpEntryMode == FIB_RANDOM)
     {
      bool   dummy = false;
      double u = BarRandom(iTime(_Symbol, _Period, 1), InpSeed, dummy);
      if(trend == 0 || u >= InpRandomProb)
         return;
      bool up = trend > 0;
      if((up && !InpAllowLong) || (!up && !InpAllowShort))
         return;
      double dist = InpRandomSLATR * atr[1];
      if(up)
         Enter(true, cl[1] - dist, cl[1] + 2.0 * dist, "隨機做多", 0, cl[1]);
      else
         Enter(false, cl[1] + dist, cl[1] - 2.0 * dist, "隨機做空", 0, cl[1]);
      return;
     }

   //--- 黃金區域：先看做多，再看做空
   for(int k = 0; k < 2; k++)
     {
      bool up = (k == 0);
      if((up && !InpAllowLong) || (!up && !InpAllowShort))
         continue;
      if(InpEntryMode != FIB_NO_TREND && trend != (up ? 1 : -1))
         continue;                        // 趨勢過濾
      FibSetup st;
      if(!FindSetup(lo, hi, atr, need, up, st))
         continue;

      bool go;
      if(InpEntryMode == FIB_NO_TRIG)     // 不等確認：第一次碰到區域就進
         go = st.first_touch;
      else                                // AO 轉向，而且收盤還在區域淺端之內
        {
         bool turn   = up ? (ao[1] > ao[2] && ao[2] <= ao[3]) : (ao[1] < ao[2] && ao[2] >= ao[3]);
         double sh   = Lvl(st, up, InpZoneShallow);
         bool inside = up ? cl[1] <= sh : cl[1] >= sh;
         go = st.reached && turn && inside;
        }
      if(!go)
         continue;

      double sl_lvl = Lvl(st, up, InpZoneDeep + InpSLBeyond);
      double sl     = up ? sl_lvl - InpSLBufferATR * atr[1] : sl_lvl + InpSLBufferATR * atr[1];
      double tp     = Lvl(st, up, InpTPLevel);
      string why    = (up ? "黃金區域做多" : "黃金區域做空") + (InpEntryMode == FIB_NO_TRIG ? "（碰到就進）" : "");
      if(Enter(up, sl, tp, why, st.tb, cl[1]))
         return;
     }
  }
//+------------------------------------------------------------------+
