//+------------------------------------------------------------------+
//| QuantA_Export.mqh                                                |
//| 回測結束時，把結果輸出成 QUANT_A app 讀得懂的 JSON 檔。               |
//|                                                                  |
//| 用法（在你的 EA 裡加 4 行）：                                        |
//|   #include <QuantA_Export.mqh>        // 放在檔案最上面              |
//|   OnInit()  裡： QA_Init("EA名稱");  QA_Param("參數名", 參數);  ...  |
//|   OnTick()  第一行： QA_OnTick();                                  |
//|   OnTester() 裡： QA_Export();                                     |
//|                                                                  |
//| 輸出位置：所有終端機共用的資料夾                                       |
//|   %APPDATA%\MetaQuotes\Terminal\Common\Files\QuantA\              |
//| 電腦上的上傳小程式會監看這個資料夾，自動上傳到 GitHub。                   |
//+------------------------------------------------------------------+
#ifndef QUANTA_EXPORT_MQH
#define QUANTA_EXPORT_MQH

input bool QA_ExportEnabled = true;   // QuantA：回測結束時輸出結果

#define QA_FOLDER     "QuantA"
#define QA_MAX_POINTS 20000

//--- 狀態
string   qa_ea_name    = "";
double   qa_init_cash  = 0.0;
bool     qa_inited     = false;
bool     qa_exported   = false;
datetime qa_last_bar   = 0;
int      qa_n          = 0;
datetime qa_eq_t[];
double   qa_eq_v[];
double   qa_bal_v[];
string   qa_params     = "";   // 已經組好的 "名稱":值, ...

//--- 持倉重建用
struct QAPos
  {
   ulong    id;
   string   symbol;
   int      dir;          // +1 多、-1 空
   double   vol_in;       // 累計進場手數
   double   vol_open;     // 尚未平倉手數
   double   vol_out;      // 累計出場手數
   datetime t_in;
   datetime t_out;
   double   p_in;         // 平均進場價
   double   p_out_sum;    // Σ 出場價 × 手數
   double   profit;       // Σ 成交損益
   double   comm;         // Σ 手續費 + 費用（MT5 為負數）
   double   swap;         // Σ 隔夜利息
   string   tag;          // 進場註解
   string   reason;       // 出場原因
  };

//+------------------------------------------------------------------+
//| 小工具                                                            |
//+------------------------------------------------------------------+
string QA_Esc(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   StringReplace(s, "\t", " ");
   return s;
  }

string QA_Time(datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d", d.year, d.mon, d.day, d.hour, d.min, d.sec);
  }

string QA_Num(double v)
  {
   if(!MathIsValidNumber(v))
      return "null";
   string s = DoubleToString(v, 8);
   int len = StringLen(s);
   while(len > 1 && StringGetCharacter(s, len - 1) == '0')
      len--;
   if(len > 0 && StringGetCharacter(s, len - 1) == '.')
      len--;
   return StringSubstr(s, 0, len);
  }

string QA_Str(string s) { return "\"" + QA_Esc(s) + "\""; }

string QA_TF()
  {
   string tf = EnumToString(_Period);
   StringReplace(tf, "PERIOD_", "");
   return tf;
  }

void QA_AddParam(string name, string json_value)
  {
   if(qa_params != "")
      qa_params += ", ";
   qa_params += QA_Str(name) + ": " + json_value;
  }

//--- 記錄 EA 參數（MQL5 沒辦法自動讀 input，所以要手動登記）
void QA_Param(string name, int v)    { QA_AddParam(name, IntegerToString(v)); }
void QA_Param(string name, long v)   { QA_AddParam(name, IntegerToString(v)); }
void QA_Param(string name, double v) { QA_AddParam(name, QA_Num(v)); }
void QA_Param(string name, bool v)   { QA_AddParam(name, v ? "true" : "false"); }
void QA_Param(string name, string v) { QA_AddParam(name, QA_Str(v)); }

//+------------------------------------------------------------------+
//| 初始化：在 OnInit() 呼叫                                            |
//+------------------------------------------------------------------+
void QA_Init(string ea_name = "")
  {
   qa_ea_name   = (ea_name == "") ? MQLInfoString(MQL_PROGRAM_NAME) : ea_name;
   qa_init_cash = AccountInfoDouble(ACCOUNT_BALANCE);
   qa_n         = 0;
   qa_last_bar  = 0;
   qa_exported  = false;
   ArrayResize(qa_eq_t, 0, 100000);
   ArrayResize(qa_eq_v, 0, 100000);
   ArrayResize(qa_bal_v, 0, 100000);
   qa_inited = true;
  }

//+------------------------------------------------------------------+
//| 每個 tick：在 OnTick() 第一行呼叫（每根新 K 棒記一次淨值）              |
//+------------------------------------------------------------------+
void QA_OnTick()
  {
   if(!qa_inited)
      QA_Init();
   datetime bt = iTime(_Symbol, _Period, 0);
   if(bt == 0 || bt == qa_last_bar)
      return;
   qa_last_bar = bt;
   int k = qa_n;
   ArrayResize(qa_eq_t, k + 1, 100000);
   ArrayResize(qa_eq_v, k + 1, 100000);
   ArrayResize(qa_bal_v, k + 1, 100000);
   qa_eq_t[k]  = bt;
   qa_eq_v[k]  = AccountInfoDouble(ACCOUNT_EQUITY);
   qa_bal_v[k] = AccountInfoDouble(ACCOUNT_BALANCE);
   qa_n = k + 1;
  }

//+------------------------------------------------------------------+
//| 從成交紀錄（deals）重建每一筆交易                                      |
//+------------------------------------------------------------------+
int QA_Find(QAPos &pos[], int n, ulong id)
  {
   for(int i = 0; i < n; i++)
      if(pos[i].id == id)
         return i;
   return -1;
  }

string QA_Reason(long r)
  {
   if(r == DEAL_REASON_SL)
      return "停損";
   if(r == DEAL_REASON_TP)
      return "停利";
   if(r == DEAL_REASON_SO)
      return "強制平倉";
   if(r == DEAL_REASON_EXPERT)
      return "EA 平倉";
   return "其他";
  }

double QA_Notional(string sym, double lots, double price)
  {
   // 名目金額（帳戶幣別）= 手數 × 價格 × 每一價格單位的價值
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(ts <= 0.0 || tv <= 0.0)
      return lots * SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE) * price;
   return lots * price * tv / ts;
  }

string QA_TradeJson(QAPos &p, double &balance)
  {
   double p_out    = (p.vol_out > 0.0) ? p.p_out_sum / p.vol_out : p.p_in;
   double pnl      = p.profit + p.comm + p.swap;
   double contract = SymbolInfoDouble(p.symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double notional = QA_Notional(p.symbol, p.vol_in, p.p_in);
   int    bars     = iBarShift(p.symbol, _Period, p.t_in) - iBarShift(p.symbol, _Period, p.t_out);
   balance += pnl;
   string j = "{";
   j += "\"方向\": " + QA_Str(p.dir > 0 ? "多" : "空");
   j += ", \"數量\": " + QA_Num(p.vol_in * contract);
   j += ", \"手數\": " + QA_Num(p.vol_in);
   j += ", \"進場時間\": " + QA_Str(QA_Time(p.t_in));
   j += ", \"進場價\": " + QA_Num(p.p_in);
   j += ", \"出場時間\": " + QA_Str(QA_Time(p.t_out));
   j += ", \"出場價\": " + QA_Num(p_out);
   j += ", \"損益\": " + QA_Num(pnl);
   j += ", \"報酬率\": " + QA_Num(notional > 0.0 ? pnl / notional : 0.0);
   j += ", \"手續費\": " + QA_Num(-p.comm);
   j += ", \"隔夜利息\": " + QA_Num(p.swap);
   j += ", \"名目金額\": " + QA_Num(notional);
   j += ", \"持有K棒\": " + IntegerToString(MathMax(bars, 0));
   j += ", \"進場標籤\": " + QA_Str(p.tag);
   j += ", \"出場原因\": " + QA_Str(p.reason);
   j += ", \"商品\": " + QA_Str(p.symbol);
   j += ", \"餘額\": " + QA_Num(balance);
   j += "}";
   return j;
  }

void QA_CopyPos(QAPos &d, const QAPos &s)
  {
   d.id = s.id;           d.symbol = s.symbol;     d.dir = s.dir;
   d.vol_in = s.vol_in;   d.vol_open = s.vol_open; d.vol_out = s.vol_out;
   d.t_in = s.t_in;       d.t_out = s.t_out;       d.p_in = s.p_in;
   d.p_out_sum = s.p_out_sum; d.profit = s.profit; d.comm = s.comm;
   d.swap = s.swap;       d.tag = s.tag;           d.reason = s.reason;
  }

void QA_Remove(QAPos &pos[], int &n, int k)
  {
   if(k != n - 1)
      QA_CopyPos(pos[k], pos[n - 1]);
   n--;
  }

int QA_BuildTrades(string &out[])
  {
   ArrayResize(out, 0, 1000);
   if(!HistorySelect(0, TimeCurrent() + 86400))
      return 0;
   QAPos pos[];
   ArrayResize(pos, 0, 64);
   int n_pos = 0, n_out = 0;
   double balance = qa_init_cash;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0)
         continue;
      long type = HistoryDealGetInteger(tk, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;                                   // 略過入金、信用額等
      long     entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
      ulong    pid   = (ulong)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      double   vol   = HistoryDealGetDouble(tk, DEAL_VOLUME);
      double   price = HistoryDealGetDouble(tk, DEAL_PRICE);
      double   prof  = HistoryDealGetDouble(tk, DEAL_PROFIT);
      double   cost  = HistoryDealGetDouble(tk, DEAL_COMMISSION) + HistoryDealGetDouble(tk, DEAL_FEE);
      double   swp   = HistoryDealGetDouble(tk, DEAL_SWAP);
      datetime t     = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
      string   sym   = HistoryDealGetString(tk, DEAL_SYMBOL);
      string   cmt   = HistoryDealGetString(tk, DEAL_COMMENT);
      int      dir   = (type == DEAL_TYPE_BUY) ? 1 : -1;
      int      k     = QA_Find(pos, n_pos, pid);

      double open_vol = vol;
      if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY || entry == DEAL_ENTRY_INOUT)
        {
         if(k >= 0)
           {
            double close_vol = (entry == DEAL_ENTRY_INOUT) ? pos[k].vol_open : MathMin(vol, pos[k].vol_open);
            pos[k].p_out_sum += price * close_vol;
            pos[k].vol_out   += close_vol;
            pos[k].vol_open  -= close_vol;
            pos[k].t_out      = t;
            pos[k].profit    += prof;
            pos[k].comm      += cost;
            pos[k].swap      += swp;
            pos[k].reason     = (entry == DEAL_ENTRY_INOUT) ? "反手" : QA_Reason(HistoryDealGetInteger(tk, DEAL_REASON));
            open_vol = vol - close_vol;
            if(pos[k].vol_open <= 1e-8)
              {
               ArrayResize(out, n_out + 1, 1000);
               out[n_out++] = QA_TradeJson(pos[k], balance);
               QA_Remove(pos, n_pos, k);
               k = -1;
              }
           }
         if(entry != DEAL_ENTRY_INOUT || open_vol <= 1e-8)
            continue;
         prof = 0.0;   // 反手後新部位的損益從 0 開始
         cost = 0.0;
         swp  = 0.0;
        }
      // 進場（或反手後的新部位）
      if(k < 0)
        {
         ArrayResize(pos, n_pos + 1, 64);
         pos[n_pos].id        = pid;
         pos[n_pos].symbol    = sym;
         pos[n_pos].dir       = dir;
         pos[n_pos].vol_in    = open_vol;
         pos[n_pos].vol_open  = open_vol;
         pos[n_pos].vol_out   = 0.0;
         pos[n_pos].t_in      = t;
         pos[n_pos].t_out     = t;
         pos[n_pos].p_in      = price;
         pos[n_pos].p_out_sum = 0.0;
         pos[n_pos].profit    = prof;
         pos[n_pos].comm      = cost;
         pos[n_pos].swap      = swp;
         pos[n_pos].tag       = cmt;
         pos[n_pos].reason    = "";
         n_pos++;
        }
      else
        {
         // 加碼：進場價取加權平均
         double v0 = pos[k].vol_in;
         pos[k].p_in      = (pos[k].p_in * v0 + price * open_vol) / (v0 + open_vol);
         pos[k].vol_in   += open_vol;
         pos[k].vol_open += open_vol;
         pos[k].comm     += cost;
        }
     }
   if(n_pos > 0)
      PrintFormat("QuantA：有 %d 個部位在回測結束時尚未平倉，未列入交易紀錄（淨值曲線已包含）", n_pos);
   return n_out;
  }

//+------------------------------------------------------------------+
//| 輸出：在 OnTester() 呼叫                                           |
//+------------------------------------------------------------------+
bool QA_Export()
  {
   if(!QA_ExportEnabled || qa_exported)
      return false;
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION))
      return false;                                  // 只在單次回測輸出（最佳化會產生上千個檔案）
   if(!qa_inited)
      QA_Init();
   qa_exported = true;

   string trades[];
   int n_tr = QA_BuildTrades(trades);

   //--- 最後補一個淨值點
   int k = qa_n;
   ArrayResize(qa_eq_t, k + 1);
   ArrayResize(qa_eq_v, k + 1);
   ArrayResize(qa_bal_v, k + 1);
   qa_eq_t[k]  = TimeCurrent();
   qa_eq_v[k]  = AccountInfoDouble(ACCOUNT_EQUITY);
   qa_bal_v[k] = AccountInfoDouble(ACCOUNT_BALANCE);
   if(k > 0 && qa_eq_t[k] <= qa_eq_t[k - 1])
      qa_eq_t[k] = qa_eq_t[k - 1] + 1;
   qa_n = k + 1;

   FolderCreate(QA_FOLDER, FILE_COMMON);
   MathSrand(GetTickCount());
   string base = qa_ea_name + "_" + _Symbol + "_" + QA_TF() + "_" + IntegerToString((long)GetTickCount())
                 + "_" + IntegerToString(MathRand());
   StringReplace(base, " ", "_");
   StringReplace(base, "/", "-");
   StringReplace(base, "\\", "-");
   string tmp_name = QA_FOLDER + "\\" + base + ".tmp";
   string fin_name = QA_FOLDER + "\\" + base + ".json";

   int h = FileOpen(tmp_name, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON, 0, CP_UTF8);
   if(h == INVALID_HANDLE)
     {
      Print("QuantA：無法建立輸出檔，錯誤碼 ", GetLastError());
      return false;
     }

   string name = qa_ea_name + " · " + _Symbol + " · " + QA_TF();
   FileWriteString(h, "{\"version\": 1, \"id\": \"\", \"created\": \"\", \"source\": \"mt5\"");
   FileWriteString(h, ", \"name\": " + QA_Str(name) + ", \"ea\": " + QA_Str(qa_ea_name));
   FileWriteString(h, ", \"symbol\": " + QA_Str(_Symbol) + ", \"timeframe\": " + QA_Str(QA_TF()));
   FileWriteString(h, ", \"cash\": " + QA_Num(qa_init_cash));
   FileWriteString(h, ", \"params\": {" + qa_params + "}");

   string settings = "\"公司\": " + QA_Str(AccountInfoString(ACCOUNT_COMPANY));
   settings += ", \"伺服器\": " + QA_Str(AccountInfoString(ACCOUNT_SERVER));
   settings += ", \"帳戶幣別\": " + QA_Str(AccountInfoString(ACCOUNT_CURRENCY));
   settings += ", \"槓桿\": " + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE));
   settings += ", \"帳戶模式\": " + QA_Str(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "對沖" : "淨部位");
   settings += ", \"合約大小\": " + QA_Num(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE));
   settings += ", \"小數位數\": " + IntegerToString(_Digits);
   settings += ", \"最終淨值\": " + QA_Num(AccountInfoDouble(ACCOUNT_EQUITY));
   FileWriteString(h, ", \"settings\": {" + settings + "}");

   //--- 淨值曲線（太長就抽樣）
   int step = (qa_n > QA_MAX_POINTS) ? (int)MathCeil((double)qa_n / QA_MAX_POINTS) : 1;
   bool first = true;
   FileWriteString(h, ", \"equity\": {\"t\": [");
   for(int i = 0; i < qa_n; i++)
     {
      if(i % step != 0 && i != qa_n - 1)
         continue;
      FileWriteString(h, (first ? "" : ", ") + QA_Str(QA_Time(qa_eq_t[i])));
      first = false;
     }
   FileWriteString(h, "], \"v\": [");
   first = true;
   for(int i = 0; i < qa_n; i++)
     {
      if(i % step != 0 && i != qa_n - 1)
         continue;
      FileWriteString(h, (first ? "" : ", ") + QA_Num(qa_eq_v[i]));
      first = false;
     }
   FileWriteString(h, "]}, \"balance\": [");
   first = true;
   for(int i = 0; i < qa_n; i++)
     {
      if(i % step != 0 && i != qa_n - 1)
         continue;
      FileWriteString(h, (first ? "" : ", ") + QA_Num(qa_bal_v[i]));
      first = false;
     }
   FileWriteString(h, "], \"trades\": [");
   for(int i = 0; i < n_tr; i++)
      FileWriteString(h, (i == 0 ? "" : ", ") + trades[i]);
   FileWriteString(h, "]}");
   FileClose(h);

   //--- 寫完才改名，避免上傳小程式讀到寫到一半的檔案
   if(!FileMove(tmp_name, FILE_COMMON, fin_name, FILE_COMMON | FILE_REWRITE))
     {
      Print("QuantA：改名失敗，錯誤碼 ", GetLastError());
      return false;
     }
   PrintFormat("QuantA：已輸出 %d 筆交易、%d 個淨值點 → Common\\Files\\%s", n_tr, qa_n, fin_name);
   return true;
  }

#endif // QUANTA_EXPORT_MQH
