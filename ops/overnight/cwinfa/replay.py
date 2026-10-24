#!/usr/bin/env python3
# READ-ONLY, offline replay (no money): outcome table for every R2 launch with our engine's timeline (block-order placement
# place_bo2 with failed-tx anchors, the S4 mechanics), at 45 and 75 ms. Per launch and latency:
#   ok      = our 1% price guard passes (spot before our buy <= 1.01 x the post-bundle price); a guard fail costs 0.005 SOL
#   eos05   = OUR pattern: 0.5 SOL, sell at the end of the next slot, our costs (2% buy overhead, 0.0005 per sell)
#   cw10    = ITS pattern on our entry: 1.0 SOL, sell ~1 s after the buy (t=1 s), its costs (0.6% buy overhead, 0.0011 per sell)
#   cw10_7  = 1.0 SOL, sell 7 slots after the buy (its median sell delay), its costs
#   eos10c  = 1.0 SOL, end of next slot, its costs   |  h1_05 = 0.5 SOL, t=1 s, our costs   | eos05c = 0.5 SOL eos, its costs
#   ng_*    = the same without the guard (fill wherever we land)
# Also the R1 launches with the block-position proxy (old data, pessimistic) for the deployer-gate history.
# Data: R2 rows = hardlinked snapshot of phaseA_dry (02:44 UTC), timelines = scores_v1/v2 + scores_v3 snapshot.
import os, sys, json, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
SH = "/home/moiz/sniper-data/collect/shadow"
L = rp.load_launches(); O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
todo = [m for m, c in L.items() if c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or []) and (c["run"] == "R1" or m in O)]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
EOS = rp.R("eos", [(1.0, ("slot", 1))], 5); T1 = rp.R("t1", [(1.0, ("t", 1))], 2); S7 = rp.R("s7", [(1.0, ("slot", 7))], 3)
def outcomes(tr, c, st, ib):
    o = {}
    a = rp.sim(tr, c, st, ib, 0.5, [EOS, T1], fill_pen=0.015)                                   # our costs
    if a: o["eos05"] = a["eos"]["pnl"]; o["h1_05"] = a["t1"]["pnl"]
    b = rp.sim(tr, c, st, ib, 1.0, [EOS, T1, S7], fee_buy_pct=0.006, sell_fee_sol=0.0011, fill_pen=0.015)   # its costs
    if b: o["eos10c"] = b["eos"]["pnl"]; o["cw10"] = b["t1"]["pnl"]; o["cw10_7"] = b["s7"]["pnl"]
    d = rp.sim(tr, c, st, ib, 0.5, [EOS], fee_buy_pct=0.006, sell_fee_sol=0.0011, fill_pen=0.015)
    if d: o["eos05c"] = d["eos"]["pnl"]
    return o
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        r = dict(run=run, bt=c["bt"], dep=c["user"], dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3), glued=len(st["glued"]))
        for Lm in (45, 75):
            if run == "R2": ib, nah = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            else: ib, nah = rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            mult = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b
            d = dict(ok=mult <= 1.01, mult=round(mult, 4), ahead=nah)
            oc = outcomes(tr, c, st, ib)
            for k, v in oc.items(): d["ng_" + k] = round(v, 6)
            if d["ok"]:
                for k, v in oc.items(): d[k] = round(v, 6)
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(os.path.join(HERE, "replay_all.json"), "w"))
    print("launches:", len(res), dict(collections.Counter(v["run"] for v in res.values())))
