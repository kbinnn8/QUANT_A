class FibGoldenZone(Strategy):
    """費波那契黃金區域回檔（順勢）。
    背景：大週期（預設 4 小時）收盤在 EMA200 之上只做多、之下只做空（只用已收盤的大週期 K 棒）。
    波段：最近一個確認的擺動高點 B，和它之前最近的擺動低點 A；A→B 要是乾淨的一波，而且長度 ≥ 3 倍 ATR。
    位置：回檔到 0.382–0.618 的黃金區域（以做多為例：B − 0.382×波段 到 B − 0.618×波段）。
    時機：區域內 AO 由紅轉綠（動能翻正），而且收盤還在 0.382 之下才進場。
    出場：停損 0.786 外 0.2 倍 ATR，停利回到 B；報酬風險比 < 1 的單不做。每一波只做一次。做空完全相反。
    entry_mode（對照實驗）：0 = 完整版、1 = 不看趨勢、2 = 不等確認（一碰到區域就進）、3 = 隨機進場（順趨勢方向）。"""

    params = {
        "entry_mode": 0,        # 0 完整版 ／ 1 不看趨勢 ／ 2 不等確認 ／ 3 隨機進場
        "htf_hours": 4,         # 大週期（小時）；資料本身週期 ≥ 這個值時，直接用資料本身的週期
        "trend_ema": 200,       # 大週期 EMA 長度
        "pivot_left": 3,        # 擺動點：左邊幾根
        "pivot_right": 3,       # 擺動點：右邊幾根（確認要等的 K 棒數）
        "max_leg": 100,         # A 到 B 最多幾根
        "min_leg_atr": 3.0,     # 波段長度至少幾倍 ATR
        "max_wait": 40,         # B 之後最多等幾根回檔，超過就作廢
        "zone_shallow": 0.382,  # 黃金區域淺的一端
        "zone_deep": 0.618,     # 黃金區域深的一端
        "sl_beyond": 0.168,     # 停損：區域深端再過去幾倍波段（0.618 + 0.168 = 0.786）
        "sl_buffer_atr": 0.2,   # 停損再多留幾倍 ATR
        "tp_level": 0.0,        # 停利位置（回檔比例）：0 = 回到 B；-0.272 = 1.272 延伸
        "min_rr": 1.0,          # 報酬風險比至少多少才進場
        "atr_period": 14,
        "risk_pct": 1.0,        # 每筆風險（淨值 %）
        "max_size": 30.0,       # 部位上限（淨值倍數，等於最大槓桿）
        "random_prob": 0.01,    # 隨機模式：每根 K 棒進場的機率
        "random_sl_atr": 1.5,   # 隨機模式：停損幾倍 ATR（停利 = 2 倍停損距離）
        "seed": 1,
        "allow_long": True,
        "allow_short": True,
    }

    MODES = {0: "完整版", 1: "不看趨勢", 2: "不等確認", 3: "隨機進場"}

    # 一鍵對照實驗：一層一層拿掉條件，再加上「換成沒人用的回檔區間」和「隨機進場」
    experiment = [
        {"entry_mode": 0},
        {"entry_mode": 1},
        {"entry_mode": 2},
        {"entry_mode": 0, "zone_shallow": 0.15, "zone_deep": 0.35},
        {"entry_mode": 3, "seed": 1},
        {"entry_mode": 3, "seed": 2},
        {"entry_mode": 3, "seed": 3},
    ]

    @classmethod
    def variant(cls, params):
        m = int(params.get("entry_mode", 0))
        if m == 3:
            return f"隨機進場 #{int(params.get('seed', 1))}"
        zs, zd = float(params.get("zone_shallow", 0.382)), float(params.get("zone_deep", 0.618))
        label = cls.MODES.get(m, f"模式{m}")
        if abs(zs - 0.382) > 1e-9 or abs(zd - 0.618) > 1e-9:
            label += f" 區間 {zs:g}–{zd:g}"
        return label

    def init(self):
        median = (self.high + self.low) / 2
        self.ao = self.I(ta.sma(median, 5) - ta.sma(median, 34), "AO", overlay=False)
        # ATR = 真實區間的簡單平均（和 MT5 iATR 相同）
        prev_close = np.concatenate([[np.nan], self.close[:-1]])
        tr = np.fmax(self.high - self.low, np.fmax(np.abs(self.high - prev_close), np.abs(self.low - prev_close)))
        self.atr = ta.sma(tr, self.p.atr_period)
        self.piv_lo = self.pivots(self.low, True)
        self.piv_hi = self.pivots(self.high, False)
        self.trend = self.htf_trend()
        self.used = {True: None, False: None}   # 已經做過的波段（B 的位置），每一波只做一次

    # ── 大週期趨勢：只用「在這根收盤時已經走完」的大週期 K 棒，不偷看未來 ──
    def htf_trend(self):
        idx = self.data.index
        n = len(idx)
        if n < 3:
            return np.zeros(n)
        step = pd.Series(idx).diff().dropna().median()
        H = pd.Timedelta(hours=self.p.htf_hours)
        if step >= H:
            c = self.close
            e = ta.ema(c, self.p.trend_ema)
            return np.nan_to_num(np.sign(c - e))
        h = pd.Series(self.close, index=idx).resample(H, label="left", closed="left").last().dropna()
        e = ta.ema(h.values, self.p.trend_ema)
        sig = np.nan_to_num(np.sign(h.values - e))
        ends = (h.index + H).values
        k = np.searchsorted(ends, (idx + step).values, side="right") - 1   # 這根收盤時，最後一根已走完的大週期 K 棒
        return np.where(k >= 0, sig[np.clip(k, 0, None)], 0.0)

    # ── 擺動點（和 AO 背離 EA 相同的定義）──
    def pivots(self, x, is_low):
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

    def setup(self, i, up):
        """找出目前有效的波段。up=True：A 低 → B 高（等回檔做多）。回傳 dict 或 None。"""
        R = self.p.pivot_right
        end_piv, start_piv = (self.piv_hi, self.piv_lo) if up else (self.piv_lo, self.piv_hi)
        b = next((j for j in range(i - R, i - self.p.max_wait - 1, -1) if j >= 0 and end_piv[j]), None)
        if b is None or b == self.used[up]:
            return None
        a = next((j for j in range(b - 1, b - self.p.max_leg - 1, -1) if j >= 0 and start_piv[j]), None)
        if a is None:
            return None
        hi, lo = self.high[a:b + 1], self.low[a:b + 1]
        if up:
            A, B = self.low[a], self.high[b]
            clean = B >= hi.max() and A <= lo.min()
        else:
            A, B = self.high[a], self.low[b]
            clean = B <= lo.min() and A >= hi.max()
        leg = abs(B - A)
        if not clean or not np.isfinite(self.atr[b]) or leg < self.p.min_leg_atr * self.atr[b]:
            return None
        d = -1 if up else 1                                   # 回檔方向：做多時往下
        lvl = lambda r: B + d * r * leg                       # 回檔 r 的價位
        after_hi, after_lo = self.high[b + 1:i + 1], self.low[b + 1:i + 1]
        if up:
            if len(after_hi) and after_hi.max() > B:          # 先創新高：這一波還沒結束，不算回檔
                return None
            extreme = after_lo.min() if len(after_lo) else np.inf
            prev_extreme = after_lo[:-1].min() if len(after_lo) > 1 else np.inf
            reached = extreme <= lvl(self.p.zone_shallow)
            first_touch = reached and prev_extreme > lvl(self.p.zone_shallow)
            broken = extreme < lvl(self.p.zone_deep + self.p.sl_beyond)
        else:
            if len(after_lo) and after_lo.min() < B:
                return None
            extreme = after_hi.max() if len(after_hi) else -np.inf
            prev_extreme = after_hi[:-1].max() if len(after_hi) > 1 else -np.inf
            reached = extreme >= lvl(self.p.zone_shallow)
            first_touch = reached and prev_extreme < lvl(self.p.zone_shallow)
            broken = extreme > lvl(self.p.zone_deep + self.p.sl_beyond)
        if broken:                                            # 已經回到停損位置：這一波作廢
            return None
        return dict(b=b, B=B, lvl=lvl, reached=reached, first_touch=first_touch)

    # ── 隨機（和 AO 背離 EA 同一個公式，Python 和 MT5 結果一樣）──
    @staticmethod
    def bar_random(t, seed):
        M = (1 << 64) - 1
        z = (int(t) + int(seed) * 0x9E3779B97F4A7C15) & M
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M
        z ^= z >> 31
        return (z >> 11) / float(1 << 53), bool(z & 1)

    def enter(self, up, sl, tp, why, b=None):
        entry = self.close[self.i]                           # 估計的進場價（實際在下一根開盤成交）
        risk = (entry - sl) if up else (sl - entry)
        reward = (tp - entry) if up else (entry - tp)
        if risk <= 0 or reward <= 0 or reward / risk < self.p.min_rr:
            return False
        size = min(self.p.risk_pct / 100 * entry / risk, self.p.max_size)
        (self.buy if up else self.sell)(size=size, sl=sl, tp=tp, tag=f"{why}（{reward / risk:.1f}R）")
        if b is not None:
            self.used[up] = b
        return True

    def next(self):
        i = self.i
        if not self.is_flat or i < 2 or not np.isfinite(self.atr[i]):
            return
        mode = int(self.p.entry_mode)
        trend = self.trend[i]
        if mode == 3:                                         # 隨機進場：順著大週期趨勢方向
            u, _ = self.bar_random(self.time.timestamp(), self.p.seed)
            if trend == 0 or u >= self.p.random_prob:
                return
            up = trend > 0
            if (up and not self.p.allow_long) or (not up and not self.p.allow_short):
                return
            dist = self.p.random_sl_atr * self.atr[i]
            c = self.close[i]
            sl, tp = (c - dist, c + 2 * dist) if up else (c + dist, c - 2 * dist)
            self.enter(up, sl, tp, "隨機做多" if up else "隨機做空")
            return

        for up in (True, False):
            if (up and not self.p.allow_long) or (not up and not self.p.allow_short):
                continue
            if mode != 1 and trend != (1 if up else -1):     # 趨勢過濾
                continue
            s = self.setup(i, up)
            if s is None:
                continue
            if mode == 2:                                     # 不等確認：第一次碰到區域就進
                go = s["first_touch"]
            else:                                             # AO 轉向，而且收盤還在區域淺端之內
                ao, ao1, ao2 = self.ao[i], self.ao[i - 1], self.ao[i - 2]
                turn = (ao > ao1 and ao1 <= ao2) if up else (ao < ao1 and ao1 >= ao2)
                inside = self.close[i] <= s["lvl"](self.p.zone_shallow) if up else \
                    self.close[i] >= s["lvl"](self.p.zone_shallow)
                go = s["reached"] and turn and inside
            if not go:
                continue
            atr = self.atr[i]
            sl_lvl = s["lvl"](self.p.zone_deep + self.p.sl_beyond)
            sl = sl_lvl - self.p.sl_buffer_atr * atr if up else sl_lvl + self.p.sl_buffer_atr * atr
            tp = s["lvl"](self.p.tp_level)
            why = ("黃金區域做多" if up else "黃金區域做空") + ("（碰到就進）" if mode == 2 else "")
            if self.enter(up, sl, tp, why, b=s["b"]):
                return
