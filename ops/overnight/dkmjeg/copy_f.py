#!/usr/bin/env python3
# READ-ONLY replay: oracle set again, but dKMjeG's own buy now FAILS when our insert pushes the price past its real
# min_tokens_out (decoded from its txs) -> does our size (0.5 vs 1.8 SOL) price it out? Optional: other followers'
# decoded limits too (core/slip_args.jsonl, built by another study).
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = rp.load_launches(); O = rp.load_obs()
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json")); ATT = {m for m, v in C.items() if "dk" in v}
A = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/buy_args.json"))
SL_DK = {s: ("sol", a["amt"], a["minout"]) for s, a in A.items() if a.get("amt") and a.get("minout")}
SL_ALL = dict(rp.load_slip()); SL_ALL.update(SL_DK)
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
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[Lm] = None; continue
            d = {}
            for B in (0.5, 1.8):
                for nm, sl in (("none", None), ("dK", SL_DK), ("all", SL_ALL)):
                    o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015, slip=sl)
                    if o: d[f"{B}_{nm}"] = (o["eos1"]["pnl"], o["eos1"].get("slipped", 0))
            r[Lm] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    for Lm in (45, 75):
        v = [x[Lm] for x in res.values() if Lm in x]; nfail = sum(1 for x in v if x is None); f = [x for x in v if x]
        cells = []
        for k in ("0.5_none", "0.5_dK", "0.5_all", "1.8_none", "1.8_dK", "1.8_all"):
            z = [x[k] for x in f if k in x]
            cells.append(f"{k}: {sum(p for p, _ in z) - 0.005 * nfail:+.2f} (slipped buys {sum(s for _, s in z)})")
        print(f"L{Lm} fills {len(f)}/{len(v)} | " + " | ".join(cells))
