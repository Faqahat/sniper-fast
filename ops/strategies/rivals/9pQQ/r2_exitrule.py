#!/usr/bin/env python3
"""9pQQ exit approximation (T3).  On ITS picks, entered by us DELTA ms after the trade it reacted to (0.55 SOL, 4.5 mSOL cost,
9pQQ removed), compare exits: its real exit (+ our extra delay), fixed holds, and a rule family we can run:
  'drought' : sell when no outside buy for N slots (decided at the start of slot last_buy+N),
  'bigsell' : or as soon as an outside sell >= X SOL lands,
  'cap'     : or after C slots.
Sell lands DELTA ms after the decision.  Grid chosen on 10-28 + 10-30 (train) -> pick on 10-31 -> report 11-02.
-> exitrule.json.  Read-only.  usage: r2_exitrule.py [DELTA]"""
import sys, pickle, json, itertools, collections
import numpy as np
import tlib9 as L, rlib9 as R
from a3_clusters import label

D = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
NS = (3, 6, 12, 25, 50, 100, 200); XS = (None, 1.0, 2.0, 4.0); CS = (150, 700, 1400, 2800)
GRID = list(itertools.product(NS, XS, CS))

def run(r):
    t = L.load_tape(r); wid = t.user_ix[L.W]; s0, bsz = R.blocksizes(r)
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and x["net"] is not None]
    rows = []; cache = {}
    for x in T:
        mi = t.mint_ix[x["mint"]]
        M = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = M
        key = M.S * 10000 + M.I
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        if js >= len(M.S) or M.U[js] != wid or M.U[jb] != wid: continue
        j = jb - 1
        while j >= 0 and M.U[j] == wid: j -= 1
        trig = M.CC[j] if j >= 0 else M.CC[jb]
        ti = trig + D
        e = int(np.searchsorted(M.CC, ti, side="right"))
        es = int(M.S[e]) if e < len(M.S) else int(M.S[-1])
        hi = int(np.searchsorted(M.S, es + max(CS), side="right"))
        o = (np.arange(e, hi))[~M.is9[e:hi]]
        bs_ = M.S[o][M.TK[o] > 0]                                     # outside buy slots after entry
        ssz = np.where(M.TK[o] < 0, M.SL[o] / 1e9, 0.0)               # outside sell sizes
        scc = M.CC[o]
        res = {"its": R.trip(M, ti, M.CC[js] + max(0.0, D - 45), drop9=True)}
        res["its_fol"] = R.trip(M, ti, M.CC[js] + max(0.0, D - 45), drop9=True, fol=0.2)
        for hs in (6, 30, 150):
            res[f"fix{hs}"] = R.trip(M, ti, ti + hs * R.SMS, drop9=True)
        b = np.concatenate([[es], bs_])
        gaps = np.diff(np.concatenate([b, [10 ** 12]]))
        for N, X, C in GRID:
            k = int(np.argmax(gaps >= N)); dec = (b[k] + N) * R.SMS
            if X is not None:
                q = np.where(ssz >= X)[0]
                if len(q): dec = min(dec, scc[q[0]])
            dec = min(dec, (es + C) * R.SMS)
            dec = max(dec, ti)
            res[(N, X, C)] = R.trip(M, ti, dec + D, drop9=True)
            if (N, X, C) in CHOSEN: res[("fol",) + (N, X, C)] = R.trip(M, ti, dec + D, drop9=True, fol=0.2)
        res["lab"] = label(x)[0]
        rows.append(res)
    return rows

CHOSEN = set()
if __name__ == "__main__":
    allr = {}
    for r in L.RUNS[:3]: allr[L.DAY[r]] = run(r)
    tr = allr["10-28"] + allr["10-30"]
    score = {g: sum(x[g] for x in tr) for g in GRID}
    top = sorted(GRID, key=lambda g: -score[g])[:10]
    pick = max(top, key=lambda g: sum(x[g] for x in allr["10-31"]))
    CHOSEN.add(pick)
    allr["11-02"] = run(L.RUNS[3])
    out = {"delta_ms": D, "train_top10": [(str(g), round(score[g] / 1e9, 2)) for g in top], "picked_on_10-31": str(pick)}
    for day, rows in allr.items():
        o = {}
        for k in ["its", "its_fol", "fix6", "fix30", "fix150", pick] + ([("fol",) + pick] if day == "11-02" else []):
            v = np.sort(np.array([x[k] for x in rows if k in x]) / 1e9)
            if not len(v): continue
            o[str(k)] = dict(net=round(v.sum(), 2), msol=round(1000 * v.mean(), 2), wo_top5=round(v[:-5].sum(), 2))
        for lab in ("LAUNCH", "DIP", "MOMO", "DRIFT"):
            for k in ("its", pick):
                v = np.sort(np.array([x[k] for x in rows if x["lab"] == lab]) / 1e9)
                o[f"{lab} {k}"] = dict(n=len(v), net=round(v.sum(), 2), msol=round(1000 * v.mean(), 2), wo_top5=round(v[:-5].sum(), 2))
        out[day] = o
        print(day, json.dumps(o), flush=True)
    print(json.dumps({k: out[k] for k in ("train_top10", "picked_on_10-31")}))
    json.dump(out, open(f"/home/moiz/sniper/ops/strategies/rivals/9pQQ/exitrule_{int(D)}.json", "w"), indent=1)
