class AODivergenceRSI(Strategy):
    """AO 背離 + RSI 極端（B 版，逆勢）。
    做多：價格創更低的擺動低點、AO 在對應位置卻比前一個低點高（看漲背離），而且兩個低點之間 RSI 曾經 ≤ 20。
    做空：價格創更高的擺動高點、AO 卻比前一個高點低（看跌背離），而且兩個高點之間 RSI 曾經 ≥ 80。
    擺動點要等右邊 N 根 K 棒走完才能確認，所以最早在確認後下一根開盤進場（不偷看未來）。
    停損放在擺動點外 0.5 倍 ATR，停利 = 停損距離 × 2，每筆風險為淨值的 1%。
    entry_mode（對照實驗用，出場規則全部一樣）：0 = 背離 + RSI（完整版）、1 = 只有背離、2 = 只有 RSI、3 = 隨機進場。"""

    params = {
        "entry_mode": 0,        # 0 背離+RSI ／ 1 只有背離 ／ 2 只有 RSI ／ 3 隨機進場
        "pivot_left": 3,        # 擺動點：左邊幾根 K 棒
        "pivot_right": 3,       # 擺動點：右邊幾根 K 棒（確認要等待的 K 棒數）
        "min_gap": 5,           # 兩個擺動點最少相隔幾根
        "max_gap": 60,          # 兩個擺動點最多相隔幾根
        "rsi_period": 14,
        "rsi_low": 20.0,        # 偏多：RSI ≤ 此值
        "rsi_high": 80.0,       # 偏空：RSI ≥ 此值
        "atr_period": 14,
        "sl_buffer_atr": 0.5,   # 停損放在擺動點外 N 倍 ATR
        "rr": 2.0,              # 停利 = 停損距離 × N
        "risk_pct": 1.0,        # 每筆風險（淨值 %）
        "max_size": 30.0,       # 部位上限（淨值倍數，等於最大槓桿）
        "random_prob": 0.01,    # 隨機模式：空手時每根 K 棒進場的機率
        "seed": 1,              # 隨機模式：亂數種子（換種子 = 換一組隨機進場）
        "allow_long": True,
        "allow_short": True,
    }

    MODES = {0: "背離+RSI", 1: "只有背離", 2: "只有RSI", 3: "隨機進場"}

    # 一鍵對照實驗：同樣的出場規則，只換進場方式；隨機進場跑 3 個種子當作「沒有優勢」的基準
    experiment = [
        {"entry_mode": 0},
        {"entry_mode": 1},
        {"entry_mode": 2},
        {"entry_mode": 3, "seed": 1},
        {"entry_mode": 3, "seed": 2},
        {"entry_mode": 3, "seed": 3},
    ]

    @classmethod
    def variant(cls, params):
        """回測紀錄名稱上顯示的模式標籤。"""
        m = int(params.get("entry_mode", 0))
        label = cls.MODES.get(m, f"模式{m}")
        return f"{label} #{int(params.get('seed', 1))}" if m == 3 else label

    def init(self):
        median = (self.high + self.low) / 2
        self.ao = self.I(ta.sma(median, 5) - ta.sma(median, 34), "AO", overlay=False)
        self.rsi = self.I(ta.rsi(self.close, self.p.rsi_period), "RSI", overlay=False)
        # ATR 用「真實區間的簡單平均」，跟 MT5 內建 iATR 的算法一樣（ta.atr 是 Wilder 平滑，數值會略有差異）
        prev_close = np.concatenate([[np.nan], self.close[:-1]])
        tr = np.fmax(self.high - self.low, np.fmax(np.abs(self.high - prev_close), np.abs(self.low - prev_close)))
        self.atr = ta.sma(tr, self.p.atr_period)
        self.piv_lo = self.pivots(self.low, True)
        self.piv_hi = self.pivots(self.high, False)
        self.window = self.p.pivot_left + self.p.pivot_right + 1   # 模式 2、3 的停損參考區間（跟擺動點同寬）

    # ── 擺動點與背離 ──
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

    def divergence(self, j2, is_low, use_rsi):
        """j2 剛被確認為擺動點時，是否和前一個擺動點形成背離（可選擇是否要求 RSI 到過極端）。"""
        piv, x = (self.piv_lo, self.low) if is_low else (self.piv_hi, self.high)
        if not piv[j2]:
            return False
        j1 = self.previous(piv, j2)
        if j1 is None:
            return False
        if is_low:
            ok = self.low[j2] < self.low[j1] and self.ao[j2] > self.ao[j1]
            return ok and (not use_rsi or np.nanmin(self.rsi[j1:j2 + 1]) <= self.p.rsi_low)
        ok = self.high[j2] > self.high[j1] and self.ao[j2] < self.ao[j1]
        return ok and (not use_rsi or np.nanmax(self.rsi[j1:j2 + 1]) >= self.p.rsi_high)

    # ── 隨機（可重現：同一根 K 棒、同一個種子，Python 和 MT5 會得到同一個亂數）──
    @staticmethod
    def bar_random(t, seed):
        M = (1 << 64) - 1
        z = (int(t) + int(seed) * 0x9E3779B97F4A7C15) & M
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M
        z ^= z >> 31
        return (z >> 11) / float(1 << 53), bool(z & 1)        # (0–1 的亂數, True = 做多)

    # ── 下單 ──
    def enter(self, is_long, sl, why):
        entry = self.close[self.i]               # 估計的進場價（實際在下一根開盤成交）
        risk = (entry - sl) if is_long else (sl - entry)
        if risk <= 0:
            return False
        size = min(self.p.risk_pct / 100 * entry / risk, self.p.max_size)
        order = self.buy if is_long else self.sell
        order(size=size, sl=sl, tp_pct=self.p.rr * risk / entry, tag=why)
        return True

    def next(self):
        i = self.i
        if not self.is_flat:
            return
        atr = self.atr[i]
        if i < 1 or not np.isfinite(atr):
            return
        buf = self.p.sl_buffer_atr * atr
        mode = int(self.p.entry_mode)

        if mode in (0, 1):                                      # 背離（模式 0 另外要求 RSI）
            j2 = i - self.p.pivot_right                         # 剛好在這根收盤時被確認的擺動點
            if j2 < 1:
                return
            use_rsi = mode == 0
            if self.p.allow_long and self.divergence(j2, True, use_rsi):
                why = f"看漲背離（RSI 曾 ≤ {self.p.rsi_low:g}）" if use_rsi else "看漲背離"
                if self.enter(True, self.low[j2] - buf, why):
                    return
            if self.p.allow_short and self.divergence(j2, False, use_rsi):
                why = f"看跌背離（RSI 曾 ≥ {self.p.rsi_high:g}）" if use_rsi else "看跌背離"
                self.enter(False, self.high[j2] + buf, why)
            return

        w0 = max(0, i - self.window + 1)                        # 模式 2、3：停損放在最近 7 根的高低點外
        sl_long, sl_short = np.min(self.low[w0:i + 1]) - buf, np.max(self.high[w0:i + 1]) + buf

        if mode == 2:                                           # RSI 剛進入極端區就進場
            r, r0 = self.rsi[i], self.rsi[i - 1]
            if self.p.allow_long and r <= self.p.rsi_low < r0:
                if self.enter(True, sl_long, f"RSI 跌破 {self.p.rsi_low:g}"):
                    return
            if self.p.allow_short and r >= self.p.rsi_high > r0:
                self.enter(False, sl_short, f"RSI 突破 {self.p.rsi_high:g}")
            return

        if mode == 3:                                           # 隨機進場
            u, go_long = self.bar_random(self.time.timestamp(), self.p.seed)
            if u < self.p.random_prob:
                if go_long and self.p.allow_long:
                    self.enter(True, sl_long, "隨機做多")
                elif not go_long and self.p.allow_short:
                    self.enter(False, sl_short, "隨機做空")
