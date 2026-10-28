#!/usr/bin/env python3
"""GAP step 10a (read-only): MEASURED pre-send landing for the pre-send-style entry model.
(1) For each of our live pre-send FILLS (tape buy by our wallet whose tx has CU limit 120000 = pre-send, as in the main-session check):
    the trigger dump = latest outside sell with single-trade drop >= 5 % before our fill within 2 slots; k = outside rows between the
    dump and our fill; ms after the dump (chain clock); same-slot share.
(2) Fill rate of armed windows in which the armed whale actually sold (disarm 'filled' vs 'whale_sold'), all live pre-send runs.
(3) MEASURED cost per pre-send fill episode and per unfilled arm (wallet SOL, episodes from g3).
Out: gap/g10a.json, g10a.txt"""
import json, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
R, MI, span, CC = X.tape()
ours = [MI["who"]["FRA"], MI["who"]["AMS"]]
cul = {}
for l in open("/home/moiz/sniper-data/dv8/tab/ours.jsonl"):
    d = json.loads(l)
    if d["err"] is None: cul[(d["s"], d["i"])] = d.get("cul")
ks = []; ms = []; same = []; nod = 0
mine_rows = np.flatnonzero(np.isin(R["user"], ours) & (R["buy"] == 1))
for g in mine_rows.tolist():
    s, i = int(R["slot"][g]), int(R["idx"][g])
    if cul.get((s, i)) != 120000: continue
    m = int(R["mint"][g]); a, b = span[m]
    M = X.Mint(m); k = g - a
    o = ~np.isin(M.us, ours)
    drop = np.where(~M.bu, 1 - M.px / M.pxp, 0)
    lo = int(np.searchsorted(M.sl, M.sl[k] - 2))
    c = [j for j in range(lo, k) if o[j] and not M.bu[j] and drop[j] >= 0.05]
    if not c: nod += 1; continue
    j = c[-1]
    ks.append(int(o[j + 1:k].sum())); ms.append(float(M.cc[k] - M.cc[j])); same.append(M.sl[k] == M.sl[j])
G = pickle.load(open(f"{OUT}/g2_engine.pkl", "rb"))
why = collections.Counter()
for X_ in G.values():
    for a in X_["arms"]:
        if not a[9]: why[a[5]] += 1
Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); eps = Z["eps"]
fe = [E for E in eps if E["path"] == "ps" and E["fill"]]
xe = [E for E in eps if E["path"] == "ps" and not E["fill"]]
fill_cost = np.mean([E["gross"] - E["pnl"] for E in fe]); x_cost = np.mean([-E["pnl"] for E in xe])
J = dict(k=ks, ms=ms, same=float(np.mean(same)), n=len(ks), no_dump=nod, disarm=dict(why), fill_cost=float(fill_cost), x_cost=float(x_cost),
         n_fill_ep=len(fe), n_x_ep=len(xe), fill_rate_whale_sold=why["filled"] / max(why["filled"] + why["whale_sold"], 1))
json.dump(J, open(f"{OUT}/g10a.json", "w"))
txt = (f"pre-send fills with a >=5% dump within 2 slots before: {len(ks)} (no dump found: {nod}); k (outside rows between dump and fill) "
       f"p10/50/90 {np.percentile(ks, [10, 50, 90])}, share k=0 {np.mean(np.array(ks) == 0):.2f}; ms after dump p10/50/90 {np.percentile(ms, [10, 50, 90]).round(0)}; same slot {np.mean(same):.2f}\n"
       f"arm outcomes (live, all runs): {dict(why)}; fill rate when the armed whale sold = filled/(filled+whale_sold) = {J['fill_rate_whale_sold']:.2f}\n"
       f"MEASURED cost per pre-send fill episode (fees+tips+failed tries+rent net, wallet) {1000 * fill_cost:.2f} mSOL over {len(fe)}; per unfilled pre-send episode {1000 * x_cost:.3f} mSOL over {len(xe)}")
print(txt); open(f"{OUT}/g10a.txt", "w").write(txt + "\n")
