"""migpaper: PAPER-ONLY forward test of the near-graduation rule (migrate/REPORT.md §7; frozen in FROZEN.md).
Window tape from grad/g1_decode.py chunks (VMIN=0: every curve trade), m1 features, m3 replay, numpy GBDT predictors.
Nothing here sends, writes to a server or touches an engine."""
import sys, os, json, glob, hashlib, collections, datetime as dt
import numpy as np

C = os.path.dirname(os.path.abspath(__file__))
D = "/home/moiz/sniper-data/e2x1_dissect/migpaper"
GRAD = "/home/moiz/sniper/ops/strategies/e2x1_dissect/grad"
MIG = "/home/moiz/sniper-data/e2x1_dissect/migrate"
sys.path.insert(0, GRAD)
import g1_decode                                                     # noqa: E402
from glib import last_before, pool_state_after, pool_fee, pkt, pday, SLOT_MS, PKT   # noqa: E402,F401
g1_decode.VMIN = 0                                                   # keep EVERY curve trade (fork inherits this in the pool)
SLOT_S = SLOT_MS / 1000.0

# ---- frozen parameters (FROZEN.md) ----------------------------------------------------------------------------------
V = 105; THETA = 0.8; SIZE = 2.0; MED_MS = 66.0
R_TRIES = 5; DELTA = 5; W = 10; A = 47
TRY_COST = 0.000005; FAIL_COST = 0.0003; RT_COST = 0.0029; GUARD = 1.05; TRY_COST_HI = 0.0003
EXITS = [(2, 0.20, 120), (2, "pd0.3", 120)]
CKS = [10, 20, 30, 60, 120]
WIN = [(1, 5), (5, 24), (10, 47), (30, 141), (120, 566)]
LOOKBACK = 3 * 3600; LOOKAHEAD = 900
PAIR = [(j, (3 * j + 1) % 10) for j in range(10)]
MODES = ["react", "pre"]

def dly():
    return np.array(json.load(open(D + "/models/dly.json"))["dly_slots"], float)

def h64(s):
    return int.from_bytes(hashlib.blake2b(str(s).encode(), digest_size=8).digest(), "little")

def sha256(fn):
    h = hashlib.sha256()
    with open(fn, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

# ---- numpy GBDT (exported sklearn HistGradientBoostingClassifier) ---------------------------------------------------
def export_hgb(model):
    trees = []
    for it in model._predictors:
        nd = it[0].nodes
        trees.append(dict(feat=nd["feature_idx"].astype(int).tolist(), thr=nd["num_threshold"].astype(float).tolist(),
                          left=nd["left"].astype(int).tolist(), right=nd["right"].astype(int).tolist(),
                          value=nd["value"].astype(float).tolist(), leaf=nd["is_leaf"].astype(int).tolist(),
                          miss_left=nd["missing_go_to_left"].astype(int).tolist()))
    base = float(np.asarray(model._baseline_prediction).ravel()[0])
    return dict(base=base, n_trees=len(trees), trees=trees)

class NPModel:
    def __init__(self, fn):
        j = json.load(open(fn)); self.base = j["base"]; self.names = j.get("names")
        self.trees = [{k: np.array(v) for k, v in t.items()} for t in j["trees"]]
    def raw(self, X):
        X = np.asarray(X, np.float64); n = len(X); out = np.full(n, self.base)
        for t in self.trees:
            node = np.zeros(n, np.int64)
            for _ in range(64):
                leaf = t["leaf"][node] == 1
                if leaf.all(): break
                x = X[np.arange(n), t["feat"][node]]
                nan = np.isnan(x)
                go_left = np.where(nan, t["miss_left"][node] == 1, x <= t["thr"][node])
                nxt = np.where(go_left, t["left"][node], t["right"][node])
                node = np.where(leaf, node, nxt)
            out += t["value"][node]
        return out
    def proba(self, X):
        if len(X) == 0: return np.zeros(0)
        return 1.0 / (1.0 + np.exp(-self.raw(X)))

# ---- chunks -------------------------------------------------------------------------------------------------------------
def chunk_ts(fn):
    b = os.path.basename(fn); return int(b.split("txs_")[1].split(".")[0])

def cache_name(cache, fn):
    run = os.path.basename(os.path.dirname(os.path.dirname(fn)))
    return os.path.join(cache, run + "__" + os.path.basename(fn).replace(".jsonl.gz", ".npz"))

# ---- window tape (same interface as glib.Tape) ----------------------------------------------------------------------
class WTape:
    def __init__(self, files):
        files = sorted(files, key=lambda f: (chunk_ts(f), f))
        self.files = files
        strings = {}; sl = []
        mig = {}; cmp_ = {}; cr = {}; mx = {}
        TR, PS = [], []; self.metas = []
        for fn in files:
            z = np.load(fn, allow_pickle=True); ids = z["ids"]
            g = np.empty(len(ids), np.int64)
            for k, s in enumerate(ids):
                v = strings.get(s)
                if v is None: v = strings[s] = len(strings)
                g[k] = v
            for x in z["mig"]:
                d = json.loads(str(x)); mig.setdefault(d["sig"], d)
            for x in z["cmp"]:
                d = json.loads(str(x))
                if d["mint"] not in cmp_ or (d["slot"], d["idx"]) < (cmp_[d["mint"]]["slot"], cmp_[d["mint"]]["idx"]): cmp_[d["mint"]] = d
            for x in z["cr"]:
                d = json.loads(str(x)); cr.setdefault(d["mint"], d)
            for k, v in json.loads(str(z["mx"][0])).items():
                if v > mx.get(k, 0): mx[k] = v
            sl.append(z["slots"].astype(np.int64))
            tr = z["tr"]
            if len(tr):
                t2 = tr.copy(); t2["mint"] = g[tr["mint"]]; t2["user"] = g[tr["user"]]; t2["signer"] = g[tr["signer"]]; TR.append(t2)
            ps = z["ps"]
            if len(ps):
                p2 = ps.copy(); p2["pool"] = g[ps["pool"]]; p2["user"] = g[ps["user"]]; p2["signer"] = g[ps["signer"]]; p2["txmint"] = g[ps["txmint"]]; PS.append(p2)
            self.metas.append(json.loads(str(z["meta"][0])))
        self.strings = np.array(list(strings.keys()), dtype=object); self.sid = strings
        self.mints = self.strings; self.mid = strings; self.users = self.strings; self.uid = strings; self.pools = self.strings; self.pid = strings
        self.cmp = cmp_; self.cr = cr
        self.M = dict(mx=mx)
        self.mig = {}
        for d in sorted(mig.values(), key=lambda d: (d["slot"], d["idx"])):
            if d.get("mig") and d["mint"] not in self.mig: self.mig[d["mint"]] = d
        pool_win = {d["pool"]: (d["slot"], d["slot"] + 12000) for d in self.mig.values()}
        # trades
        TR = np.concatenate(TR) if TR else np.zeros(0, g1_decode.TRD)
        PS = np.concatenate(PS) if PS else np.zeros(0, g1_decode.PSD)
        if len(PS):
            pn = self.strings[PS["pool"]]
            keep = np.array([(p in pool_win) and (pool_win[p][0] <= s <= pool_win[p][1]) for p, s in zip(pn, PS["slot"].astype(np.int64))], bool)
            PS = PS[keep]
        def dedup(a):
            if len(a) == 0: return a
            k = a["sigh"].astype(np.uint64) ^ (a["j"].astype(np.uint64) << np.uint64(56))
            _, u = np.unique(k, return_index=True); return a[np.sort(u)]
        TR = dedup(TR); PS = dedup(PS)
        self.T = TR[np.lexsort((TR["j"], TR["idx"], TR["slot"], TR["mint"]))] if len(TR) else TR
        self.P = PS[np.lexsort((PS["j"], PS["idx"], PS["slot"], PS["pool"]))] if len(PS) else PS
        n = len(self.strings)
        self.ms = np.searchsorted(self.T["mint"], np.arange(n), "left"); self.me = np.searchsorted(self.T["mint"], np.arange(n), "right")
        self.ps_ = np.searchsorted(self.P["pool"], np.arange(n), "left"); self.pe_ = np.searchsorted(self.P["pool"], np.arange(n), "right")
        # block clock
        S = np.concatenate(sl) if sl else np.zeros((0, 3), np.int64)
        self.slo = int(S[:, 0].min()); self.shi = int(S[:, 0].max())
        self.N = np.zeros(self.shi - self.slo + 1, np.int64); self.BT = np.zeros_like(self.N)
        np.maximum.at(self.N, S[:, 0] - self.slo, S[:, 2] + 1)
        np.maximum.at(self.BT, S[:, 0] - self.slo, S[:, 1])
        self.bt_lo = int(S[:, 1].min()); self.bt_hi = int(S[:, 1].max())
    def bsize(self, s):
        k = int(s) - self.slo
        return int(self.N[k]) if 0 <= k < len(self.N) else 0
    def clock(self, s, i):
        n = max(self.bsize(s), 1)
        return s + min(i / n, 0.999999)
    def position(self, c):
        s = int(np.floor(c)); f = c - s
        for _ in range(12):
            if self.bsize(s) > 0: break
            s += 1; f = 0.0
        return s, int(np.floor(f * max(self.bsize(s), 1)))
    def bt_of(self, s):
        k = int(s) - self.slo
        k = min(k, len(self.BT) - 1)
        while 0 < k < len(self.BT) and self.BT[k] == 0: k -= 1
        return int(self.BT[max(k, 0)])
    def trades(self, m):
        k = self.mid.get(m)
        return self.T[self.ms[k]:self.me[k]] if k is not None else self.T[:0]
    def pool_events(self, pool):
        k = self.pid.get(pool)
        return self.P[self.ps_[k]:self.pe_[k]] if k is not None else self.P[:0]

# ---- wallet history store (m0 trips, hashed ids) --------------------------------------------------------------------
WDT = np.dtype([("u", "u8"), ("m", "u8"), ("t_end", "u4"), ("t_first", "u4"), ("pnl", "f4"), ("sol_in", "f4"), ("flags", "u1"), ("ntr", "u2"), ("cmp_bt", "u4")])
F_GRAD, F_NEAR, F_PO, F_CP, F_CS = 1, 2, 4, 8, 16

def trips_from_tape(T, mints_keep):
    """m0 logic on a WTape: curve trips of mints_keep (set of mint strings) + pool trips of canonical migrated pools"""
    nm = len(T.strings)
    cmp_bt = np.full(nm, 0, np.int64); cmp_slot = np.full(nm, -1, np.int64)
    for m, c in T.cmp.items():
        k = T.mid.get(m)
        if k is not None: cmp_bt[k] = c["bt"]; cmp_slot[k] = c["slot"]
    keep_ids = np.array(sorted(T.mid[m] for m in mints_keep if m in T.mid), np.int64)
    TR = T.T[np.isin(T.T["mint"].astype(np.int64), keep_ids)] if len(keep_ids) else T.T[:0]
    out = []
    if len(TR):
        u = TR["user"].astype(np.int64); m = TR["mint"].astype(np.int64); key = u * nm + m
        order = np.argsort(key, kind="stable"); key = key[order]; rows = TR[order]
        uk, start = np.unique(key, return_index=True)
        buy = rows["buy"] == 1; sol = rows["sol"].astype(np.float64) / 1e9
        red = lambda x, f=np.add: f.reduceat(x, start)
        c_in = red(np.where(buy, sol, 0.0)); c_out = red(np.where(buy, 0.0, sol))
        c_tf = red(rows["bt"].astype(np.int64), np.minimum); c_tl = red(rows["bt"].astype(np.int64), np.maximum)
        c_n = np.diff(np.append(start, len(rows)))
        c_ng = red((buy & (rows["vsol"] >= 80_000_000_000)).astype(np.int64)) > 0
        c_cmp = red((buy & (rows["rtok"] == 0)).astype(np.int64)) > 0
        mslot = cmp_slot[rows["mint"].astype(np.int64)]
        c_cs = red((buy & (rows["slot"].astype(np.int64) == mslot)).astype(np.int64)) > 0
        out.append(dict(key=uk, sol_in=c_in, sol_out=c_out, tf=c_tf, tl=c_tl, n=c_n, ng=c_ng, cp=c_cmp, cs=c_cs, po=np.zeros(len(uk), bool)))
    # pool trips
    pool_mint = np.full(nm, -1, np.int64); pool_mig_slot = np.full(nm, -1, np.int64)
    for m, mg in T.mig.items():
        pk = T.pid.get(mg["pool"]); mk = T.mid.get(m)
        if pk is not None and mk is not None: pool_mint[pk] = mk; pool_mig_slot[pk] = mg["slot"]
    P = T.P
    if len(P):
        pm = pool_mint[P["pool"].astype(np.int64)]; okp = pm >= 0
        Pp = P[okp]; pmk = pm[okp]
        if len(Pp):
            u2 = Pp["user"].astype(np.int64); key2 = u2 * nm + pmk
            o2 = np.argsort(key2, kind="stable"); key2 = key2[o2]; Pp = Pp[o2]
            uk2, st2 = np.unique(key2, return_index=True)
            pbuy = Pp["buy"] == 1; uq = Pp["uquote"].astype(np.float64) / 1e9
            red2 = lambda x, f=np.add: f.reduceat(x, st2)
            p_in = red2(np.where(pbuy, uq, 0.0)); p_out = red2(np.where(pbuy, 0.0, uq))
            p_tf = red2(Pp["bt"].astype(np.int64), np.minimum); p_tl = red2(Pp["bt"].astype(np.int64), np.maximum)
            p_n = np.diff(np.append(st2, len(Pp)))
            ms2 = pool_mig_slot[Pp["pool"].astype(np.int64)]
            p_po = red2((pbuy & (Pp["slot"].astype(np.int64) <= ms2 + 1)).astype(np.int64)) > 0
            out.append(dict(key=uk2, sol_in=p_in, sol_out=p_out, tf=p_tf, tl=p_tl, n=p_n, ng=np.zeros(len(uk2), bool), cp=np.zeros(len(uk2), bool),
                            cs=np.zeros(len(uk2), bool), po=p_po))
    if not out: return np.zeros(0, WDT)
    allk = np.union1d(*[o["key"] for o in out]) if len(out) > 1 else out[0]["key"]
    def place(o, name, default, dtype=None):
        v = o[name]; res = np.full(len(allk), default, dtype=dtype or v.dtype); res[np.searchsorted(allk, o["key"])] = v; return res
    sol_in = sum(place(o, "sol_in", 0.0) for o in out); sol_out = sum(place(o, "sol_out", 0.0) for o in out)
    tf = np.minimum.reduce([place(o, "tf", np.int64(2**62)) for o in out]); tl = np.maximum.reduce([place(o, "tl", np.int64(0)) for o in out])
    ntr = sum(place(o, "n", np.int64(0)) for o in out)
    ng = np.logical_or.reduce([place(o, "ng", False) for o in out]); cp = np.logical_or.reduce([place(o, "cp", False) for o in out])
    cs = np.logical_or.reduce([place(o, "cs", False) for o in out]); po = np.logical_or.reduce([place(o, "po", False) for o in out])
    user = allk // nm; mint = allk % nm
    cb = cmp_bt[mint]
    W_ = np.zeros(len(allk), WDT)
    W_["u"] = np.array([h64(s) for s in T.strings[user]], np.uint64); W_["m"] = np.array([h64(s) for s in T.strings[mint]], np.uint64)
    W_["t_end"] = tl; W_["t_first"] = tf; W_["pnl"] = sol_out - sol_in; W_["sol_in"] = sol_in
    W_["flags"] = (cb > 0) * F_GRAD + ng * F_NEAR + po * F_PO + cp * F_CP + cs * F_CS
    W_["ntr"] = np.minimum(ntr, 65535); W_["cmp_bt"] = cb
    return W_

class WStore:
    def __init__(self, fn):
        self.fn = fn
        self.W = np.load(fn)["W"] if os.path.exists(fn) else np.zeros(0, WDT)
        self._index()
    def _index(self):
        W_ = self.W
        self.U = np.unique(W_["u"]); self.Mu = np.unique(W_["m"]); nm = len(self.Mu); self.nm = nm
        uidx = np.searchsorted(self.U, W_["u"]).astype(np.int64); midx = np.searchsorted(self.Mu, W_["m"]).astype(np.int64)
        grad = (W_["flags"] & F_GRAD) > 0
        t_res = np.where(grad, np.maximum(W_["t_end"].astype(np.int64), W_["cmp_bt"].astype(np.int64)),
                         np.maximum(W_["t_end"].astype(np.int64), W_["t_first"].astype(np.int64) + 600))
        o = np.lexsort((t_res, uidx)); self.o = o
        self.wu = uidx[o]; self.t_res = t_res[o]; self.wm = midx[o]
        self.KEY = self.wu * (1 << 31) + self.t_res
        fl = W_["flags"][o]
        cols = dict(n=np.ones(len(o)), pnl=W_["pnl"][o].astype(np.float64), ng=((fl & F_NEAR) > 0).astype(float),
                    ngg=(((fl & F_NEAR) > 0) & ((fl & F_GRAD) > 0)).astype(float), po=((fl & F_PO) > 0).astype(float),
                    cp=((fl & F_CP) > 0).astype(float), cs=((fl & F_CS) > 0).astype(float), win=(W_["pnl"][o] > 0).astype(float))
        self.cols = cols
        self.CUM = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in cols.items()}
        self.MK = np.lexsort((self.wm, self.wu)); self.MKEY = self.wu[self.MK] * nm + self.wm[self.MK]
    def wstats(self, users_h, t, mint_h):
        """m1.wstats: prior stats of each user at time t (trips resolved before t), excluding the current mint's trip"""
        uh = np.asarray(users_h, np.uint64)
        users = np.searchsorted(self.U, uh).astype(np.int64); users = np.minimum(users, max(len(self.U) - 1, 0))
        known = (self.U[users] == uh) if len(self.U) else np.zeros(len(uh), bool)
        lo = np.searchsorted(self.KEY, users * (1 << 31)); hi = np.searchsorted(self.KEY, users * (1 << 31) + t)
        out = {k: np.where(known, c[hi] - c[lo], 0.0) for k, c in self.CUM.items()}
        mi = int(np.searchsorted(self.Mu, np.uint64(mint_h)))
        if mi < len(self.Mu) and self.Mu[mi] == np.uint64(mint_h) and len(self.MKEY):
            j = np.searchsorted(self.MKEY, users * self.nm + mi); j = np.minimum(j, len(self.MKEY) - 1); r = self.MK[j]
            own = known & (self.MKEY[j] == users * self.nm + mi) & (self.t_res[r] < t)
            if own.any():
                for k, v in self.cols.items(): out[k] = out[k] - np.where(own, v[r], 0.0)
        return out
    def upsert(self, new):
        if len(new) == 0: return 0
        comb = np.concatenate([self.W, new]); prio = np.concatenate([np.zeros(len(self.W), np.int8), np.ones(len(new), np.int8)])
        o = np.lexsort((prio, comb["m"], comb["u"])); comb = comb[o]
        last = np.ones(len(comb), bool); last[:-1] = (comb["u"][1:] != comb["u"][:-1]) | (comb["m"][1:] != comb["m"][:-1])
        n0 = len(self.W); self.W = comb[last]; self._index(); return len(self.W) - n0
    def save(self):
        tmp = self.fn + ".tmp.npz"; np.savez_compressed(tmp, W=self.W); os.replace(tmp, self.fn)

# ---- creator store ----------------------------------------------------------------------------------------------------
CDT = np.dtype([("m", "u8"), ("c", "u8"), ("bt", "u4"), ("near", "u1"), ("cmp_bt", "u4")])
class CStore:
    def __init__(self, fn):
        self.fn = fn; self.Cr = np.load(fn)["C"] if os.path.exists(fn) else np.zeros(0, CDT); self._index()
    def _index(self):
        o = np.lexsort((self.Cr["bt"], self.Cr["c"])); self.Cs = self.Cr[o]
        self.cc = self.Cs["c"]; self.bts = self.Cs["bt"].astype(np.int64); self.near = self.Cs["near"].astype(np.int64); self.cb = self.Cs["cmp_bt"].astype(np.int64)
        self.cnear = np.concatenate([[0], np.cumsum(self.near)])
    def cstats(self, creator, t):
        ch = np.uint64(h64(creator)); a = int(np.searchsorted(self.cc, ch, "left")); b = int(np.searchsorted(self.cc, ch, "right"))
        if a == b: return 0, 0, 0
        n = int(np.searchsorted(self.bts[a:b], t - 1))
        ng = int(((self.cb[a:b] > 0) & (self.cb[a:b] < t)).sum())
        return n, int(self.cnear[a + n] - self.cnear[a]), ng
    def upsert_tape(self, T):
        rows = []
        for m, d in T.cr.items():
            c = T.cmp.get(m); rows.append((h64(m), h64(d["creator"]), d["bt"], int(T.M["mx"].get(m, 0) >= 78e9), c["bt"] if c else 0))
        new = np.array(rows, CDT) if rows else np.zeros(0, CDT)
        # mints already stored (created before the tape) that reached 78 / completed inside the tape
        if len(self.Cr):
            idx = {int(m): k for k, m in enumerate(self.Cr["m"])}
            for m in set(T.M["mx"]) | set(T.cmp):
                k = idx.get(h64(m))
                if k is not None:
                    if T.M["mx"].get(m, 0) >= 78e9: self.Cr["near"][k] = 1
                    c = T.cmp.get(m)
                    if c and self.Cr["cmp_bt"][k] == 0: self.Cr["cmp_bt"][k] = c["bt"]
        comb = np.concatenate([self.Cr, new]); prio = np.concatenate([np.zeros(len(self.Cr), np.int8), np.ones(len(new), np.int8)])
        # keep the earliest create per mint but merge near/cmp flags
        o = np.lexsort((prio, comb["m"])); comb = comb[o]
        first = np.ones(len(comb), bool); first[1:] = comb["m"][1:] != comb["m"][:-1]
        grp = np.cumsum(first) - 1
        near = np.zeros(grp.max() + 1 if len(grp) else 0, np.int64); np.maximum.at(near, grp, comb["near"].astype(np.int64))
        cbm = np.zeros_like(near); np.maximum.at(cbm, grp, comb["cmp_bt"].astype(np.int64))
        out = comb[first].copy(); out["near"] = near; out["cmp_bt"] = cbm
        n0 = len(self.Cr); self.Cr = out; self._index(); return len(out) - n0
    def save(self):
        tmp = self.fn + ".tmp.npz"; np.savez_compressed(tmp, C=self.Cr); os.replace(tmp, self.fn)

# ---- candidates and features (m1_features.py, V=105 first crossing only) ---------------------------------------------
def first_crossing(rows, Vq=V):
    """m1 crossing logic restricted to the first crossing of Vq: returns index k or None (None also if the first row >= Vq is a sell)"""
    vs = rows["vsol"].astype(float) / 1e9
    above = np.nonzero(vs >= Vq)[0]
    if len(above) == 0: return None
    k = int(above[0])
    return k if rows["buy"][k] == 1 else None

def candidates(T):
    out = []
    for m, v in T.M["mx"].items():
        cr = T.cr.get(m)
        if v < V * 1e9 or cr is None or cr.get("mayhem") or m not in T.mid: continue
        mg = T.mig.get(m)
        if mg and not mg["quote"].startswith("So111"): continue
        out.append(m)
    return out

def features(T, m, rows, k, ws, cs, Vq=V, ncross=0):
    cr = T.cr[m]
    vs = rows["vsol"].astype(float) / 1e9; sol = rows["sol"].astype(float) / 1e9; buy = rows["buy"] == 1
    slot = rows["slot"].astype(np.int64); bt = rows["bt"].astype(np.int64); user = rows["user"].astype(np.int64)
    tok = rows["tok"].astype(float)
    cb = np.concatenate([[0.0], np.cumsum(np.where(buy, sol, 0))]); cs_ = np.concatenate([[0.0], np.cumsum(np.where(buy, 0, sol))])
    cnb = np.concatenate([[0], np.cumsum(buy)]); cns = np.concatenate([[0], np.cumsum(~buy)])
    first50 = np.nonzero(vs >= 50)[0]; first80 = np.nonzero(vs >= 80)[0]
    t50 = bt[first50[0]] if len(first50) else None; t80 = bt[first80[0]] if len(first80) else None
    # balances up to k
    bal = collections.defaultdict(float)
    dev = cr["creator"]; dev_id = T.uid.get(dev, -1)
    cre_slot = cr["slot"]; snip_users = set(user[slot == cre_slot][buy[slot == cre_slot]].tolist())
    dev_sold = False
    for i in range(k + 1):
        u = user[i]
        if buy[i]: bal[u] += tok[i]
        else:
            bal[u] -= tok[i]
            if u == dev_id: dev_sold = True
    vals = np.array(list(bal.values())); keys = np.array(list(bal.keys()))
    vals = np.maximum(vals, 0); tot = vals.sum()
    srt = np.sort(vals)[::-1]
    sn = dict(top1=srt[0] / tot if tot > 0 else 0, top5=srt[:5].sum() / tot if tot > 0 else 0,
              nhold=int((vals > tot * 1e-4).sum()), dev_share=max(bal.get(dev_id, 0), 0) / tot if tot > 0 else 0,
              dev_sold=float(dev_sold), snip_share=sum(max(bal.get(u2, 0), 0) for u2 in snip_users) / tot if tot > 0 else 0,
              holders=(keys[vals > 0], vals[vals > 0]))
    f = collections.OrderedDict()
    Kk = vs[k] * (rows["vtok"][k] / 1e9); Vc = Kk / ((rows["vtok"][k] - rows["rtok"][k]) / 1e9) if rows["rtok"][k] else vs[k]
    t = int(bt[k]); sk = int(slot[k])
    f["V"] = Vq; f["vsol"] = vs[k]; f["sol_left"] = max(Vc - vs[k], 0); f["ncross"] = ncross
    f["cross_sol"] = sol[k]; f["age_s"] = t - cr["bt"]; f["t_since50"] = t - t50 if t50 is not None else -1
    f["t_since80"] = t - t80 if t80 is not None else -1
    f["n_tr"] = k + 1; f["n_buys"] = cnb[k + 1]; f["n_sells"] = cns[k + 1]; f["buy_sol_tot"] = cb[k + 1]; f["sell_sol_tot"] = cs_[k + 1]
    f["vmax_prev"] = vs[:k].max() if k else vs[k]; f["dd"] = vs[k] / max(f["vmax_prev"], 1e-9)
    for (sec, nsl) in WIN:
        a = int(np.searchsorted(slot, sk - nsl, "left"))
        f[f"net{sec}"] = cb[k + 1] - cb[a] - (cs_[k + 1] - cs_[a]); f[f"buy{sec}"] = cb[k + 1] - cb[a]; f[f"sell{sec}"] = cs_[k + 1] - cs_[a]
        f[f"nb{sec}"] = cnb[k + 1] - cnb[a]; f[f"ns{sec}"] = cns[k + 1] - cns[a]
        w = slice(a, k + 1); bb = buy[w]
        f[f"ub{sec}"] = len(set(user[w][bb].tolist())); f[f"maxb{sec}"] = sol[w][bb].max() if bb.any() else 0.0
    for kk in ("top1", "top5", "nhold", "dev_share", "dev_sold", "snip_share"): f[kk] = sn[kk]
    f["dev_prior_n"], f["dev_prior_near"], f["dev_prior_grad"] = cs.cstats(dev, cr["bt"])
    mh = h64(m)
    a = int(np.searchsorted(slot, sk - 47, "left")); w = slice(a, k + 1); bb = buy[w]
    bu = user[w][bb]; bs = sol[w][bb]
    uu, inv = np.unique(bu, return_inverse=True); usol = np.bincount(inv, weights=bs)
    st = ws.wstats([h64(s) for s in T.strings[uu]], t, mh)
    f["b10_n_known"] = int((st["n"] >= 3).sum()); f["b10_pnl"] = float(st["pnl"].sum()); f["b10_pnl_w"] = float((st["pnl"] * usol).sum() / max(usol.sum(), 1e-9))
    f["b10_ngrate"] = float(((st["ngg"] + 1) / (st["ng"] + 2) * usol).sum() / max(usol.sum(), 1e-9))
    f["b10_ng_n"] = float(st["ng"].sum()); f["b10_ngg_n"] = float(st["ngg"].sum())
    f["b10_completer_max"] = float(st["cp"].max()); f["b10_compslot_max"] = float(st["cs"].max()); f["b10_poolopen_max"] = float(st["po"].max())
    f["b10_bots_po"] = int((st["po"] >= 3).sum()); f["b10_sol_po"] = float(usol[st["po"] >= 3].sum())
    f["b10_winrate"] = float(((st["win"] + 1) / (st["n"] + 2) * usol).sum() / max(usol.sum(), 1e-9))
    st1 = ws.wstats([h64(T.strings[user[k]])], t, mh)
    for kk in ("n", "pnl", "ng", "ngg", "cp", "po"): f[f"cx_{kk}"] = float(st1[kk][0])
    hk, hv = sn["holders"]
    if len(hk):
        sh = ws.wstats([h64(s) for s in T.strings[hk]], t, mh); tot = hv.sum()
        f["hold_po_share"] = float(hv[sh["po"] >= 3].sum() / tot); f["hold_cp_share"] = float(hv[sh["cp"] >= 2].sum() / tot)
        f["hold_known_share"] = float(hv[sh["n"] >= 5].sum() / tot); f["hold_pnl_w"] = float((sh["pnl"] * hv).sum() / tot)
        f["hold_ngrate_w"] = float(((sh["ngg"] + 1) / (sh["ng"] + 2) * hv).sum() / tot)
    else:
        for kk in ("hold_po_share", "hold_cp_share", "hold_known_share", "hold_pnl_w", "hold_ngrate_w"): f[kk] = 0.0
    pk_ = pkt(t); f["hour"] = pk_.hour + pk_.minute / 60; f["wday"] = pk_.weekday()
    return f

# ---- continuation model checkpoints (m3_sim.py ck_feats) -----------------------------------------------------------
def ck_feats(rows, k, Vq, p0, hour):
    out = {}
    slot = rows["slot"].astype(np.int64); vs = rows["vsol"].astype(float) / 1e9; sol = rows["sol"].astype(float) / 1e9; buy = rows["buy"] == 1
    cb = np.concatenate([[0.0], np.cumsum(np.where(buy, sol, 0))]); cs = np.concatenate([[0.0], np.cumsum(np.where(buy, 0, sol))])
    cnb = np.concatenate([[0], np.cumsum(buy)])
    comp = np.nonzero(rows["rtok"] == 0)[0]; c = int(comp[0]) if len(comp) else None
    for sec in CKS:
        s2 = slot[k] + int(sec / SLOT_S); j = int(np.searchsorted(slot, s2, "right")) - 1
        if j < k or (c is not None and j >= c) or slot[-1] < s2: out[sec] = None; continue
        a10 = int(np.searchsorted(slot, s2 - 47)); a30 = int(np.searchsorted(slot, s2 - 141))
        Kk = vs[j] * (rows["vtok"][j] / 1e9); Vc = Kk / ((rows["vtok"][j] - rows["rtok"][j]) / 1e9)
        f = [Vq, vs[j], vs[j] / vs[k], Vc - vs[j], cb[j + 1] - cb[a10] - (cs[j + 1] - cs[a10]), cb[j + 1] - cb[a30] - (cs[j + 1] - cs[a30]),
             cnb[j + 1] - cnb[a10], cnb[j + 1] - cnb[a30], sec, p0, hour, vs[:j + 1].max() / vs[j]]
        y = (c is not None) and (slot[c] - s2) * SLOT_S <= 120
        out[sec] = (np.array(f, np.float32), float(y))
    return out

# ---- replay of one entry (m3_sim.py sim_row, V=105, frozen exits, both modes) --------------------------------------
def sim_row(T, m, rows, k, mode, PCrow, DLY, size=SIZE):
    """PCrow: dict sec -> continuation p (or None). Returns dict with expected P&L per EXITS, fill share, diagnostics."""
    c_ = np.nonzero(rows["rtok"] == 0)[0]; c = int(c_[0]) if len(c_) else None
    mg = T.mig.get(m)
    K_ = float(rows["vsol"][k]) * float(rows["vtok"][k]); f = (float(rows["fbps"][k]) + float(rows["cbps"][k])) / 1e4
    sk, ik = int(rows["slot"][k]), int(rows["idx"][k]); ck = T.clock(sk, ik)
    cclock = T.clock(int(rows["slot"][c]), int(rows["idx"][c])) if c is not None else np.inf
    P = T.pool_events(mg["pool"]) if mg else None; cm = T.clock(mg["slot"], mg["idx"]) if mg else None
    out = np.zeros(len(EXITS)); filled = 0.0; nfill_vs = []; tries_tot = 0.0; why = {}; gk = np.zeros(len(EXITS)); pre_hits = 0
    kinds = [collections.Counter() for _ in EXITS]; wec = 0; land_before = 0; land_slots = []; land_idx_gap = []
    pool_q_at_sell = []; reverts = 0.0; nomig = False; unresolved = False
    arm_k = None
    if mode == "pre":
        vs = rows["vsol"].astype(float) / 1e9
        j = k
        while j > 0 and vs[j - 1] >= V - DELTA: j -= 1
        arm_k = j if j < k else k
    for je, jx in PAIR:
        de, dx = DLY[je], DLY[jx]
        e = None; cost = 0.0; mode_used = "react"
        if mode == "pre" and arm_k < k:
            ca = T.clock(int(rows["slot"][arm_k]), int(rows["idx"][arm_k]))
            pos = ca + de + np.arange(A * R_TRIES) / R_TRIES
            pos = pos[pos <= ca + A]
            ntry = 0; t_ = arm_k
            for p_ in pos:
                s_, i_ = T.position(p_)
                t_ = last_before(rows, s_, i_)
                if t_ < arm_k: ntry += 1; continue
                if rows["rtok"][t_] == 0: break
                v_ = float(rows["vsol"][t_]) / 1e9
                if V <= v_ <= V + W:
                    e = t_; mode_used = "pre"; pre_hits += 1; break
                ntry += 1
            cost += (ntry + (R_TRIES if e is not None else 0)) * TRY_COST
            if e is None and (pos[-1] if len(pos) else ca) < ck:
                e = None
            elif e is None:
                out -= cost; why["pre_miss"] = why.get("pre_miss", 0) + 1; tries_tot += ntry; continue
        if e is None:
            se, ie = T.position(ck + de)
            if (se, ie) <= (sk, ik): se, ie = sk, ik + 1
            e = max(last_before(rows, se, ie), k)
            if rows["rtok"][e] == 0:
                out -= cost + FAIL_COST; why["late"] = why.get("late", 0) + 1; reverts += 1; continue
        Ve, Te, Re = float(rows["vsol"][e]), float(rows["vtok"][e]), float(rows["rtok"][e])
        x = size * 1e9 / (1 + f); Vc = K_ / (Te - Re)
        if Ve + x >= Vc: xx = Vc - Ve; q = Re; we_complete = True
        else: xx = x; q = Te - K_ / (Ve + x); we_complete = False
        spent = xx * (1 + f) / 1e9
        if mode_used == "react":
            qd = float(rows["vtok"][k]) - K_ / (float(rows["vsol"][k]) + x)
            if (xx / q) > GUARD * (x / qd):
                out -= cost + FAIL_COST; why["guard"] = why.get("guard", 0) + 1; reverts += 1; continue
        filled += 1; nfill_vs.append(Ve / 1e9); tries_tot += cost / TRY_COST if mode == "pre" else 0
        wec += we_complete; land_before += 1
        ce = T.clock(int(rows["slot"][e]), int(rows["idx"][e])) if e > k else T.clock(*T.position(ck + de))
        land_slots.append(int(np.floor(ce)) - sk); land_idx_gap.append(e - k)
        end = c if c is not None else len(rows) - 1
        lim = int(np.searchsorted(rows["slot"], int(rows["slot"][e]) + int(600 / SLOT_S) + 50, "right")) - 1
        end = min(end, max(lim, e))
        idx = np.arange(e + 1, end + 1) if end > e else np.arange(0)
        V2 = rows["vsol"][idx].astype(float) + xx
        val = (V2 - K_ / (K_ / V2 + q)) * (1 - f) / 1e9
        if len(idx):
            sl_ = rows["slot"][idx].astype(np.int64); nn = np.maximum(T.N[np.clip(sl_ - T.slo, 0, len(T.N) - 1)], 1)
            clk = sl_ + np.minimum(rows["idx"][idx] / nn, 0.999999)
        else: clk = np.zeros(0)
        def curve_exit(dec):
            sx, ix = T.position(dec + dx); t = last_before(rows, sx, ix)
            if c is not None and t >= c: return None
            if we_complete: return None
            t = max(t, e); V3 = float(rows["vsol"][t]) + xx
            return (V3 - K_ / (K_ / V3 + q)) * (1 - f) / 1e9
        grad_val = {}; gq = None
        if (c is not None or we_complete) and mg is not None:
            sx, ix = T.position(cm + EXITS[0][0] + dx); kk = last_before(P, sx, ix)
            pb, pq = pool_state_after(P, kk, mg); fee = pool_fee(P, kk)
            grad_val[EXITS[0][0]] = (pq - pb * pq / (pb + q)) * (1 - fee) / 1e9; gq = pq / 1e9
        elif c is not None or we_complete:
            pb, pq = 206.9e12, 84.99e9
            grad_val[EXITS[0][0]] = (pq - pb * pq / (pb + q)) * (1 - 0.0125) / 1e9; nomig = True; gq = pq / 1e9
        pd_dec = {}
        for th in (0.3,):
            dec = None
            for sec in CKS:
                pc = PCrow.get(sec)
                if pc is not None and pc < th: dec = ck + sec / SLOT_S; break
            pd_dec[th] = dec
        for xi, (n, st, to) in enumerate(EXITS):
            dec = ce + to / SLOT_S
            if isinstance(st, float) and len(val):
                hit = np.nonzero(val <= (1 - st) * spent)[0]
                if len(hit): dec = min(dec, clk[hit[0]])
            elif isinstance(st, str):
                pdd = pd_dec[float(st[2:])]
                if pdd is not None and pdd > ce: dec = min(dec, pdd)
            v = None; kind = "curve"
            if not we_complete and (c is None or dec < cclock):
                v = curve_exit(dec)
                if v is not None:
                    if dec < ce + to / SLOT_S: kind = "stop" if isinstance(st, float) else "pd"
                    else: kind = "timeout"
                    if T.position(dec + dx)[0] > T.shi: kind = "unresolved"; unresolved = True
            if v is None:
                if c is None and not we_complete: v = val[-1] if len(val) else 0.0; kind = "unresolved"; unresolved = True
                elif n in grad_val: v = grad_val[n]; gk[xi] += 1; kind = "grad"
                else: v = np.nan; kind = "nan"
            kinds[xi][kind] += 1
            out[xi] += v - spent - RT_COST - cost
        if gq is not None: pool_q_at_sell.append(gq)
    nP = len(PAIR)
    res = dict(mode=mode, res=(out / nP).tolist(), fill=filled / nP, why={k: v / nP for k, v in why.items()}, gradexit=(gk / nP).tolist(),
               pre_share=pre_hits / nP, fill_vs=float(np.mean(nfill_vs)) if nfill_vs else None, tries=tries_tot / nP, reverts=reverts / nP,
               we_complete=wec / nP, land_slots=float(np.mean(land_slots)) if land_slots else None,
               land_rows=float(np.mean(land_idx_gap)) if land_idx_gap else None, kinds=[dict(kc) for kc in kinds],
               pool_q_sell=float(np.mean(pool_q_at_sell)) if pool_q_at_sell else None, nomig=nomig, unresolved=unresolved)
    res["res_try03"] = [r - (tries_tot / nP) * (TRY_COST_HI - TRY_COST) for r in res["res"]] if mode == "pre" else list(res["res"])
    res["res_rev005"] = [r + (reverts / nP) * (FAIL_COST - TRY_COST) for r in res["res"]] if mode == "react" else list(res["res"])
    if mg is not None and P is not None and len(P):
        kk = last_before(P, mg["slot"] + 2, 0); pb, pq = pool_state_after(P, kk, mg)
        res["sniped"] = bool((pq / pb) < (mg["pquote"] / mg["pbase"]) * 0.999)
    return res
