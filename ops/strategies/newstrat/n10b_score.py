#!/usr/bin/env python3
"""score LEADER-LADDER: leaders from SEL days; evaluate TARGET. usage: n10b_score.py SEL(comma) TARGET [LADMIN] [PNL 0/1] [EXSEL]"""
import sys, json, hashlib
import numpy as np
import nlib as L
from n5_scan import one_pos
import os
NMIN = int(os.environ.get("NMIN", "30"))
sel = sys.argv[1].split(","); tgt = sys.argv[2]; lmin = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
pnl = int(sys.argv[4]) if len(sys.argv) > 4 else 0; exsel = sys.argv[5] if len(sys.argv) > 5 else "NB2"
def ld(r): z = np.load(f"{L.OUT}/n10_{r}.npz"); return {k: z[k] for k in z.files}
per = []
for r in sel:
    d = ld(r); uu, inv = np.unique(d["u"], return_inverse=True)
    n = np.bincount(inv); lad = np.bincount(inv, weights=d["lad"]); pl = np.bincount(inv, weights=d[f"d70{exsel}"].astype(np.float64))
    per.append({u: (n[j], lad[j] / n[j], pl[j]) for j, u in enumerate(uu)})
lead = sorted(set.intersection(*[set(u for u, (n, l, p) in q.items() if n >= NMIN and l >= lmin and (p >= 0 or not pnl)) for q in per]))
d = ld(tgt); hrs = float(d["hours"][0])
idx = np.nonzero(np.isin(d["u"], lead))[0]
idx = idx[one_pos(d["m"][idx], d["cc"][idx], 25, 70)]
out = {"sel": sel, "target": tgt, "ladmin": lmin, "pnl_rule": pnl, "leaders": len(lead), "events": len(idx),
       "ladder_share_target": round(float(d["lad"][idx].mean()), 3) if len(idx) else 0, "sha": hashlib.sha256("\n".join(lead).encode()).hexdigest()[:16]}
for D in (50, 70, 90):
    for ex in ("S6", "S25", "H200", "NB2"):
        v = d[f"d{D}{ex}"][idx].astype(np.float64); s = L.stats(v)
        out[f"D{D}_{ex}"] = dict(per_day=round(s["net"] / hrs * 24, 2), mSOL=s["per"], win=s["win"], wo5_day=round(s["wo5"] / hrs * 24, 2))
out["f20_D70_S25"] = round(float(d["f20_d70S25"][idx].sum()) / 1e9 / hrs * 24, 2)
uu, inv = np.unique(d["u"][idx], return_inverse=True); sl = np.bincount(inv, weights=d["d70NB2"][idx].astype(np.float64)) / 1e9
o = np.argsort(sl)[::-1]; out["top_leaders_NB2"] = [(str(uu[j])[:8], int((inv == j).sum()), round(float(sl[j]), 2)) for j in o[:5]]
out["wo_top3_leaders_NB2_day"] = round(float(sl[o[3:]].sum()) / hrs * 24, 2)
print(json.dumps(out))
json.dump({"res": out, "leaders": lead}, open(f"{L.OUT}/n10s_{lmin}_{pnl}_{exsel}_{tgt}.json", "w"))
