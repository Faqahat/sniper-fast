#!/usr/bin/env python3
# READ-ONLY, offline replay: on OUR guarded entries (R2, block-order placement at 45 / 75 ms, 1% guard), does
# dKMjeG's size (1.8 SOL) or its exit pattern (time ladder: half at ~2 s, a quarter at ~4 s, rest by ~6.5 s; or "dump
# all at ~2 s") beat our quick sell (all at the end of the next slot) at 0.5 SOL?  Sets: its attempted launches
# (oracle) and the walk-forward deployer list.
import sys, json, collections, statistics as S
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
ATT = {m for m, v in C.items() if "dk" in v}
todo = [m for m in ATT if m in L and L[m]["run"] == "R2" and m in O and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1 (ours)", [(1.0, ("slot", 1))], 5),
      rp.R("all at ~2 s (slot 9)", [(1.0, ("slot", 9))], 5),
      rp.R("dK ladder 50%@2.1s 25%@3.8s rest@6.4s", [(0.5, ("slot", 10)), (0.25, ("slot", 18)), (1.0, ("slot", 30))], 10),
      rp.R("dK big-size ladder 30%@1.3s 25%@3.2s 25%@6.4s rest@12.7s", [(0.3, ("slot", 6)), (0.25, ("slot", 15)), (0.25, ("slot", 30)), (1.0, ("slot", 60))], 20),
      rp.R("hold ~4.5 s (its median last sell)", [(1.0, ("slot", 21))], 8)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            d = dict(ok=ok)
            if ok:
                for B in (0.5, 1.8):
                    o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015)
                    if o: d[str(B)] = {k: v["pnl"] for k, v in o.items()}
            r[str(Lm)] = d
        out[m] = (c["bt"], r)
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    t0 = min(v[0] for v in res.values()); t1 = max(v[0] for v in res.values()); mid = t0 + (t1 - t0) / 2
    OUT = {}
    for Lm in ("45", "75"):
        for B in ("0.5", "1.8"):
            for e in EX:
                v = []
                for m, (bt, r) in res.items():
                    if Lm not in r: continue
                    if not r[Lm]["ok"]: v.append((bt, -0.005)); continue
                    x = r[Lm].get(B, {}).get(e["name"])
                    if x is not None: v.append((bt, x))
                tot = sum(x for _, x in v); a = sum(x for t, x in v if t < mid); nf = sum(1 for _, x in v if x != -0.005)
                print(f"L{Lm} size {B} | {e['name']:58} total {tot:+7.2f} SOL ({a:+.2f}/{tot - a:+.2f}) fills {nf}/{len(v)} | per fill {sum(x for _, x in v if x != -0.005) / max(1, nf):+.4f}")
                OUT[f"L{Lm}_{B}_{e['name']}"] = dict(tot=round(tot, 3), h1=round(a, 3), h2=round(tot - a, 3), fills=nf, n=len(v))
    json.dump(OUT, open("/home/moiz/sniper/ops/overnight/dkmjeg/copy_c.json", "w"), indent=1)
