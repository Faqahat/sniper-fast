#!/usr/bin/env python3
# Generic-flow study, stage 1: who trades, and how each launch went.
#  - per wallet (outside the launch's dev + glued bundle): launches bought, launches where its first buy was a SNIPE
#    (create slot or the next), early (<= ~1 s), buy SOL, buy txs, txs with tips -> wallet classes in stage 2
#  - per launch: deployer, time, post-bundle price, buyers / buy SOL in 60 s, price at 10/60/300 s and peak within 300 s
#    (vs post-bundle), graduated -> deployer track records (walk-forward) in stage 2
# Data: R1 = phaseA, R2 = phaseA_gf (static snapshot). usage: RP_PHASEA_R2=phaseA_gf python3 -I gf_stage1.py
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches()
SINCE = float(os.environ.get("GF_SINCE", "0"))           # forward runs: only launches created at/after this unix time
todo = [m for m, c in L.items() if c.get("bt") and c["bt"] >= SINCE and "InitializeMayhemState" not in (c.get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
SL = rp.SLOT_MS / 1000.0
def at(tr, k_slot):
    """price (vsol/vtok) after the last trade with slot <= k_slot (None if none)"""
    p = None
    for t in tr:
        if t["s"] > k_slot: break
        p = t["vsol"] / t["vtok"] if t["vtok"] else p
    return p
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); W = {}; LS = {}
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c); ins = st["insiders"]
        g = tr[st["g_end"] - 1] if st["g_end"] >= 1 else tr[0]; p_b = g["vsol"] / g["vtok"]
        first = {}
        for t in tr:
            if t["user"] in ins: continue
            w = W.get(t["user"])
            if w is None: w = W[t["user"]] = [0, 0, 0, 0.0, 0, 0, 0, 0.0]   # launches, snipes, early, buySOL, buyTx, tipTx, sellTx, sellSOL
            if t["buy"]:
                w[3] += t["sol"] / 1e9; w[4] += 1; w[5] += 1 if t.get("tips") else 0
                if t["user"] not in first: first[t["user"]] = t["s"] - S
            else: w[6] += 1; w[7] += t["sol"] / 1e9
        for u, d in first.items():
            w = W[u]; w[0] += 1; w[1] += 1 if d <= 1 else 0; w[2] += 1 if d <= 5 else 0
        k60 = S + int(60 / SL); out = [t for t in tr if t["user"] not in ins]
        b60 = [t for t in out if t["buy"] and t["s"] <= k60]
        pk = max((t["vsol"] / t["vtok"] for t in tr if t["s"] <= S + int(300 / SL) and t["vtok"]), default=p_b)
        LS[m] = dict(run=run, bt=c["bt"], dep=c["user"], S=S, p_b=p_b, nb60=len({t["user"] for t in b60}), sb60=round(sum(t["sol"] for t in b60) / 1e9, 3),
                     m10=round((at(tr, S + int(10 / SL)) or p_b) / p_b, 4), m60=round((at(tr, k60) or p_b) / p_b, 4),
                     m300=round((at(tr, S + int(300 / SL)) or p_b) / p_b, 4), pk300=round(pk / p_b, 4),
                     grad=max(t["vsol"] for t in tr) >= rp.GRAD_VSOL, ntr=len(tr), last_s=tr[-1]["s"] - S)
    return W, LS
if __name__ == "__main__":
    W = {}; LS = {}
    with Pool(8) as p:
        for w, ls in p.imap_unordered(work, sorted(byb)):
            LS.update(ls)
            for u, v in w.items():
                x = W.get(u)
                if x is None: W[u] = v
                else:
                    for i in range(8): x[i] += v[i]
    json.dump(W, open(os.environ.get("GF_W_OUT", "/home/moiz/sniper/ops/overnight/core/gf_wallets.json"), "w"))
    json.dump(LS, open(os.environ.get("GF_LS_OUT", "/home/moiz/sniper/ops/overnight/core/gf_launches.json"), "w"))
    sn = sum(1 for v in W.values() if v[1] >= 5 and v[1] >= 0.5 * v[0])
    print(f"launches {len(LS)} ({collections.Counter(v['run'] for v in LS.values())}); wallets {len(W)}; snipers (>=5 snipes, >=50% of launches) {sn}")
