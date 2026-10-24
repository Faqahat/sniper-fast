#!/usr/bin/env python3
# READ-ONLY, offline: same as replay.py but with CWiNFA's OWN trades removed from the curve path (rp.sim me=...), for the
# launches it attempted or that a walk-forward CWiNFA list could pick. Shows how much of our simulated profit on its picks
# comes from its own 1 SOL buy landing right after ours. Output: replay_nocw.json
import os, sys, json, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
SH = "/home/moiz/sniper-data/collect/shadow"
L = rp.load_launches(); O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
R = json.load(open(os.path.join(HERE, "replay_all.json")))
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
deps = {C[m].get("dep") for m in C if C[m].get("dep")}
todo = [m for m, r in R.items() if r["run"] == "R2" and (m in C or r["dep"] in deps)]
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
EOS = rp.R("eos", [(1.0, ("slot", 1))], 5); T1 = rp.R("t1", [(1.0, ("t", 1))], 2)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); r = {}
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: continue
            cw_after = any(t["user"] == W and t["buy"] for t in tr[ib:])
            a = rp.sim(tr, c, st, ib, 0.5, [EOS], fill_pen=0.015, me=W)
            b2 = rp.sim(tr, c, st, ib, 1.0, [T1], fee_buy_pct=0.006, sell_fee_sol=0.0011, fill_pen=0.015, me=W)
            r[str(Lm)] = dict(cw_after=cw_after, eos05=a["eos"]["pnl"] if a else None, cw10=b2["t1"]["pnl"] if b2 else None)
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(os.path.join(HERE, "replay_nocw.json"), "w"))
    print("launches", len(res))
