#!/usr/bin/env python3
"""Reactive-dip-buy speed by landed path and leader client: haqq (path = tip account of the landed copy) vs our regular fills and pre-send
fills (MEASURED, chain clock dump -> own buy; dump = previous outside trade is a sell >= 0.5 SOL within 2 slots).
Out: sniper-data/haqq_dissect/exec/t7_pathspeed.txt"""
import sys, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
D = "/home/moiz/sniper-data/haqq_dissect/exec"
rows = pickle.load(open(f"{D}/txs.pkl", "rb"))
info = {(r["s"], r["i"]): r for r in rows if r["kind"] == "buy" and r["ok"]}
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
sl = np.asarray(T["slot"], np.int64); ix = np.asarray(T["idx"], np.int64); mint = np.asarray(T["mint"]); sg = np.asarray(T["signer"]); us = np.asarray(T["user"])
buy = np.asarray(T["buy"]); sol = np.asarray(T["sol"], np.float64) / 1e9
ids, idx = L.ids_map()
o = np.lexsort((T["j"], ix, sl, mint)); ms = L.cc(sl, ix)
mo, so, io, go, uo, bo, vo, mso = mint[o], sl[o], ix[o], sg[o], us[o], buy[o], sol[o], ms[o]
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
for who, wal in (("haqq", L.HAQQ), ("FRA", L.WAL["FRA"]), ("AMS", L.WAL["AMS"])):
    wid = idx[wal]; mine = (go == wid) | (uo == wid)
    res = collections.defaultdict(list)
    for p in np.nonzero(mine & (bo == 1))[0]:
        q = p - 1
        while q >= 0 and mo[q] == mo[p] and mine[q]: q -= 1
        if q < 0 or mo[q] != mo[p] or bo[q] != 0 or vo[q] < 0.5 or so[p] - so[q] > 2: continue
        r = info.get((int(so[p]), int(io[p])))
        if r is None: continue
        _, cc, _ = L.leader_info(int(so[p]), "FRA" if who == "haqq" else who)
        kind = "presend" if (who != "haqq" and r["fee"] < 10000) else ("regular" if who != "haqq" else ("hi" if r["fee"] >= 60000 else "lo"))
        d = float(mso[p] - mso[q]); same = so[p] == so[q]
        res[(kind, r["path"])].append((d, same)); res[(kind, "ALL")].append((d, same)); res[(kind, "client:" + cc)].append((d, same))
    P(f"===== {who}: reactive dip buys, dump -> buy (chain clock ms)")
    for k in sorted(res, key=lambda k: (k[0], -len(res[k]))):
        v = res[k]
        if len(v) < 15: continue
        d = np.array([x[0] for x in v]); s = np.array([x[1] for x in v])
        P(f"  {k[0]:8} {k[1]:28} n={len(v):6} med {np.median(d):6.0f} p25 {np.percentile(d,25):5.0f} p75 {np.percentile(d,75):5.0f} same-slot {100*s.mean():4.0f}%")
open(f"{D}/t7_pathspeed.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
