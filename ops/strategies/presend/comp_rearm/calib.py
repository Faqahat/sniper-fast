#!/usr/bin/env python3
"""base replay (D7b, r37 hours) vs live AMS r37 (MEASURED records) on the same usable hours"""
import json, pickle, numpy as np, collections
R = pickle.load(open("/home/moiz/sniper-data/comp_rearm/res_D7b.pkl", "rb")); hs = set(h // 3600 for h in R["meta"]["hours"])
L = [json.loads(l) for l in open("/home/moiz/sniper-data/wave37/dip_ams_r37.jsonl") if l.startswith("{")]
fill_t = {r["mint"]: r["t"] for r in L if r.get("ev") == "presend_live_fill"}
arms = [r for r in L if r.get("ev") == "presend_live_arm"]
real = [r for r in L if r.get("ev") == "presend_live_realized"]
def tsec(t): return t / 1000 if t > 1e11 else t
lf = [r for r in real if r["mint"] in fill_t and int(tsec(fill_t[r["mint"]]) // 3600) in hs]
fee = 0
print("hours", len(hs), "live fills", len(lf), "live realized SOL", round(sum(r["pnl"] for r in lf), 3), "live per fill mSOL", round(np.mean([r["pnl"] for r in lf]) * 1e3, 1))
print("live arms in hours", sum(1 for r in arms if int(tsec(r.get('t', 0) or 0) // 3600) in hs), "(t may be missing)")
o = R["out"]["base"]; SZ = int(0.696e9)
nf = []; g = []; arm = []; fails = []
for k, x in o.items():
    rs = [r for r in x["rows"] if r["armed"] and r["bt"] // 3600 in hs]
    arm.append(len(rs)); f = [r for r in rs if r.get("filled")]; nf.append(len(f))
    g.append(sum(r["grid"][(SZ, 0.2, 0.0)] for r in f) / 1e9); fails.append(sum(r["nfail"] for r in rs))
print("replay arms", np.mean(arm), "fills", np.mean(nf), "gross SOL", round(np.mean(g), 3), "[draws", round(min(g), 2), round(max(g), 2), "] per fill mSOL", round(np.mean(g) / np.mean(nf) * 1e3, 1), "failed tries", np.mean(fails))
