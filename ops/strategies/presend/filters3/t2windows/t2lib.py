"""T2-WINDOWS shared library: chain tapes per mint (from e3 buckets), the block-position clock, pump curve math, and the window simulator.
Method = filters3/whaleflip/w5_replay.py + diplimit/d3_replay.py (curve = raw tape, outside trades only, walked from the anchor's recorded
post state; real tries keep their real landing; simulated tries every 212/8 ms with landing delays from the run's real pool), vectorized.
All times on the block clock cc(s, i) = s*212 + (i+0.5)/(maxi(s)+1)*212 ms (whaleflip/wtape.py)."""
import json, math, bisect, collections, pickle, zlib
import numpy as np

D = "/home/moiz/sniper-data/filters3/t2windows"
K = 30_000_000_000 * 1_073_000_000_000_000
VOFF = 73_000_000_000_000
SUP = 1e15
SMS = 212.0
FR = 0.012500000186264515
FAIL = 5120
NB = 64
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
BOTS = {"haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq": "haqq6", "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC",
        "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN": "9pQQ", "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3": "8yYM",
        "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqi", "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg": "2Vgg"}
CUT = 1793516400            # 11-01 12:00 PKT: fit / choose boundary inside r42


def bucket(m): return zlib.crc32(m.encode()) % NB


def key(s, i): return s * 100000 + i


class Clock:
    def __init__(self, maxi): self.maxi = maxi

    def cc(self, s, i):
        mx = self.maxi.get(s)
        if mx is None or mx < i: mx = max(i, 400)
        return s * SMS + (i + 0.5) / (mx + 1) * SMS

    def y2key(self, y):
        s = int(y // SMS); fr = (y - s * SMS) / SMS
        mx = self.maxi.get(s, 400)
        return key(s, int(fr * (mx + 1)))


def load_bucket(b):
    """-> {mint: tape}; tape = dict(curve, rows) with rows sorted by chain order, our txs flagged"""
    raw = collections.defaultdict(dict)
    with open(f"{D}/bk/b{b:02d}.jsonl") as f:
        for l in f:
            s, i, sig, sg, cl, tb = json.loads(l)
            for m in {x[0] for x in tb}:
                raw[m][sig] = (s, i, sig, sg, cl, tb)
    tapes = {}
    for m, txs in raw.items():
        cnt = collections.Counter()
        for d in txs.values():
            for x in d[5]:
                if x[0] == m: cnt[x[1]] += 1
        curve = cnt.most_common(1)[0][0]
        rows = []
        for s, i, sig, sg, cl, tb in sorted(txs.values(), key=lambda d: (d[0], d[1])):
            own = {}
            for mm, o, pre, post in tb:
                if mm != m: continue
                a, b_ = own.get(o, (0, 0)); own[o] = (a + (pre or 0), b_ + (post or 0))
            if curve not in own: continue
            cpre, cpost = own.pop(curve)
            dl = {o: b_ - a for o, (a, b_) in own.items()}
            sel = min(dl.items(), key=lambda kv: kv[1], default=(None, 0))
            buy = max(dl.items(), key=lambda kv: kv[1], default=(None, 0))
            rows.append({"s": s, "i": i, "k": key(s, i), "sig": sig, "sg": sg, "cl": cl, "own": own, "cpre": cpre, "cpost": cpost,
                         "seller": sel[0] if sel[1] < 0 else None, "sold": -sel[1] if sel[1] < 0 else 0,
                         "buyer": buy[0] if buy[1] > 0 else None, "bought": buy[1] if buy[1] > 0 else 0,
                         "ours": sg in OURS or any(o in OURS for o in own)})
        tapes[m] = {"curve": curve, "rows": rows, "keys": [r["k"] for r in rows]}
    return tapes


def price_post(r):
    vt = r["cpost"] + VOFF; return (K / vt) / vt


def price_pre(r):
    vt = r["cpre"] + VOFF; return (K / vt) / vt


def holders_at(tape, kmax, exclude=()):
    """{owner: balance} after every row with key <= kmax (token-account owners, curve excluded; our wallets excluded)"""
    bal = {}
    for r in tape["rows"]:
        if r["k"] > kmax: break
        for o, (a, b_) in r["own"].items(): bal[o] = b_
    return {o: b_ for o, b_ in bal.items() if b_ > 0 and o not in OURS and o not in exclude}


def sol_in_of(spend): return int(spend / (1.0 + FR))


def min_out(V, Tk, spend, drop):
    k = V * Tk; vl = V * math.sqrt(1.0 - drop); tl = k / vl; x = spend / (1.0 + FR)
    return math.floor(tl * x / (vl + x))


class Seg:
    """outside trades after an anchor row (our txs removed), with the curve state after each, for fast lookups"""
    def __init__(self, tape, ka, clk, max_slots=80):
        rows = tape["rows"]; a = rows[ka]
        self.T0 = a["cpost"] + VOFF; self.s0 = a["s"]
        self.out = []          # (key, cc, kind, amt, seller, sold, buyer, row)
        T = self.T0; ks = []; Ts = []
        for r in rows[ka + 1:]:
            if r["ours"]: continue
            if r["s"] > self.s0 + max_slots: break
            dt = r["cpost"] - r["cpre"]
            if dt > 0: kind, amt = "s", dt; T = T + dt
            elif dt < 0: kind, amt = "b", K / (r["cpost"] + VOFF) - K / (r["cpre"] + VOFF); T = K / (K / T + amt)
            else: kind, amt = "n", 0
            self.out.append((r["k"], clk.cc(r["s"], r["i"]), kind, amt, r["seller"], r["sold"], r["buyer"], r))
            ks.append(r["k"]); Ts.append(T)
        self.ks = np.array(ks, dtype=np.int64); self.Ts = np.array([self.T0] + Ts, dtype=np.float64)
        self.ccs = np.array([o[1] for o in self.out], dtype=np.float64)

    def T_before_keys(self, keys):
        """vtok just before each chain key (outside trades only)"""
        return self.Ts[np.searchsorted(self.ks, keys, side="left")]

    def T_before_cc(self, ys):
        """vtok seen at block-clock time y: every outside trade with cc < y"""
        return self.Ts[np.searchsorted(self.ccs, ys, side="left")]

    def sell_value(self, fk, sol_in, tok, sell_k, fewer=False):
        """curve SOL out (gross) for `tok` sold just before chain key sell_k, our buy (sol_in -> tok) inserted at fk.
        fewer: the -20 % followers stress = every outside buy after our fill whose crc32(sig) % 5 == 0 is removed"""
        j = int(np.searchsorted(self.ks, fk, side="left"))
        T = self.Ts[j]; T = T - tok          # our buy
        for o in self.out[j:]:
            if o[0] >= sell_k: break
            if o[2] == "b" and fewer and zlib.crc32(o[7]["sig"].encode()) % 5 == 0: continue
            if o[2] == "b": T = K / (K / T + o[3])
            elif o[2] == "s": T = T + o[3]
        V = K / T
        return V * tok / (T + tok)


def make_pool(rec_pool):
    ms = np.array([p[1] for p in rec_pool if p[0] != "unseen" and p[1] is not None and 0 < p[1] < 2000], dtype=np.float64)
    un = sum(1 for p in rec_pool if p[0] == "unseen") / max(1, len(rec_pool))
    return ms, un


def draws(pool, unseen, seed, reps, nmax=480):
    """common random numbers per window: landing delays and seen flags (reps x nmax), shared by every mechanics of the window"""
    rng = np.random.default_rng(seed)
    return pool[rng.integers(0, len(pool), (reps, nmax))], rng.random((reps, nmax)) >= unseen


def sim(seg, clk, tau0, E, spend, drop, H, dr):
    """simulated tries every SMS/8 from tau0 while tau < E; landing tau + L; deadline = send slot + 1.
    dr = draws(): (Lmat, Smat). -> list per rep of (filled, fill_k, fill_cc, tok, fails, curve_pnl_gross or None)"""
    Lm, Sm = dr; reps = Lm.shape[0]
    if E <= tau0: return [(False, None, None, 0, 0, 0.0)] * reps
    taus = np.arange(tau0, E, SMS / 8.0)[:Lm.shape[1]]
    n = len(taus)
    Tseen = seg.T_before_cc(taus)
    V = K / Tseen
    vl = V * math.sqrt(1.0 - drop); x = spend / (1.0 + FR)
    mo = np.floor((V * Tseen / vl) * x / (vl + x))
    dl = np.floor(taus / SMS).astype(np.int64) + 1
    sin = sol_in_of(spend)
    out = []
    for rep in range(reps):
        L = Lm[rep, :n]; seen = Sm[rep, :n]
        y = taus + L
        ls = np.floor(y / SMS).astype(np.int64)
        fr = (y - ls * SMS) / SMS
        mx = np.array([clk.maxi.get(int(s), 400) for s in ls], dtype=np.float64)
        lk = ls * 100000 + np.floor(fr * (mx + 1)).astype(np.int64)
        Tl = seg.T_before_keys(lk)
        Vl = K / Tl
        tok = np.floor(Tl * sin / (Vl + sin))
        ok = seen & (ls <= dl) & (tok >= mo)
        idx = np.nonzero(seen)[0]
        if not ok.any():
            out.append((False, None, None, 0, int(seen.sum()), 0.0)); continue
        cand = np.nonzero(ok)[0]
        f = cand[np.argmin(lk[cand])]
        fk = int(lk[f]); fcc = float(y[f]); ftok = float(tok[f])
        fails = int(((taus[idx] <= fcc) & (idx != f)).sum())
        if H is None: out.append((True, fk, fcc, ftok, fails, None)); continue
        sk = clk.y2key(fcc + H); sk = max(sk, fk + 1)
        val = seg.sell_value(fk, sin, ftok, sk)
        out.append((True, fk, fcc, ftok, fails, val - sin))
    return out
