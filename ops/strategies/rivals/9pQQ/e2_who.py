#!/usr/bin/env python3
"""9pQQ exits: which wallets' trades (during its hold) are followed by its sell within 1 slot -> per-wallet hazard; and whether the
seller was a co-entrant (bought the same mint within +-3 slots of 9pQQ's buy).  Read-only.  usage: e2_who.py"""
import pickle, collections, numpy as np, tlib9 as L
tot = collections.Counter(); hit = collections.Counter(); co = collections.Counter(); coh = collections.Counter()
for run in L.RUNS:
    t = L.load_tape(run); wid = t.user_ix[L.W]
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{run}.pkl", "rb")) if x["net"] is not None and x.get("tape_ok")]
    for x in T:
        mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
        S = t.s[a0:a1]; key = S * 10000 + t.i[a0:a1]; U = t.u[a0:a1]; TK = t.tok[a0:a1]
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        lo = int(np.searchsorted(S, x["bs"] - 3)); hi = int(np.searchsorted(S, x["bs"] + 3, side="right"))
        coent = set(U[lo:hi][(TK[lo:hi] > 0)].tolist()) - {wid}
        last = None
        for j in range(js - 1, jb, -1):
            if U[j] != wid: last = j; break
        for j in range(jb + 1, js):
            if U[j] == wid or TK[j] > 0: continue           # sells by others only
            u = t.users[U[j]]
            tg = (j == last and x["ss"] - S[j] <= 1)
            tot[u] += 1; hit[u] += tg
            c = U[j] in coent
            co[c] += 1; coh[c] += tg
print("P(9pQQ sells within 1 slot | other's sell during hold), by co-entrant:", {k: (co[k], round(coh[k] / co[k], 3)) for k in co})
rows = sorted(((hit[u] / tot[u], tot[u], hit[u], u) for u in tot if tot[u] >= 100), reverse=True)
print("wallets with >=100 sells inside its holds, top by hazard:")
for h, n, k, u in rows[:25]: print(f"  {u[:12]} n {n:6d} hits {k:5d} P {h:.2f}")
print("bottom:", [(u[:8], n, round(h, 3)) for h, n, k, u in rows[-8:]])
allh = sum(hit.values()); print("total sell-triggered exits", allh, "covered by wallets with P>=0.3:", sum(hit[u] for u in tot if tot[u] >= 20 and hit[u] / tot[u] >= 0.3))
