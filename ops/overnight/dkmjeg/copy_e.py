#!/usr/bin/env python3
# READ-ONLY replay check for the WALK-FORWARD deployer list (from its attempts) and the R1-trained MODEL picks: how much
# of our replayed profit needs dKMjeG's own buy landing after ours (path with its trades removed = it does not buy)?
import sys, json, collections, statistics as S, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
import numpy as np
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = rp.load_launches(); O = rp.load_obs(); AR = json.load(open("/home/moiz/sniper/ops/overnight/core/allres.json"))
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json")); ATT = {m for m, v in C.items() if "dk" in v}
def wf(Lm, k=2, rate=0.10):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt")); na = collections.Counter(); nl = collections.Counter(); pick = set()
    for bt, m in ev:
        d = L[m]["user"]
        if na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate): pick.add(m)
        nl[d] += 1
        if m in ATT: na[d] += 1
    return pick
LIST = wf("75")
R = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/sel_rows.json")); src = open("/home/moiz/sniper/ops/overnight/dkmjeg/sel2.py").read(); g = {}
exec(src[src.index("def f(r):"):src.index("X = np.array")], {"math": math}, g); exec(src[src.index("def fit("):src.index("tr = run ==")], {"np": np}, g)
X = np.array([g["f"](r) for r in R]); y = np.array([r["att"] for r in R], dtype=float); run = np.array([r["run"] for r in R])
w, mu, sd = g["fit"](X[run == "R1"], y[run == "R1"]); s2 = g["pred"](w, mu, sd, X[run == "R2"]); R2m = [r["m"] for r in R if r["run"] == "R2"]
MODEL = {m for m, sc in zip(R2m, s2) if sc >= np.quantile(s2, 0.98)}
SETS = {"walk-forward list": LIST, "model top 2%": MODEL}
todo = {m for s in SETS.values() for m in s if m in L and L[m]["run"] == "R2" and m in O and "InitializeMayhemState" not in (L[m].get("ixn") or [])}
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        kd = next((k for k, t in enumerate(tr) if t["user"] == W and t["buy"]), None)
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[Lm] = dict(fail=True); continue
            o1 = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015); o2 = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015, me=W)
            if o1 and o2: r[Lm] = dict(real=o1["eos1"]["pnl"], nodk=o2["eos1"]["pnl"], dk_after=(kd is not None and kd >= ib))
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    for nm, sset in SETS.items():
        for Lm in (45, 75):
            v = [res[m][Lm] for m in sset if m in res and Lm in res[m]]
            f = [x for x in v if not x.get("fail")]; a = [x for x in f if x["dk_after"]]
            print(f"{nm:18} L{Lm}: launches {len(v)}, fills {len(f)} (fail cost {-0.005 * (len(v) - len(f)):+.2f}) | real {sum(x['real'] for x in f):+.2f} | without dK's trades {sum(x['nodk'] for x in f):+.2f} | "
                  f"fills where dK lands after us {len(a)}: real {sum(x['real'] for x in a):+.2f} vs without dK {sum(x['nodk'] for x in a):+.2f}")
