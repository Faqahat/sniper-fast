"""NEWSTRAT shared library (read-only on data).
Tape: /home/it/sniper-data/newstrat/tape/<run>.npz from n0_tape.py (rows sorted by mint, s, i).
Chain clock CC = s*212 + i/blocksize(s)*212 ms (blocksize = max landed pump-tx index in the slot + 1), as in rivals/9pQQ/rlib9.py.
Curve maths: vtok = cbal + 73e12, vsol = 30e9*1073e12/vtok.  Our trade: buy SIZE (pump fee FEE in), sell all (FEE out),
COST lamports per round trip (tips + tx fees).  Our tokens are taken out of the curve for every later price (cx - tok).
Fewer-followers row: remove FOLSHARE of OUTSIDE token buys landing in the first FOLSLOTS slots after our entry."""
import os, json
import numpy as np

TAPE = "/home/it/sniper-data/newstrat/tape"
COLLECT = "/data/tapes/collect"
OUT = "/home/it/sniper-data/newstrat"
RUNS = ["run_20261028_1405", "run_20261029_1400", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]
DAY = dict(zip(RUNS, ["10-28", "10-29", "10-30", "10-31", "11-02"]))
ROLE = dict(zip(RUNS, ["fit", "fit", "fit", "choose", "test"]))
W9 = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
W8 = "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk"
OURS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
SMS = 212.0
K = 30e9 * 1073e12
VT = 73e12
TOTAL = 1_000_000_000_000_000
FEE = 0.0125
COST = 4.5e6
SIZE = 0.55e9
FOLSHARE = 0.2
FOLSLOTS = 10

def vsol(c): return K / (c + VT)

class T: pass

def load(run, curve_only=True):
    z = np.load(f"{TAPE}/{run}.npz")
    t = T()
    keep = None
    fl = z["fl"]
    if curve_only: keep = (fl & 1) == 1
    for k in ["s", "i", "bt", "u", "m", "tok", "sol", "cpre", "cpost", "cup", "tip", "fl", "rt", "fee"]:
        a = z[k]
        setattr(t, k, a[keep] if keep is not None else a)
    t.users = z["users"]; t.mints = z["mints"]; t.routes = z["routes"]
    # block sizes from ALL rows (curve + AMM)
    s_all, i_all = z["s"], z["i"]
    t.s0 = int(s_all.min())
    b = np.zeros(int(s_all.max()) - t.s0 + 1, np.int32)
    np.maximum.at(b, s_all - t.s0, i_all + 1)
    b[b == 0] = 400
    t.bsz = b
    t.cpre = np.where(t.cpre < 100e12, TOTAL, t.cpre)
    t.cpost = np.where(t.cpost < 100e12, TOTAL, t.cpost)
    t.mstart = np.searchsorted(t.m, np.arange(len(t.mints) + 1))
    t.cc = t.s * SMS + t.i / np.maximum(t.bsz[t.s - t.s0], t.i + 1) * SMS
    t.uix = {u: k for k, u in enumerate(t.users)}
    t.mix = {m: k for k, m in enumerate(t.mints)}
    t.run = run
    return t

def launches(run):
    L = {}
    for l in open(f"{COLLECT}/{run}/launches.jsonl"):
        d = json.loads(l)
        ix = d.get("ixn") or []
        may = ("MayhemState" in ix) if isinstance(ix, str) else any("Mayhem" in x for x in ix)
        if d.get("err") is not None: continue
        L[d["mint"]] = dict(slot=d["slot"], bt=d["bt"], creator=d.get("creator"), may=may)
    return L

def buy_tok(cbal, spend):
    vt = cbal + VT; vs = K / vt
    return vt - K / (vs + spend / (1 + FEE))

def sell_sol(cbal, tok):
    vt = cbal + VT; vs = K / vt
    return (vs - K / (vt + tok)) * (1 - FEE)

class Mint:
    """one mint's curve rows (chain-clock sorted) with helpers"""
    def __init__(self, t, mi, drop_uid=None):
        a0, a1 = t.mstart[mi], t.mstart[mi + 1]
        sl = slice(a0, a1)
        cc = t.cc[sl]; o = np.argsort(cc, kind="stable")
        self.CC = cc[o]; self.S = t.s[sl][o]; self.U = t.u[sl][o]; self.TK = t.tok[sl][o].astype(np.float64)
        self.SL = t.sol[sl][o]; self.CP = t.cpre[sl][o].astype(np.float64); self.CQ = t.cpost[sl][o].astype(np.float64)
        self.RT = t.rt[sl][o]
        if drop_uid is not None:
            isd = self.U == drop_uid
            self.adj = np.cumsum(np.where(isd, self.TK, 0.0))   # add back the dropped wallet's net tokens
        else:
            self.adj = None
        self.obuy = np.cumsum(np.where(self.TK > 0, self.TK, 0.0))
    def idx(self, tcc):
        return np.searchsorted(self.CC, tcc, side="right")
    def cbal(self, e):
        e = np.asarray(e)
        c = np.where(e > 0, self.CQ[np.maximum(e - 1, 0)], self.CP[0])
        if self.adj is not None:
            c = c + np.where(e > 0, self.adj[np.maximum(e - 1, 0)], 0.0)
        return c

def trip(M, t_in, t_out, size=SIZE, cost=COST, fol=0.0, folslots=FOLSLOTS, exclude_uid=None):
    """vectorised paper round trips on one mint. t_in, t_out: chain-clock arrays. returns net lamports (array)"""
    t_in = np.atleast_1d(np.asarray(t_in, np.float64)); t_out = np.atleast_1d(np.asarray(t_out, np.float64))
    e = M.idx(t_in); x = M.idx(t_out)
    cb = M.cbal(e); tok = buy_tok(cb, size)
    cx = M.cbal(x) - tok
    if fol:
        se = M.S[np.minimum(e, len(M.S) - 1)]
        xf = np.minimum(x, np.searchsorted(M.S, se + folslots, side="right"))
        ob = np.where(xf > e, M.obuy[np.maximum(xf - 1, 0)] - np.where(e > 0, M.obuy[np.maximum(e - 1, 0)], 0.0), 0.0)
        cx = cx + fol * ob
    cx = np.maximum(cx, 206.9e12 - 1e12)
    return sell_sol(cx, tok) - size - cost

def price(c): return K / (c + VT) ** 2

def stats(v, top=5):
    v = np.asarray(v, np.float64)
    if len(v) == 0: return dict(n=0, net=0.0, per=0.0, win=0.0, wo5=0.0)
    s = np.sort(v)[::-1]
    return dict(n=int(len(v)), net=round(float(v.sum()) / 1e9, 3), per=round(float(v.mean()) / 1e6, 2),
                win=round(float((v > 0).mean()) * 100, 1), wo5=round(float(s[top:].sum()) / 1e9, 3))

def hours(t):
    """recorded hours of the run from bt"""
    return (int(t.bt.max()) - int(t.bt[t.bt > 0].min())) / 3600.0
