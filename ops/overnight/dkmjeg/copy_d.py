#!/usr/bin/env python3
# READ-ONLY replay check: how much of the oracle profit is dKMjeG's OWN buy landing after ours? Same placement/guard
# as copy_c.py, quick sell at 0.5 SOL, (1) real path, (2) path with dKMjeG's trades removed (as if its buy failed).
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = rp.load_launches(); O = rp.load_obs()
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
ATT = {m for m, v in C.items() if "dk" in v}
todo = [m for m in ATT if m in L and L[m]["run"] == "R2" and m in O and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
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
            if ib < 1 or (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: continue
            o1 = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015); o2 = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015, me=W)
            if o1 and o2: r[Lm] = dict(real=o1["eos1"]["pnl"], nodk=o2["eos1"]["pnl"], dk_after=(kd is not None and kd >= ib), dk_buy=kd is not None)
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    for Lm in (45, 75):
        v = [r[Lm] for r in res.values() if Lm in r]
        a = [x for x in v if x["dk_after"]]; b = [x for x in v if not x["dk_after"]]
        print(f"L{Lm}: our guarded fills {len(v)} | dK's buy lands AFTER ours in {len(a)} (real {sum(x['real'] for x in a):+.2f}, without dK's trades {sum(x['nodk'] for x in a):+.2f}) | "
              f"dK not after us / no dK buy {len(b)} (real {sum(x['real'] for x in b):+.2f}) | all: real {sum(x['real'] for x in v):+.2f}, without dK {sum(x['nodk'] for x in v):+.2f}")
