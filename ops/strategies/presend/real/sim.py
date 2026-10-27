#!/usr/bin/env python3
"""REAL replay simulator (read-only). Counts only the fills the live engine could really get:
  * discrete tries at the live pace (k per slot, src/presend_live.rs Pace), refused (never queued) by the engine's three rate
    limiters in its order (pslive.rs take_rate: path TokenBucket, global TokenBucket, then the path's [[send]] 1-second budget),
    shared by every armed window;
  * each try's landing from the LIVE tries of the probes (landing model below), its own limit (the latest price the engine had
    seen x (1 - drop)), its own deadline (engine slot + 1, capped at the window's last slot);
  * a try fills only if, at its landing position in its block, the recorded curve price <= its limit, its slot <= its
    deadline, and the window has not filled already (non-idempotent ATA: one fill per window); one position at a time
    (the engine pauses every try while a pre-send position is open);
  * the window as live: arm on the T2 trigger, skip create-slot triggers, end when the engine's slot passes the window's
    last slot, 30 ms after the engine sees the whale's first sell, or when it sees our fill;
  * exits as live: TP +10% / SL -20% on any later trade, else when the engine reaches entry slot + 2; the sell lands at a
    delay drawn from the live sells; P&L on the recorded tape with our buy in it (followers whose slippage our buy breaks
    are dropped: the measured slack table) and every cost.
Landing model ("donor transplant", MEASURED inputs): for each window, one live window of the probes with a similar trigger
position in its slot is drawn (never the window itself, nor its token, in calibration). Its tries give, as a function of
d = ms after the engine saw the trigger: lam(d) = landing chain clock - trigger chain clock - d, and g(d) = the engine's slot
lag. A try sent at d lands at trigger chain clock + d + lam(d) (lam interpolated between the donor's landed tries), i.e. the
donor's own landing pattern (leader batching, engine slot stalls, dropped tries) laid onto this window's chain events.
Mode "corr" (pessimistic bound for dense k): lam is NOT interpolated; a try takes the landing delay of the donor's try sent
just before it (tries between two donor tries pile up at the same landing offset)."""
import math, heapq, bisect, json, collections
import numpy as np
import rlib

SMS = rlib.SMS
SLACK = np.array(sorted(r[1] for r in json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"]), float)

def slack_of(sigh):
    u = (int(sigh) & ((1 << 64) - 1)) / 18446744073709551616.0
    return min(float(SLACK[min(len(SLACK) - 1, int(u * len(SLACK)))]), 1e6)

# ---------------------------------------------------------------------------------------------------------------------------
class Tok:
    """one token's recorded trades in a slot range, chain order, our wallets' trades removed"""
    __slots__ = ("mint", "s", "i", "pos", "cc", "buy", "sol", "tok", "vsol", "vtok", "fr", "user", "sigh", "n")
    def __init__(self, tp, mint, s_lo=0, s_hi=1 << 62):
        mid = tp.id_map()[mint]; a, e = tp.span[mid]
        ss = tp.s[a:e]
        a2 = a + int(np.searchsorted(ss, s_lo, side="left")); e2 = a + int(np.searchsorted(ss, s_hi, side="right"))
        sl = slice(a2, e2)
        keep = np.array([int(h) not in tp.skip_sigh for h in tp.sigh[sl]], bool) if tp.skip_sigh else np.ones(e2 - a2, bool)
        if getattr(tp, "drop_users", None):
            keep &= ~np.isin(tp.user[sl], np.array(sorted(tp.drop_users), dtype=np.int64))
        def col(x): return x[sl][keep].tolist()
        self.mint = mint
        self.s = col(tp.s); self.i = col(tp.i)
        self.pos = list(zip(self.s, self.i))
        self.cc = [tp.cc(s, i) for s, i in self.pos]
        self.buy = col(tp.buy); self.sol = col(tp.sol); self.tok = col(tp.tok)
        self.vsol = col(tp.vsol); self.vtok = col(tp.vtok); self.fr = col(tp.fr)
        self.user = col(tp.user); self.sigh = [int(h) for h in tp.sigh[sl][keep]]; self.n = len(self.s)
    def before(self, s, i):
        """index of the last trade strictly before chain position (s, i) (i may be fractional), -1 if none"""
        return bisect.bisect_left(self.pos, (s, i)) - 1
    def seen_by(self, c):
        """index of the last trade whose chain clock <= c"""
        return bisect.bisect_right(self.cc, c) - 1

class LazyStore:
    """Tok objects built on demand from the (fork-shared) tape over registered spans, with a small LRU cache"""
    def __init__(self, tp, spans, maxn=3000):
        self.tp = tp; self.spans = spans; self.cache = collections.OrderedDict(); self.maxn = maxn
    def __getitem__(self, mint):
        lo, hi = self.spans[mint]
        key = (mint, lo, hi)
        t = self.cache.get(key)
        if t is None:
            t = Tok(self.tp, mint, lo, hi); self.cache[key] = t
            if len(self.cache) > self.maxn: self.cache.popitem(last=False)
        else: self.cache.move_to_end(key)
        return t

def build_store(tp, spans):
    """spans: mint -> (slot lo, slot hi) -> {mint: Tok}"""
    return {m: Tok(tp, m, lo, hi) for m, (lo, hi) in spans.items()}

# ---------------------------------------------------------------------------------------------------------------------------
class Bucket:
    """send::TokenBucket (rate per second, burst = max(rate / 4, 1), starts full); ms clock"""
    def __init__(self, rate):
        self.per_ms = rate / 1000.0; self.cap = float(max(int(rate) // 4, 1)); self.units = self.cap; self.last = None
    def _at(self, t): return self.units if self.last is None else min(self.cap, self.units + max(0.0, t - self.last) * self.per_ms)
    def peek(self, t): return self._at(t) >= 1.0
    def take(self, t):
        self.units = self._at(t)
        if self.last is None or t > self.last: self.last = t
        self.units -= 1.0

class Budget:
    """send::Budget::try_now: at most per_sec sends in any 1 s window"""
    def __init__(self, per_sec): self.n = int(per_sec); self.q = collections.deque()
    def try_take(self, t):
        while self.q and t - self.q[0] >= 1000.0: self.q.popleft()
        if len(self.q) >= self.n: return False
        self.q.append(t); return True

# ---------------------------------------------------------------------------------------------------------------------------
class Landing:
    """the donor transplant (see the module doc). D: donors.pkl (the probes' tries, MEASURED)."""
    def __init__(self, D, full_only=True, fband=0.15, probes=("P1", "P2"), mode="interp"):
        self.L = []; self.mode = mode
        for name in probes:
            for W in D[name]["wins"]:
                if full_only and (W["disarm"] or {}).get("why") != "expired": continue
                tr = [t for t in W["tries"] if t["res"] != "unknown"]
                if len(tr) < 8: continue
                tr.sort(key=lambda t: t["d"])
                d = np.array([t["d"] for t in tr])
                lam = np.array([t["lam"] if t["lam"] is not None else np.nan for t in tr])
                g = np.array([t["g"] for t in tr])
                self.L.append(dict(key=(name, W["w"]), mint=W["mint"], f=(W["ct"] / SMS) % 1.0, d=d, lam=lam, g=g, drop=np.isnan(lam),
                                   n=len(tr), dmax=float(d[-1]), q=W.get("q_view", 0.5)))
        self.fband = fband
    def pick(self, rng, f, exclude_keys=(), exclude_mint=None):
        ok = lambda x: x["key"] not in exclude_keys and x["mint"] != exclude_mint
        c = [x for x in self.L if ok(x) and min(abs(x["f"] - f), 1 - abs(x["f"] - f)) <= self.fband]
        if not c: c = [x for x in self.L if ok(x)]
        return c[int(rng.integers(len(c)))]
    def at(self, x, d):
        """-> (lam or None = dropped, g) at d ms after the trigger"""
        D = x["d"]; n = x["n"]; k = int(np.searchsorted(D, d))
        j0 = min(max(k - 1, 0), n - 1); j1 = min(k, n - 1)
        if k <= 0: j0 = j1 = 0
        jn = j0 if abs(D[j0] - d) <= abs(D[j1] - d) else j1
        # the engine slot lag: linear between the neighbours (slot changes fall between two donor tries)
        g0 = x["g"][j0] + (d - D[j0]); g1 = x["g"][j1] + (d - D[j1])
        if k >= n:
            gg = g0 - SMS * round((d - D[j0]) / SMS)      # past the donor's last try: the engine keeps slot pace
        else:
            wg = 0.0 if D[j1] == D[j0] else (d - D[j0]) / (D[j1] - D[j0])
            gg = g0 + (g1 - g0) * wg
        if x["drop"][jn]: return None, gg
        if self.mode == "corr" or k <= 0 or k >= n:
            jj = j0 if not x["drop"][j0] else jn
            if self.mode == "corr" and x["drop"][jj]: return None, gg
            return float(x["lam"][jj]), gg
        a0, a1 = j0, j1
        while a0 > 0 and x["drop"][a0]: a0 -= 1
        while a1 < n - 1 and x["drop"][a1]: a1 += 1
        l0 = x["lam"][a0]; l1 = x["lam"][a1]
        if np.isnan(l0): l0 = l1
        if np.isnan(l1): l1 = l0
        w = 0.0 if D[a1] == D[a0] else (d - D[a0]) / (D[a1] - D[a0])
        return float(l0 + (l1 - l0) * min(max(w, 0.0), 1.0)), gg


# ---------------------------------------------------------------------------------------------------------------------------
class View:
    """the engine's view of the token's later trades, relative to when it saw the trigger (MEASURED, view_cdf.json: for live
    tries and nearby trades, P(the try's limit already reflected trade x) vs u = send ms - (x's chain clock - trigger chain
    clock), by x's slot distance from the trigger 0, 1, 2, 3, 4+). A window has one view speed q (its quantile on every
    curve); trade x is seen at (x chain clock - trigger chain clock) + F_b^-1(q), never before an earlier trade."""
    def __init__(self, path="/home/moiz/sniper-data/presend_real/view_cdf.json"):
        J = json.load(open(path)); self.inv = {}
        for b, F in J.items():
            u = np.array([g for g, p, n in F if p is not None], float); p = np.array([p for g, p, n in F if p is not None], float)
            w = np.array([n for g, p, n in F if p is not None], float)
            p = self._iso(p, w)
            p[0] = min(p[0], 0.0) if p[0] < 0.02 else p[0]
            self.inv[int(b)] = (u, p)
    @staticmethod
    def _iso(p, w):
        """pool-adjacent-violators: a non-decreasing fit"""
        blocks = [[p[i] * w[i], w[i], 1] for i in range(len(p))]
        out = []
        for b in blocks:
            out.append(b)
            while len(out) > 1 and out[-2][0] / out[-2][1] > out[-1][0] / out[-1][1]:
                a = out.pop(); out[-1][0] += a[0]; out[-1][1] += a[1]; out[-1][2] += a[2]
        r = []
        for sw, ww, n in out: r += [sw / ww] * n
        return np.array(r)
    def eps(self, b, q):
        u, p = self.inv[min(max(b, 0), 4)]
        # the u where the fitted P(seen) reaches q (linear between grid points)
        k = int(np.searchsorted(p, q, side="left"))
        if k <= 0: return float(u[0])
        if k >= len(p): return float(u[-1])
        if p[k] == p[k - 1]: return float(u[k])
        return float(u[k - 1] + (u[k] - u[k - 1]) * (q - p[k - 1]) / (p[k] - p[k - 1]))
    def seen_times(self, tk, kt, s0, ct, q):
        """seen time (ms after the trigger view) of each trade after the trigger kt+1 .. n-1, non-decreasing"""
        e = {}
        out = np.empty(max(tk.n - kt - 1, 0))
        last = 0.0
        for j, x in enumerate(range(kt + 1, tk.n)):
            b = tk.s[x] - s0
            if b not in e: e[b] = self.eps(b, q)
            v = max(tk.cc[x] - ct + e[b], last); out[j] = v; last = v
        return out

# ---------------------------------------------------------------------------------------------------------------------------
class Model:
    """the measured pieces besides the landing: the engine's view jitter (rx gap - chain-clock gap, trigger -> whale sell, both
    probes' shadow records), and the sells' landing delays (both probes' live sells)"""
    def __init__(self, D, tp):
        self.jit = collections.defaultdict(list)
        self.sell_time = []; self.sell_tpsl = []
        for name in ("P1", "P2"):
            arms = {}
            for (m, w, row), r in D[name]["shadow"]["presend_arm"].items(): arms[(m, w)] = r
            for (m, w, row), r in D[name]["shadow"]["presend_disarm"].items():
                ws = r.get("whale_sell"); a = arms.get((m, w))
                if not ws or not a: continue
                ds = ws["slot"] - a["slot"]
                self.jit[self.jb(ds)].append((ws["t"] - a["t"]) / 1e6 - (tp.cc(ws["slot"], ws["idx"]) - tp.cc(a["slot"], a["idx"])))
            for W in D[name]["wins"]:
                f, ex, se = W["fill"], W["exit"], W["sell"]
                if not (f and ex and se): continue
                if ex["why"] == "time-limit": self.sell_time.append(tp.cc(se["slot"], se["idx"]) - (f["slot"] + 2) * SMS)
                else: self.sell_tpsl.append((se["t"] - ex["t"]) / 1e6)
    @staticmethod
    def jb(ds): return 0 if ds <= 0 else 1 if ds <= 2 else 2 if ds <= 5 else 3
    def jitter(self, rng, ds):
        v = self.jit.get(self.jb(ds)) or self.jit.get(3)
        return float(v[int(rng.integers(len(v)))])

# ---------------------------------------------------------------------------------------------------------------------------
class Cost:
    def __init__(self, fail_fee=5120, buy_fee=5120, tip=200_000, sell_fee=605_000, sell_tips=1_200_000):
        self.fail_fee, self.buy_fee, self.tip, self.sell_fee, self.sell_tips = fail_fee, buy_fee, tip, sell_fee, sell_tips

class Cfg:
    def __init__(self, **kw):
        self.size = 350_000_000; self.k = 8; self.drop = 0.12; self.deadline_slots = 1; self.window_slots = 10; self.live_ms = 50.0
        self.whale_sell_ms = 30.0; self.paths = [(30, 30)]; self.global_rate = 30; self.exit_slots = 2; self.tp = 0.10; self.sl = 0.20
        self.one_position = True; self.margin_ms = 300.0; self.create_slot = False; self.cost = Cost(); self.follower = "slack"
        self.kfun = None            # V3: kfun(window, engine slot) -> k in that slot
        self.arm_filter = None      # V4: arm_filter(trigger dict) -> bool
        self.whale_pct = 6.0
        self.extra_lag_ms = 0.0     # stress test: every try lands this much later
        self.follower_cut = 0.0     # stress test: drop this share of later buys at random
        self.slot_ms = 212.0        # the engine's pace slot (SLOT_US: P1 measured 214.1, P2 211.7)
        self.slot_lag_ms = 30.0     # MEASURED fit: the engine's slot view vs the view model (75% exact, 99% within 1 slot)
        self.__dict__.update(kw)

# ---------------------------------------------------------------------------------------------------------------------------
def buy_tokens(v, t, spend, fr):
    x = int(spend / (1.0 + fr))
    return (t * x) // (v + x), x

def sell_out(v, t, q): return (v * q) // (t + q)

class Win:
    __slots__ = ("ix", "trig", "mint", "tok", "ct", "st", "en_slot", "stop_d", "donor", "n", "done", "why", "tries", "fill",
                 "fill_seen_d", "ext", "rate_skips", "paused", "armed", "meta", "kt", "seen", "q")

def run(ck, store, wins_in, cfg, landing, model, view, rng, exclude_self=False):
    """wins_in: list of trigger dicts (mint, slot, idx, age_slots, v2, cashback, whale_sell=(slot, idx) or None, ...).
    exclude_self: calibration (never draw the window's own probe window / token as its landing donor).
    Returns one result dict per window (in chain order)."""
    paths = [(Bucket(r), Budget(c)) for r, c in cfg.paths]
    glob = Bucket(cfg.global_rate)
    W = []
    for x in wins_in:
        w = Win(); w.trig = x; w.mint = x["mint"]; w.st = x["slot"]; w.ct = ck.cc(x["slot"], x["idx"])
        w.tok = None; w.done = False; w.why = None; w.tries = []; w.fill = None; w.fill_seen_d = math.inf; w.ext = None
        w.rate_skips = collections.Counter(); w.paused = 0; w.armed = False; w.n = 0; w.donor = None; w.meta = {}
        W.append(w)
    W.sort(key=lambda w: (w.ct, w.trig.get("j", 0)))
    for q, w in enumerate(W): w.ix = q
    heap = []
    pause = {}                    # window ix -> (from, until): every try paused (one position at a time)
    tok_free = {}                 # mint -> ms until a new window on it may arm (our sell + margin)
    armed_tok = {}                # mint -> window ix while armed
    nxt = 0
    def paused_at(t):
        hit = False
        for k_ in [k_ for k_, (a, b) in pause.items() if b <= t]: del pause[k_]      # past positions (the clock only moves on)
        for a, b in pause.values():
            if a <= t < b: hit = True
        return hit
    def end(w, why):
        w.done = True; w.why = why
        if armed_tok.get(w.mint) == w.ix: del armed_tok[w.mint]
    while nxt < len(W) or heap:
        t_arm = W[nxt].ct + 0.6 if nxt < len(W) else math.inf
        if heap and heap[0][0] < t_arm:
            t, ix = heapq.heappop(heap)
            w = W[ix]
            if w.done: continue
            d = t - w.ct
            lam, _g = landing.at(w.donor, d)
            # the engine's slot: the slot of the newest chain position it has seen (the measured view, this window's speed q, +30 ms)
            a_now = w.ct + d
            E = int((a_now - view.eps(int(a_now // SMS) - w.st, w.q) - cfg.slot_lag_ms) // SMS)
            if E > w.en_slot: end(w, "expired"); continue
            if d >= w.stop_d: end(w, "whale_sold"); continue
            if d >= w.fill_seen_d: end(w, "filled"); continue
            k = cfg.kfun(w, E) if cfg.kfun else cfg.k
            heapq.heappush(heap, (t + cfg.slot_ms / max(k, 1), ix))
            w.n += 1
            if k <= 0: continue
            if cfg.one_position and paused_at(t): w.paused += 1; continue
            pb, pc = paths[(w.n + w.ix) % len(paths)]
            if not pb.peek(t): w.rate_skips["rate_path"] += 1; continue
            if not glob.peek(t): w.rate_skips["rate_global"] += 1; continue
            if not pc.try_take(t): w.rate_skips["rate_path_config"] += 1; continue
            pb.take(t); glob.take(t)
            deadline = min(E + cfg.deadline_slots, w.en_slot)
            tk = w.tok
            ks = w.kt + int(np.searchsorted(w.seen, d, side="right"))      # the latest trade the engine had seen
            psign = tk.vsol[ks] / tk.vtok[ks]
            lim = psign * (1.0 - cfg.drop)
            tr = dict(n=w.n, d=d, E=E, deadline=deadline, lim=lim, psign=psign)
            if lam is None:
                tr["res"] = "drop"; w.tries.append(tr); continue
            a = max(w.ct + d + lam + cfg.extra_lag_ms, tk.cc[ks] + 1e-3, E * SMS)       # never before what it saw, never before its send slot
            S, I = ck.cc_inv(a)
            tr["S"] = S; tr["I"] = I
            if S > deadline: tr["res"] = "deadline"; w.tries.append(tr); continue
            kb = tk.before(S, I)
            if kb >= 0 and tk.vsol[kb] > 0 and tk.vtok[kb] > 0 and tk.vsol[kb] / tk.vtok[kb] <= lim and tk.vsol[kb] < rlib.UNTRADE_V:
                tr["res"] = "cand"
                if w.fill is None or (S, I) < (w.fill["S"], w.fill["I"]):
                    xk = next((j for j in range(ks + 1, kb + 1) if tk.vsol[j] / tk.vtok[j] <= lim), kb)     # the crossing trade
                    w.fill = dict(S=S, I=I, kb=kb, n=w.n, d=d, lim=lim, psign=psign, xgap=ck.cc(S, I) - tk.cc[xk])
                    # the engine sees our fill on its feed: chain-clock gap + the measured view jitter (never before it was sent)
                    w.fill_seen_d = max(d + 20.0, (ck.cc(S, I) - w.ct) + view.eps(S - w.st, w.q))
                    w.ext = exit_path(ck, tk, w, cfg, model, rng)
                    pause[w.ix] = (w.ct + w.fill_seen_d, w.ext["t_sell"] + 60.0)
                    tok_free[w.mint] = w.ext["t_sell"] + 60.0 + cfg.margin_ms
            else:
                tr["res"] = "6042"
            w.tries.append(tr)
        else:
            w = W[nxt]; nxt += 1
            x = w.trig
            why = None
            if not x.get("force_arm"):
                if not cfg.create_slot and x["age_slots"] == 0: why = "create_slot"
                elif x.get("v2") is False: why = "legacy_create"
                elif x.get("cashback"): why = "non_vanilla"
                elif cfg.arm_filter is not None and not x.get("null") and not cfg.arm_filter(x): why = "filter"
                elif w.mint in armed_tok: why = "blocked_armed"
                elif tok_free.get(w.mint, -1.0) > w.ct: why = "blocked_position"
            if why:
                w.done = True; w.why = "skip:" + why; continue
            w.armed = True
            armed_tok[w.mint] = w.ix
            w.tok = store[w.mint]
            w.en_slot = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * SMS) / SMS))
            if exclude_self:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_keys={(x.get("probe"), x.get("w"))}, exclude_mint=x["mint"])
            else:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0)
            tk = w.tok
            w.kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
            w.q = w.donor["q"]
            w.seen = view.seen_times(tk, w.kt, w.st, w.ct, w.q)
            ws = x.get("whale_sell")
            if ws is not None:
                kw = tk.before(ws[0], ws[1] + 0.5)
                if kw > w.kt and tk.pos[kw] == (ws[0], ws[1]): sd = w.seen[kw - w.kt - 1]
                else: sd = max(ck.cc(ws[0], ws[1]) - w.ct + view.eps(ws[0] - w.st, w.q), 0.0)     # beyond the stored span
                w.stop_d = sd + cfg.whale_sell_ms
            else: w.stop_d = math.inf
            heapq.heappush(heap, (w.ct + cfg.live_ms + 0.5 + float(rng.random()) * 0.5, w.ix))
    return [finish(w, cfg) for w in W]

def exit_path(ck, tk, w, cfg, model, rng):
    """our buy at the fill position; the later trades (followers our buy priced out dropped); the exit decision (TP / SL on a
    later trade, else the engine reaching entry slot + exit_slots) and the sell's landing; P&L with every cost"""
    f = w.fill; kb = f["kb"]
    v = tk.vsol[kb]; t = tk.vtok[kb]; fr = tk.fr[kb]
    q, x = buy_tokens(v, t, cfg.size, fr)
    v += x; t -= q
    S_in = f["S"]; I_in = f["I"]
    why = "time"
    t_time = (S_in + cfg.exit_slots) * SMS
    t_sell = t_time + model.sell_time[int(rng.integers(len(model.sell_time)))]
    t_dec_time = t_time + 40.0                      # the engine sees slot entry + 2 about here (MEASURED: time-exit sells)
    frs = fr
    k = kb + 1
    while k < tk.n and tk.cc[k] < t_sell:
        if tk.pos[k] < (S_in, I_in): k += 1; continue
        if tk.buy[k]:
            sol = tk.sol[k]; dtk = (t * sol) // (v + sol)
            if cfg.follower == "slack" and dtk < tk.tok[k] / (1.0 + slack_of(tk.sigh[k])):
                k += 1; continue
            if cfg.follower_cut > 0 and rng.random() < cfg.follower_cut:      # stress: a share of later buyers do not come
                k += 1; continue
            v += sol; t -= dtk
        else:
            tkn = tk.tok[k]; so = (v * tkn) // (t + tkn); v -= so; t += tkn
        frs = tk.fr[k]
        if why == "time" and tk.cc[k] < t_dec_time:
            val = sell_out(v, t, q) * (1.0 - frs) / cfg.size
            if (cfg.tp > 0 and val >= 1.0 + cfg.tp) or (cfg.sl > 0 and val <= 1.0 - cfg.sl):
                why = "tp" if val >= 1.0 + cfg.tp else "sl"
                t_new = tk.cc[k] + model.sell_tpsl[int(rng.integers(len(model.sell_tpsl)))]
                t_sell = min(t_sell, t_new)
        k += 1
    out = sell_out(v, t, q)
    net_out = int(out * (1.0 - frs))
    c = cfg.cost
    pnl = net_out - cfg.size - c.buy_fee - c.tip - c.sell_fee - c.sell_tips
    return dict(t_sell=t_sell, why=why, tokens=q, out=net_out, pnl=pnl, curve=out - x, S_in=S_in, sell_S=ck.cc_inv(t_sell)[0])

def finish(w, cfg):
    r = dict(ix=w.ix, mint=w.mint, trig=w.trig, armed=w.armed, why=w.why)
    if not w.armed: return r
    fill = w.fill
    landed = [t for t in w.tries if t["res"] != "drop"]
    fees = sum(cfg.cost.fail_fee for t in landed if fill is None or t["n"] != fill["n"])
    r.update(sent=len(w.tries), landed=len(landed), dropped=len(w.tries) - len(landed), fees=fees, rate=dict(w.rate_skips), paused=w.paused,
             filled=fill is not None, deadline=sum(1 for t in w.tries if t["res"] == "deadline"), why=w.why or "open")
    if fill is not None:
        r.update(fill_S=fill["S"], fill_I=fill["I"], fill_n=fill["n"], fill_d=fill["d"], pnl=w.ext["pnl"], exit=w.ext["why"], curve=w.ext["curve"], xgap=fill["xgap"])
    else: r["pnl"] = 0
    r["net"] = r["pnl"] - fees
    return r
