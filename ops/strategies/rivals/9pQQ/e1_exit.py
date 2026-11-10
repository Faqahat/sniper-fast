#!/usr/bin/env python3
"""9pQQ exits: for every closed trip, walk the other wallets' trades during the hold and record the state after each one.
Row cols: trip n, slots since its buy, secs, ret (curve price vs right after its buy), dd (vs peak since its buy), side (+1 buy / -1 sell),
size SOL, is_last (last other trade before its sell), slots_to_sell, slots since the previous other buy, net flow (SOL) last 10 slots,
net flow since entry, trader's trade count (bot-ness), seller had bought during this hold (follower exit), share of
follower tokens sold so far, distinct sellers since entry, slots since the previous outside sell (buys only), after_its_sell flag, slot, idx.  -> exits_<run>.npy.  Read-only on inputs.  usage: e1_exit.py"""
import pickle, collections, sys
import numpy as np
import tlib9 as L

def build(run):
    t = L.load_tape(run)
    wid = t.user_ix[L.W]
    ucnt = np.bincount(t.u, minlength=len(t.users))
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{run}.pkl", "rb")) if x["net"] is not None and x.get("tape_ok")]
    rows = []
    for n, x in enumerate(T):
        mi = t.mint_ix[x["mint"]]; a0, a1 = t.mstart[mi], t.mstart[mi + 1]
        S = t.s[a0:a1]; key = S * 10000 + t.i[a0:a1]
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        p0 = L.price(t.cpost[a0 + jb]); pk = p0
        lastb = x["bs"]; cumf = 0.0; fl = collections.deque()
        fb = collections.Counter(); fsold = 0.0; fbought = 0.0; sellers = set(); lasts = x["bs"]
        # last trade by others before its sell (index)
        last = None
        for j in range(js - 1, jb, -1):
            if t.u[a0 + j] != wid: last = j; break
        jend = int(np.searchsorted(S, x["bs"] + 2800, side="right"))     # rows continue past its sell (for policy tests), flagged
        for j in range(jb + 1, max(js, jend)):
            g = a0 + j
            if t.u[g] == wid: continue
            p = L.price(t.cpost[g]); pk = max(pk, p)
            sg = -t.sol[g] / 1e9                                  # + = SOL into the curve (buy)
            cumf += sg; fl.append((t.s[g], sg))
            while fl and fl[0][0] < t.s[g] - 10: fl.popleft()
            f10 = sum(v for _, v in fl)
            gap_b = t.s[g] - lastb
            uu = int(t.u[g]); fol_sell = 0
            if t.tok[g] > 0: fb[uu] += t.tok[g]; fbought += t.tok[g]
            else:
                sellers.add(uu)
                if fb.get(uu, 0) > 0:
                    q = min(fb[uu], -t.tok[g]); fb[uu] -= q; fsold += q; fol_sell = 1
            rows.append((n, t.s[g] - x["bs"], t.bt[g] - x["bbt"], p / p0 - 1, p / pk - 1, 1 if t.tok[g] > 0 else -1, abs(t.sol[g]) / 1e9,
                         1 if j == last else 0, x["ss"] - t.s[g], gap_b, f10, cumf, ucnt[uu], fol_sell, fsold / fbought if fbought else 0.0,
                         len(sellers), t.s[g] - lasts if t.tok[g] > 0 else 0, 1 if j > js else 0, t.s[g], t.i[g]))
            if t.tok[g] > 0: lastb = t.s[g]
            else: lasts = t.s[g]
    a = np.array(rows, dtype=float)
    np.save(f"{L.OUT}/exits_{run}.npy", a)
    return a, T

if __name__ == "__main__":
    for r in L.RUNS:
        a, T = build(r)
        print(r, a.shape, flush=True)
