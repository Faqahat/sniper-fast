#!/usr/bin/env python3
"""9pQQ selection universe.  Decision moments = every OTHER wallet's landed curve trade on a token launched inside the recording,
while 9pQQ holds no position on that token.  Label = 9pQQ's next buy on that token lands in the same slot or the next one and this
trade is the last outside trade before it (= the trade it reacted to).  Vectorised over the whole tape.
Features: side, size, age, curve SOL, mayhem, net flow / buy counts / distinct trades in 1/10/75/150 slots, price change 10/75 slots,
drawdown from the 450-slot high (approx.: max over trades in window), trades so far, creator has sold, trader is a high-volume wallet,
9pQQ round trips already done on the token and slots since its last sell there, PKT hour.
Outcome (for taken vs skipped): curve price change from right after the event to 25/100/400 slots later (its own trades included).
-> uni_<run>.npz.  Read-only on inputs.  usage: s1_universe.py [run ...]"""
import sys, pickle
import numpy as np
import tlib9 as L

def build(run):
    t = L.load_tape(run); la = L.launches(run)
    wid = t.user_ix[L.W]
    n = len(t.s); s0 = int(t.s.min())
    key = (t.m.astype(np.int64) << 32) | (t.s - s0)
    me = t.u != wid
    sg = np.where(me, -t.sol, 0).astype(np.float64) / 1e9                 # + = SOL into the curve (buy) by others
    isb = (me & (t.tok > 0)).astype(np.int64)
    cs = np.concatenate([[0.0], np.cumsum(sg)]); cb = np.concatenate([[0], np.cumsum(isb)]); ct = np.concatenate([[0], np.cumsum(me.astype(np.int64))])
    P = L.price(t.cpost.astype(np.float64))
    F = {}
    for w in (1, 10, 75, 150):
        lo = np.searchsorted(key, key - w, "left")
        F[f"flow{w}"] = cs[np.arange(n) + 1] - cs[lo]
        F[f"nbuy{w}"] = (cb[np.arange(n) + 1] - cb[lo]).astype(np.float64)
        F[f"ntr{w}"] = (ct[np.arange(n) + 1] - ct[lo]).astype(np.float64)
        if w in (10, 75): F[f"dp{w}"] = P / P[lo] - 1
    # drawdown from the high of the last 450 slots: running max over a sliding window (approx. with block max via reduceat over windows is costly;
    # use the max price among trades in window via a sparse table)
    lo450 = np.searchsorted(key, key - 450, "left")
    K = int(np.log2(max(2, (np.arange(n) - lo450).max() + 1))) + 1
    sp = [P]
    for k in range(1, K):
        prev = sp[-1]; h = 1 << (k - 1)
        sp.append(np.maximum(prev, np.concatenate([prev[h:], np.full(h, -np.inf)])))
    ln = np.arange(n) - lo450 + 1
    kk = np.floor(np.log2(ln)).astype(int)
    mx = np.empty(n)
    for k in range(K):
        sel = kk == k
        if sel.any():
            a = lo450[sel]; b = np.arange(n)[sel] - (1 << k) + 1
            mx[sel] = np.maximum(sp[k][a], sp[k][b])
    F["dd450"] = P / mx - 1
    del sp
    # token facts
    mints = t.mints
    lslot = np.array([la[m]["slot"] if m in la else -1 for m in mints], np.int64)
    may = np.array([la[m]["may"] if m in la else False for m in mints], bool)
    crt = np.array([t.user_ix.get(la[m]["creator"], -2) if m in la else -2 for m in mints], np.int64)
    F["age"] = np.where(lslot[t.m] >= 0, t.s - lslot[t.m], np.nan).astype(np.float64)
    F["may"] = may[t.m].astype(np.float64)
    F["vsol"] = L.vsol(t.cpost.astype(np.float64)) / 1e9
    F["side"] = np.sign(t.tok).astype(np.float64)
    F["size"] = np.abs(t.sol) / 1e9
    F["ntr_sofar"] = (np.arange(n) - t.mstart[t.m]).astype(np.float64)
    ucnt = np.bincount(t.u, minlength=len(t.users))
    F["trader_cnt"] = ucnt[t.u].astype(np.float64)
    # creator has sold before (or at) this trade
    devsell = (t.u == crt[t.m]) & (t.tok < 0)
    cds = np.concatenate([[0], np.cumsum(devsell)])
    F["dev_sold"] = ((cds[np.arange(n) + 1] - cds[t.mstart[t.m]]) > 0).astype(np.float64)
    F["hour"] = ((t.bt // 3600 + 5) % 24).astype(np.float64)
    # 9pQQ state: holding mask, label, round trips done, slots since its last sell
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{run}.pkl", "rb")) if x.get("tape_ok")]
    hold = np.zeros(n, bool); y = np.zeros(n, np.int8); trip_net = np.full(n, np.nan)
    kdone = np.zeros(n, np.float64); since = np.full(n, np.nan)
    for x in T:
        mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
        kk_ = key[a0:a1]; ii = t.i[a0:a1]; ss_ = t.s[a0:a1]
        jb = a0 + int(np.searchsorted(ss_ * 10000 + ii, x["bs"] * 10000 + x["bi"]))
        js = a0 + int(np.searchsorted(ss_ * 10000 + ii, x["ss"] * 10000 + x["si"])) if x.get("ss") else a1
        hold[jb:js + 1] = True
        j = jb - 1
        while j >= a0 and t.u[j] == wid: j -= 1
        if j >= a0 and x["bs"] - t.s[j] <= 1:
            y[j] = 1; trip_net[j] = x["net"] / 1e9 if x["net"] is not None else np.nan
        if x.get("ss"):
            kdone[js + 1:a1] += 1
            since[js + 1:a1] = t.s[js + 1:a1] - x["ss"]           # later trips overwrite: slots since the latest sell
    F["k_done"] = kdone; F["since_sell"] = since
    # outcome: price change from right after the event to H slots later (last trade at or before s+H on the same token)
    for H in (25, 100, 400):
        ix = np.searchsorted(key, key + H, "right") - 1
        F[f"fwd{H}"] = P[ix] / P - 1
    keep = me & ~hold & (lslot[t.m] >= 0)
    out = {k: v[keep].astype(np.float32) for k, v in F.items()}
    out["y"] = y[keep]; out["trip_net"] = trip_net[keep].astype(np.float32)
    out["s"] = t.s[keep]; out["m"] = t.m[keep]; out["u"] = t.u[keep]; out["bt"] = t.bt[keep]
    np.savez(f"{L.OUT}/uni_{run}.npz", **out)
    print(run, "events", int(keep.sum()), "labels", int(out["y"].sum()), "of trips", len(T), flush=True)

if __name__ == "__main__":
    for r in (sys.argv[1:] or L.RUNS): build(r)
