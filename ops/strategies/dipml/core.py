#!/usr/bin/env python3
"""VM1 independent check: shared data + my own curve math, features and model evaluator (no code from the copy).

Token universe ("normal SOL curve"): vsol*vtok = 30 SOL x 1.073e15 within 0.5% on every trade, never a Mayhem-agent
trade (fee 0/0 or vsol < 29.9 SOL), first recorded trade starts from the pristine curve (pre-state 30 SOL), so the whole
history is in the recording. Chain order = (slot, tx index, event index).
"""
import json, os
import numpy as np

D = "/home/moiz/sniper-data/dipml"
SLOT_SEC = 0.21207            # measured: block time vs slot over the 3.3 days recorded (fit 0.21207 s/slot)
K0 = 30e9 * 1.073e15          # pump.fun constant product (lamports x token units)
S0 = 459_700_000              # slot origin for packed keys
MAYHEM_AGENT = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"

def pack(mint, slot, idx, j=0):
    """composite chain key: mint | slot | tx index | event index (int64, sortable)"""
    return (np.asarray(mint, np.int64) << 37) | ((np.asarray(slot, np.int64) - S0) << 16) | (np.asarray(idx, np.int64) << 4) | np.asarray(j, np.int64)

class Data:
    def __init__(self, d=D):
        T = np.load(os.path.join(d, "trades.npy"))
        self.users = json.load(open(os.path.join(d, "users.json"))); self.mints = json.load(open(os.path.join(d, "mints.json")))
        v = T["vsol"].astype(np.float64); t = T["vtok"].astype(np.float64)
        normal = (np.abs(v * t / K0 - 1) < 0.005) & (T["vsol"] > 0)
        try: agent = self.users.index(MAYHEM_AGENT)
        except ValueError: agent = -1
        bad = (~normal) | (T["user"] == agent) | ((T["fee_bps"] == 0) & (T["cfee_bps"] == 0)) | (T["vsol"] < 29_900_000_000)
        nm = np.zeros(len(self.mints), bool); nm[np.unique(T["mint"][normal])] = True
        bm = np.zeros(len(self.mints), bool); bm[np.unique(T["mint"][bad])] = True
        keep_m = nm & ~bm
        T = T[keep_m[T["mint"]]]
        o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"])); T = T[o]
        # pristine start: first trade's pre-state is 30 SOL
        first = np.ones(len(T), bool); first[1:] = T["mint"][1:] != T["mint"][:-1]
        sgn = np.where(T["buy"] == 1, -1, 1).astype(np.int64)
        pre = T["vsol"].astype(np.int64) + sgn * T["sol"].astype(np.int64)
        pristine_m = np.zeros(len(self.mints), bool); pristine_m[T["mint"][first & (pre == 30_000_000_000)]] = True
        self.full_hist = pristine_m           # per mint: full history recorded
        self.T = T
        self.G = pack(T["mint"], T["slot"], T["idx"], T["j"])
        self.pre_vsol = pre
        # chain consistency (a missing trade breaks it)
        ok = np.ones(len(T), bool); ok[1:] = (pre[1:] == T["vsol"][:-1].astype(np.int64)) | first[1:]
        self.chain_ok = ok
        mm = T["mint"]; self.mstart = np.searchsorted(mm, np.arange(len(self.mints)), "left"); self.mend = np.searchsorted(mm, np.arange(len(self.mints)), "right")
        S = np.load(os.path.join(d, "slots.npy"))
        self.slot_lo, self.slot_hi = int(S["slot"].min()), int(S["slot"].max())
        n = self.slot_hi - self.slot_lo + 1
        self.N = np.zeros(n, np.int32); self.N[S["slot"].astype(np.int64) - self.slot_lo] = S["maxi"].astype(np.int32) + 1   # block size estimate (0 = no block seen)
        self.BT = np.zeros(n, np.int64); self.BT[S["slot"].astype(np.int64) - self.slot_lo] = S["bt"]
        self.holes = json.load(open(os.path.join(d, "holes.json")))
        # leader schedule
        L = np.full(n, -1, np.int32); self.leader_ids = []
        for ep in ():
            a = np.load(os.path.join(d, f"leaders_e{ep}.npy")); first_slot = ep * 432000
            lo = max(first_slot, self.slot_lo); hi = min(first_slot + 432000 - 1, self.slot_hi)
            if lo <= hi: L[lo - self.slot_lo: hi - self.slot_lo + 1] = a[lo - first_slot: hi - first_slot + 1]
        self.L = L

    # ---- block clock -------------------------------------------------------------------------------------------
    def bsize(self, slot):
        slot = np.asarray(slot, np.int64); k = np.clip(slot - self.slot_lo, 0, len(self.N) - 1)
        return self.N[k]
    def clock(self, slot, idx):
        """block-clock time in slot units: slot + idx / block size"""
        n = self.bsize(slot).astype(np.float64); n[n <= 0] = 1
        return np.asarray(slot, np.float64) + np.minimum(np.asarray(idx, np.float64) / n, 0.999999)
    def position(self, tclock):
        """block-clock time -> (slot, idx) of a tx landing then; a slot with no block -> start of the next produced block"""
        tclock = np.asarray(tclock, np.float64); slot = np.floor(tclock).astype(np.int64); frac = tclock - slot
        n = self.bsize(slot)
        for _ in range(8):                         # skip slots without a block
            miss = n <= 0
            if not miss.any(): break
            slot = np.where(miss, slot + 1, slot); frac = np.where(miss, 0.0, frac); n = self.bsize(slot)
        idx = np.floor(frac * np.maximum(n, 1)).astype(np.int64)
        return slot, idx
    def leader(self, slot):
        k = np.clip(np.asarray(slot, np.int64) - self.slot_lo, 0, len(self.L) - 1); return self.L[k]
    def pkt(self, slot):
        import datetime as dt
        k = int(np.clip(slot - self.slot_lo, 0, len(self.BT) - 1))
        while self.BT[k] == 0 and k > 0: k -= 1
        return dt.datetime.fromtimestamp(int(self.BT[k]), dt.timezone(dt.timedelta(hours=5)))

    # ---- state lookup ------------------------------------------------------------------------------------------
    def state_before(self, mint, slot, idx):
        """index of the token's last trade strictly before chain position (slot, idx) (-1 if none)"""
        g = pack(mint, slot, idx, 0)
        k = np.searchsorted(self.G, g, "left") - 1
        mint = np.asarray(mint)
        ok = (k >= 0) & (k >= self.mstart[mint]) & (k < self.mend[mint])
        return np.where(ok, k, -1)

    def dumps(self, min_sol=1e9, vlo=25e9, vhi=200e9):
        T = self.T
        m = (T["buy"] == 0) & (T["sol"] >= min_sol) & (T["vsol"] >= vlo) & (T["vsol"] <= vhi)
        return np.where(m)[0]

# ---- features: my own implementation of the 16 named features (two readings) ---------------------------------
FEATS = ["sell", "drop", "curve", "age", "flow15", "sells15", "buyers5", "buyers15", "ntr", "gap_last", "ch15", "ch60",
         "max_curve", "dev_like", "n_bigsells60", "seller_bought"]

def features(D, kidx, mode="model"):
    """kidx: global trade indices of dumps. mode 'plain' = my reading of the names; mode 'model' = the training
    semantics of the frozen model as specified in its documentation (window of whole slots s-24/s-70/s-282 inclusive,
    0.2126 s/slot for age/gap, ch15/ch60 against the FIRST trade inside the window, 0 if none)."""
    T = D.T; out = np.full((len(kidx), 16), np.nan)
    if mode == "model":
        W5, W15, W60, SEC = 24, 70, 282, 0.2126
    else:
        SEC = SLOT_SEC; W5, W15, W60 = int(5 / SEC), int(15 / SEC), int(60 / SEC)    # s - slot <= W  (W = 23, 70, 282)
    P = T["vsol"].astype(np.float64) / T["vtok"].astype(np.float64)
    for r, k in enumerate(kidx):
        m = T["mint"][k]; a = D.mstart[m]; s = int(T["slot"][k])
        sl = T["slot"][a:k]                           # trades strictly before the dump (chain order)
        n_before = k - a
        a5 = a + np.searchsorted(sl, s - W5, "left"); a15 = a + np.searchsorted(sl, s - W15, "left"); a60 = a + np.searchsorted(sl, s - W60, "left")
        sol = T["sol"][k] / 1e9; vs = T["vsol"][k]; vt = T["vtok"][k]
        pre_p = (vs + T["sol"][k]) / max(vt - T["tok"][k], 1)
        post_p = vs / vt
        b15 = T["buy"][a15:k] == 1; b5 = T["buy"][a5:k] == 1
        so15 = T["sol"][a15:k]
        f = out[r]
        f[0] = sol
        f[1] = 1 - post_p / pre_p
        f[2] = vs / 1e9
        f[3] = (s - int(T["slot"][a])) * SEC
        f[4] = so15[b15].sum() / 1e9
        f[5] = so15[~b15].sum() / 1e9
        f[6] = len(np.unique(T["user"][a5:k][b5]))
        f[7] = len(np.unique(T["user"][a15:k][b15]))
        f[8] = n_before
        f[9] = (s - int(T["slot"][k - 1])) * SEC if n_before else 99.0
        if mode == "model":
            f[10] = post_p / P[a15] - 1 if a15 < k else 0.0
            f[11] = post_p / P[a60] - 1 if a60 < k else 0.0
        else:   # price at the window start = after the last trade BEFORE the window (pristine price if none)
            p0 = 30e9 / 1.073e15
            f[10] = post_p / (P[a15 - 1] if a15 > a else p0) - 1
            f[11] = post_p / (P[a60 - 1] if a60 > a else p0) - 1
        f[12] = T["vsol"][a:k + 1].max() / 1e9
        f[13] = float(n_before < 3)
        s60 = (T["buy"][a60:k] == 0) & (T["sol"][a60:k] >= 1_000_000_000)
        f[14] = s60.sum()
        u = T["user"][k]
        f[15] = float(np.any((T["user"][a:k] == u) & (T["buy"][a:k] == 1)))
    return out

# ---- the frozen model: my own evaluator of its json (edges + trees) -------------------------------------------
class Model:
    def __init__(self, path="/home/moiz/sniper-landfix/ops/landfix/vm1.json"):
        j = json.load(open(path))
        assert j["features"] == FEATS, "feature order differs"
        self.edges = [np.array(e, float) for e in j["edges"]]; self.F0 = j["F0"]; self.lr = j["lr"]; self.cut = j["cut"]
        self.trees = j["trees"]; self.trained_until_slot = j["trained_until_slot"]
    def bins(self, X):
        B = np.zeros(X.shape, np.int64)
        for c in range(X.shape[1]):
            x = X[:, c]; b = np.searchsorted(self.edges[c], x, side="right") + 1    # bin = #edges <= x, +1; NaN -> 0
            b[np.isnan(x)] = 0; B[:, c] = b
        return B
    def score(self, X):
        B = self.bins(np.asarray(X, float)); f = np.full(len(B), self.F0)
        for t in self.trees:
            f += self.lr * self._tree(t, B)
        return f
    def _tree(self, t, B):
        out = np.zeros(len(B)); stack = [(t, np.arange(len(B)))]
        while stack:
            n, ix = stack.pop()
            if "w" in n: out[ix] = n["w"]; continue
            go_l = B[ix, n["f"]] <= n["b"]
            stack.append((n["l"], ix[go_l])); stack.append((n["r"], ix[~go_l]))
        return out
