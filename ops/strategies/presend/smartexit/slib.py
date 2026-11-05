"""SMARTEXIT simulator library.

Pricing = filters3/exit125/xlib.py (validated 1915/1915 at the real landing on r42-r49): pump.fun constant product on the tape's
virtual reserves, time placement (every other trade whose rx time t < our landing rx time is ahead of our sell), our real sell
removed (vtok - q after it), other traders' TOKEN amounts kept.  Extended here to
  * partial sells (an earlier partial landing puts its tokens back on the curve for everything priced after it),
  * an event stream in rx-time order (what the engine sees, when it sees it) for causal policies,
  * fc (followers stress): every other BUY after our fill gets fc fewer tokens (and fc less SOL in the policy's eyes).

Conventions (labelled):
  * MEASURED: tape rx times, each fill's own decision->land lag (real sell rx t - real exit decision t), real realized P&L, ATA refund.
  * ASSUMED: timer decisions fire exactly at fill + H + 1 ms (dip34 exact exit; r51+ measured 125.3..129 ms); event decisions fire at
    the rx time of the trade that triggers them (+0.2 ms processing); the sell lands at decision + the fill's own lag; a second sell
    tx costs SELL_TX (tx fee + one tip, measured median below) and pays the 1.25% pump fee on its own gross.
  * Landing past the covered tape (fill + 3000 ms) is clamped to the tape end and counted (n_clamped).
"""
import json, bisect, statistics, random, collections, math

FEE = 0.0125
SELL_TX = 0.0018          # SOL per extra sell tx: measured sell_land.fee 0.605 mSOL + tip 1.2 mSOL (close.sell_sigs[2])
TAPE_MS = 3000.0
D = "/home/moiz/sniper-data/smartexit"
TP, SL = 1.20, 0.80


def gross_out(q, vsol, vtok):
    return q * vsol // (vtok + q)


class Fill:
    """one fill, precomputed for fast policy evaluation"""
    __slots__ = ("x", "tr", "fi", "si", "q", "t0", "lag", "real", "g_real", "ev", "ts", "pm", "cumbuy", "run", "split", "kind",
                 "spend", "lags_pool")

    def __init__(self, x):
        self.x = x
        tp = x["tape"]
        tr = sorted(tp, key=lambda a: (a["slot"], a["idx"], a.get("j", 0)))
        sell_sig = x["sells"][0]["sig"]
        self.fi = next(i for i, a in enumerate(tr) if a["sig"] == x["sig"])
        self.si = next(i for i, a in enumerate(tr) if a["sig"] == sell_sig and not a["buy"])
        self.tr = tr; self.q = x["tokens"]; self.t0 = x["t"]
        s = x["sells"][0]; ex = x["exit"]
        self.lag = (s["t"] - ex["t"]) / 1e6
        self.g_real = s["sol"]
        self.real = ((x["realized"] or {}).get("pnl", 0) + ((x["ata"] or {}).get("delta", 0) if (x["ata"] or {}).get("ok") else 0)) / 1e9
        self.run, self.split, self.kind, self.spend = x["run"], x["split"], x["kind"], x["spend"]
        # other trades after our fill (chain order), excluding our real sell
        oth = [i for i in range(self.fi + 1, len(tr)) if i != self.si]
        # events in rx order
        oth_t = sorted(oth, key=lambda i: tr[i]["t"])
        self.ts = [tr[i]["t"] for i in oth_t]
        pm, m = [], self.fi
        cb, c = [], 0
        for i in oth_t:
            m = max(m, i); pm.append(m)
            if tr[i]["buy"]: c += tr[i]["tok"]
            cb.append(c)
        self.pm, self.cumbuy = pm, cb
        self.ev = oth_t

    def ok(self):
        return True

    # ---- curve state for a sell landing at rx time T (ns) ----
    def state(self, T, fc=0.0, sold=()):
        """sold: iterable of (land_t, tokens) of our earlier partial sells (they are ahead of T if land_t < T)"""
        k = bisect.bisect_left(self.ts, T)        # trades with t < T
        if k == 0:
            ref_i = self.fi; cut = 0
        else:
            ref_i = self.pm[k - 1]; cut = int(self.cumbuy[k - 1] * fc) if fc else 0
        ref = self.tr[ref_i]
        kk = ref["vsol"] * ref["vtok"]
        vtok = ref["vtok"] - (self.q if ref_i > self.si else 0) + cut
        for lt, tk in sold:
            if lt < T: vtok += tk
        if vtok == ref["vtok"]: return ref["vsol"], vtok
        return kk // vtok, vtok

    def value(self, T, fc=0.0, sold=(), q=None):
        vsol, vtok = self.state(T, fc, sold)
        return gross_out(q if q is not None else self.q, vsol, vtok)


def load_fills(splits=("dev", "val", "hold"), runs=None):
    J = json.load(open(f"{D}/fills.json"))
    out, skipped = [], collections.Counter()
    for x in J["fills"]:
        if x["split"] not in splits: continue
        if runs and x["run"] not in runs: continue
        if not x.get("tape"): skipped["no tape"] += 1; continue
        if not x["sells"] or not x["exit"] or not x["realized"]: skipped["no sell/exit"] += 1; continue
        try:
            f = Fill(x)
        except StopIteration:
            skipped["sell/fill not in tape"] += 1; continue
        out.append(f)
    # per-run lag pools for the resampled-lag row
    pool = collections.defaultdict(list)
    for f in out: pool[f.run].append(f.lag)
    allp = [a for v in pool.values() for a in v]
    for f in out:
        f.lags_pool = pool[f.run] if len(pool[f.run]) >= 30 else allp
    return out, J, skipped


# ---------------- event stream (engine view) ----------------
class Ev:
    __slots__ = ("ms", "t", "buy", "sol", "tok", "w", "fl", "pct", "mark", "i")


def events(f, fc=0.0):
    """other trades after our fill in rx order with the engine mark (value of our whole position after that trade / spend, fee off)"""
    out = []
    cut = 0
    # mark: engine computes from the trade's own post-state (chain), our real sell removed; fc cut accumulates in chain order
    chain_cut = {}
    c = 0
    for i in range(f.fi + 1, len(f.tr)):
        if i == f.si: continue
        a = f.tr[i]
        if fc and a["buy"]: c += int(a["tok"] * fc)
        chain_cut[i] = c
    for i in f.ev:
        a = f.tr[i]
        e = Ev()
        e.i = i; e.t = a["t"]; e.ms = (a["t"] - f.t0) / 1e6; e.buy = a["buy"]
        e.sol = a["sol"] / 1e9 * ((1 - fc) if (fc and a["buy"]) else 1.0)
        e.tok = a["tok"]; e.w = a.get("w", ""); e.fl = a.get("fl", "") or ""; e.pct = a.get("pct_after", 0.0) or 0.0
        vtok = a["vtok"] - (f.q if i > f.si else 0) + chain_cut[i]
        vsol = (a["vsol"] * a["vtok"]) // vtok
        e.mark = gross_out(f.q, vsol, vtok) * (1 - FEE) / (f.spend * 1e9)
        out.append(e)
    return out


# ---------------- policy evaluation ----------------
def settle(f, decisions, fc=0.0, lag=None):
    """decisions: list of (decision_t_ns, fraction) in time order, fractions sum to 1.  Returns (net SOL, n_clamped, land_ms_last)"""
    lag = f.lag if lag is None else lag
    sold = []; g = 0; clamp = 0; rem = f.q; land_ms = 0
    for n, (d, fr) in enumerate(decisions):
        tok = rem if n == len(decisions) - 1 else int(f.q * fr)
        rem -= tok
        land = d + lag * 1e6
        if (land - f.t0) / 1e6 > TAPE_MS:
            land = f.t0 + int((TAPE_MS - 0.001) * 1e6); clamp += 1
        vsol, vtok = f.state(land, fc, sold)
        g += gross_out(tok, vsol, vtok)
        sold.append((land, tok))
        land_ms = (land - f.t0) / 1e6
    extra = SELL_TX * (len(decisions) - 1)
    return f.real + (g - f.g_real) * (1 - FEE) / 1e9 - extra, clamp, land_ms


def with_tpsl(evs, d, start_ms=0.0, tp=TP, sl=SL):
    """engine TP/SL: first mark crossing seen before decision d (ns) -> decision at that trade's rx time"""
    for e in evs:
        if e.t >= d: break
        if e.ms < start_ms: continue
        if e.mark >= tp or e.mark <= sl:
            return e.t + 200_000, ("tp" if e.mark >= tp else "sl")
    return d, "time"


def timer_t(f, H):
    return f.t0 + int((H + 1.0) * 1e6)


# ---------------- reporting ----------------
def pct(a, p):
    a = sorted(a); return a[int(p * (len(a) - 1))] if a else float("nan")


def summarize(rows, hours, base_key="b", key="p"):
    """rows: list of dict(run, b=baseline pnl, p=policy pnl).  Returns dict of metrics"""
    n = len(rows)
    b = sum(r[base_key] for r in rows); p = sum(r[key] for r in rows)
    d = sorted((r[key] - r[base_key] for r in rows), reverse=True)
    ps = sorted((r[key] for r in rows), reverse=True); bs = sorted((r[base_key] for r in rows), reverse=True)
    return dict(n=n, base=b, pol=p, gain=p - b, per_day=(p - b) / hours * 24 if hours else float("nan"),
                base_day=b / hours * 24 if hours else float("nan"), pol_day=p / hours * 24 if hours else float("nan"),
                win_b=sum(1 for r in rows if r[base_key] > 0) / max(1, n), win_p=sum(1 for r in rows if r[key] > 0) / max(1, n),
                gain_wo5=sum(d[5:]), pol_wo5=sum(ps[5:]), base_wo5=sum(bs[5:]),
                changed=sum(1 for x in d if abs(x) > 1e-9), up=sum(1 for x in d if x > 1e-9), down=sum(1 for x in d if x < -1e-9))


def boot_ci(gains, n=2000, seed=1):
    rnd = random.Random(seed); m = len(gains)
    if m == 0: return (0, 0)
    s = sorted(sum(gains[rnd.randrange(m)] for _ in range(m)) for _ in range(n))
    return s[int(0.025 * n)], s[int(0.975 * n)]


# ---------------- phase-conditioned lag (robustness row) ----------------
class PhaseLag:
    """MEASURED: real time-ms exits (all runs) -> decision->land lag by the decision's phase in its slot (25 ms bins, phase =
    decision rx t - first-seen rx t of the latest slot seen, slotmap.json).  A counterfactual decision draws its lag from the bin
    of ITS phase (instead of keeping the fill's own lag)."""
    def __init__(self, fills, seed=11):
        self.SM = {int(k): v[0] for k, v in json.load(open(f"{D}/slotmap.json")).items()}
        self.bins = collections.defaultdict(list); self.all = []
        for f in fills:
            ex = f.x["exit"]
            if ex["why"] != "time-ms": continue
            b = self.bin(f, ex["t"])
            self.all.append(f.lag)
            if b is not None: self.bins[b].append(f.lag)
        self.rnd = random.Random(seed)

    def bin(self, f, d):
        best = None
        for s in range(f.x["slot"] - 1, f.x["slot"] + 17):
            v = self.SM.get(s)
            if v is not None and v <= d: best = v
        if best is None: return None
        return min(int((d - best) / 1e6 // 25), 12)

    def draw(self, f, d):
        b = self.bin(f, d)
        pool = self.bins.get(b) if b is not None else None
        if not pool or len(pool) < 20: pool = self.all
        return pool[self.rnd.randrange(len(pool))]
