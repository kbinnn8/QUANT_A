class AODivergenceRSI(Strategy):
    """AO 背離 + RSI 極端（B 版，逆勢）。
    做多：價格創更低的擺動低點、AO 在對應位置卻比前一個低點高（看漲背離），而且兩個低點之間 RSI 曾經 ≤ 20。
    做空：價格創更高的擺動高點、AO 卻比前一個高點低（看跌背離），而且兩個高點之間 RSI 曾經 ≥ 80。
    擺動點要等右邊 N 根 K 棒走完才能確認，所以最早在確認後下一根開盤進場（不偷看未來）。
    停損放在第二個擺動點外 0.5 倍 ATR，停利 = 停損距離 × 2，每筆風險為淨值的 1%。"""

    params = {
        "pivot_left": 3,        # 擺動點：左邊幾根 K 棒
        "pivot_right": 3,       # 擺動點：右邊幾根 K 棒（確認要等待的 K 棒數）
        "min_gap": 5,           # 兩個擺動點最少相隔幾根
        "max_gap": 60,          # 兩個擺動點最多相隔幾根
        "rsi_period": 14,
        "rsi_low": 20.0,        # 偏多：兩低點之間 RSI 曾經 ≤ 此值
        "rsi_high": 80.0,       # 偏空：兩高點之間 RSI 曾經 ≥ 此值
        "atr_period": 14,
        "sl_buffer_atr": 0.5,   # 停損放在擺動點外 N 倍 ATR
        "rr": 2.0,              # 停利 = 停損距離 × N
        "risk_pct": 1.0,        # 每筆風險（淨值 %）
        "max_size": 30.0,       # 部位上限（淨值倍數，外匯槓桿用）
        "allow_long": True,
        "allow_short": True,
    }

    def init(self):
        median = (self.high + self.low) / 2
        self.ao = self.I(ta.sma(median, 5) - ta.sma(median, 34), "AO", overlay=False)
        self.rsi = ta.rsi(self.close, self.p.rsi_period)
        # ATR 用「真實區間的簡單平均」，跟 MT5 內建 iATR 的算法一樣（ta.atr 是 Wilder 平滑，數值會略有差異）
        prev_close = np.concatenate([[np.nan], self.close[:-1]])
        tr = np.fmax(self.high - self.low, np.fmax(np.abs(self.high - prev_close), np.abs(self.low - prev_close)))
        self.atr = ta.sma(tr, self.p.atr_period)
        self.piv_lo = self.pivots(self.low, True)
        self.piv_hi = self.pivots(self.high, False)

    def pivots(self, x, is_low):
        """第 j 根是擺動低點：比左邊 L 根都低（嚴格），而且不高於右邊 R 根。
        要用到 j 之後 R 根的資料，所以只有在 j + R 根收盤後才能使用（next() 會遵守）。"""
        L, R = self.p.pivot_left, self.p.pivot_right
        n = len(x)
        out = np.zeros(n, dtype=bool)
        for j in range(L, n - R):
            left, right = x[j - L:j], x[j + 1:j + R + 1]
            if is_low:
                out[j] = x[j] < left.min() and x[j] <= right.min()
            else:
                out[j] = x[j] > left.max() and x[j] >= right.max()
        return out

    def previous(self, piv, j2):
        """在 j2 之前、相隔 min_gap 到 max_gap 根的範圍內，最近的一個擺動點。"""
        for j in range(j2 - self.p.min_gap, j2 - self.p.max_gap - 1, -1):
            if j >= 0 and piv[j]:
                return j
        return None

    def next(self):
        i = self.i
        if not self.is_flat:
            return
        j2 = i - self.p.pivot_right            # 剛好在這根收盤時被確認的擺動點
        atr = self.atr[i]
        if j2 < 1 or not np.isfinite(atr):
            return
        entry = self.close[i]                  # 估計的進場價（實際在下一根開盤成交）

        if self.p.allow_long and self.piv_lo[j2]:
            j1 = self.previous(self.piv_lo, j2)
            if (j1 is not None and self.low[j2] < self.low[j1] and self.ao[j2] > self.ao[j1]
                    and np.nanmin(self.rsi[j1:j2 + 1]) <= self.p.rsi_low):
                sl = self.low[j2] - self.p.sl_buffer_atr * atr
                risk = entry - sl
                if risk > 0:
                    size = min(self.p.risk_pct / 100 * entry / risk, self.p.max_size)
                    self.buy(size=size, sl=sl, tp_pct=self.p.rr * risk / entry,
                             tag=f"看漲背離（RSI 曾 ≤ {self.p.rsi_low:g}）")
                    return

        if self.p.allow_short and self.piv_hi[j2]:
            j1 = self.previous(self.piv_hi, j2)
            if (j1 is not None and self.high[j2] > self.high[j1] and self.ao[j2] < self.ao[j1]
                    and np.nanmax(self.rsi[j1:j2 + 1]) >= self.p.rsi_high):
                sl = self.high[j2] + self.p.sl_buffer_atr * atr
                risk = sl - entry
                if risk > 0:
                    size = min(self.p.risk_pct / 100 * entry / risk, self.p.max_size)
                    self.sell(size=size, sl=sl, tp_pct=self.p.rr * risk / entry,
                              tag=f"看跌背離（RSI 曾 ≥ {self.p.rsi_high:g}）")
