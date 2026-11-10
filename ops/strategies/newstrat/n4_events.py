#!/usr/bin/env python3
"""NEWSTRAT step 4: per-BUY follower outcomes for generic 'react to a buy' ideas (leader-follow, retail-wave).
For every landed curve BUY >= 0.05 SOL on a non-mayhem mint launched in the run (and >= 2 h into the run so wallet history exists):
  signing-time features (all from rows landed at or before the trigger buy):
    u (buyer), rt (route id), spend, pc (buyer's prior trades in this run), age (slots since create), vs (vSOL after the buy, SOL),
    rb10 / rs10 (# buys / SOL bought in the last 10 slots incl. this one by wallets with pc < 30, 'retail-like'),
    nb10 / nf10 (# buys / net SOL flow in the last 10 slots, all wallets), imp (price move of this buy, %)
  outcomes (lamports, our 0.55 SOL, entry = trigger CC + D, fixed exit k slots after entry):
    D in 0/50/70/90 x k in 2/5/10/25/150; plus f20 (20 % fewer outside buys in 10 slots) at D=70 for k 5/25/150.
-> OUT/ev_<run>.npz"""
import sys
import numpy as np
import nlib as L

DS = [0, 50, 70, 90]
KS = [2, 5, 10, 25, 150]

def main(run):
    t = L.load(run)
    la = L.launches(run)
    nm = len(t.mints)
    # prior trade count of the signer at each row (time order)
    o = np.lexsort((t.cc, t.u))
    pc = np.empty(len(t.u), np.int32)
    us = t.u[o]
    start = np.r_[0, np.nonzero(np.diff(us))[0] + 1]
    rank = np.arange(len(us)) - np.repeat(start, np.diff(np.r_[start, len(us)]))
    pc[o] = rank
    del o, us, rank
    t0 = float(t.cc.min()) + 2 * 3600e3
    cols = {k: [] for k in ["u", "rt", "spend", "pc", "age", "vs", "rb10", "rs10", "nb10", "nf10", "imp", "cc", "m"]}
    outs = {f"d{D}k{k}": [] for D in DS for k in KS}
    for k in (5, 25, 150): outs[f"f20k{k}"] = []
    for mi in range(nm):
        mint = str(t.mints[mi]); lv = la.get(mint)
        if lv is None or lv["may"]: continue
        a0, a1 = t.mstart[mi], t.mstart[mi + 1]
        if a1 - a0 < 5: continue
        M = L.Mint(t, mi)
        o = np.argsort(t.cc[a0:a1], kind="stable") + a0
        P = pc[o]; RT = t.rt[o]
        spend = -M.SL.astype(np.float64)
        isb = (M.TK > 0) & (spend >= 0.05e9) & (M.CC >= t0)
        if not isb.any(): continue
        bi = np.nonzero(isb)[0]
        # windows: last 10 slots incl. this row
        lo = np.searchsorted(M.S, M.S[bi] - 10, side="left")
        ret = (M.TK > 0) & (P < 30)
        crb = np.r_[0, np.cumsum(ret)]; crs = np.r_[0, np.cumsum(np.where(ret, spend, 0.0))]
        cnb = np.r_[0, np.cumsum(M.TK > 0)]; cnf = np.r_[0, np.cumsum(spend)]
        hi = bi + 1
        cp = M.CP[bi]; cq = M.CQ[bi]
        cols["u"].append(M.U[bi]); cols["rt"].append(RT[bi]); cols["spend"].append(spend[bi] / 1e9); cols["pc"].append(P[bi])
        cols["age"].append(M.S[bi] - lv["slot"]); cols["vs"].append(L.vsol(cq) / 1e9)
        cols["rb10"].append(crb[hi] - crb[lo]); cols["rs10"].append((crs[hi] - crs[lo]) / 1e9)
        cols["nb10"].append(cnb[hi] - cnb[lo]); cols["nf10"].append((cnf[hi] - cnf[lo]) / 1e9)
        cols["imp"].append((L.price(cq) / L.price(cp) - 1) * 100); cols["cc"].append(M.CC[bi]); cols["m"].append(np.full(len(bi), mi, np.int32))
        for D in DS:
            tin = M.CC[bi] + D
            for k in KS:
                outs[f"d{D}k{k}"].append(L.trip(M, tin, tin + k * L.SMS).astype(np.float32))
        tin = M.CC[bi] + 70
        for k in (5, 25, 150):
            outs[f"f20k{k}"].append(L.trip(M, tin, tin + k * L.SMS, fol=L.FOLSHARE).astype(np.float32))
    res = {k: np.concatenate(v) for k, v in cols.items()}
    res.update({k: np.concatenate(v) for k, v in outs.items()})
    res["users"] = t.users; res["routes"] = t.routes; res["mints"] = t.mints; res["hours"] = np.array([L.hours(t) - 2])
    np.savez(f"{L.OUT}/ev_{run}.npz", **res)
    print(run, "events", len(res["u"]), flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)
