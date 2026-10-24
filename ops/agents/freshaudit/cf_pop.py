#!/usr/bin/env python3
# counterfactual over EVERY dump our live bot scored (dump events of r1..r5): first-in-line vs our measured landing kernel
import sys, json, glob, gzip, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from sim import *
A = "/home/moiz/sniper/ops/agents/freshaudit"
TP = load_tapes(f"{A}/out/tapes_live.json.gz")
K = json.load(open(f"{A}/out/kernel.json"))
SL = {}
for f in sorted(glob.glob(f"{A}/x/r3/*.jsonl.gz"))[-75:]:
    for l in gzip.open(f, "rt"):
        if l.startswith('["SLOTS'): SL.update({int(a): b for a, b in json.loads(l)[1].items()})
D = []
for n in range(1, 6):
    for l in open(f"/home/moiz/sniper/ops/dip/speed/dip_r{n}.jsonl"):
        e = json.loads(l)
        if e["ev"] == "dump": D.append(dict(run=n, mint=e["mint"], slot=e["slot"], idx=e["idx"], sig=e["sig"], score=e["score"], ps=e["pass"], sell=e["sell"], age=e.get("age"), drop=e.get("drop_pct"), dev=e.get("dev")))
B = 0.35; TIP = 3_000_000
EXITS = [("h1", ("time", 1, 100)), ("h2", ("time", 2, 100)), ("h3", ("time", 3, 100)), ("h5", ("time", 5, 100)), ("h8", ("time", 8, 100)), ("h12", ("time", 12, 100))]
def work(d):
    rows = TP.get(d["mint"])
    if not rows: return None
    tr_all = trades(rows)
    dst = None
    for t in tr_all:
        if (t[0], t[1]) == (d["slot"], d["idx"]) and t[3] == 0: dst = (t[7], t[8]); fr = (t[9] + t[10]) / 1e4; break
    if dst is None: return None
    tr = [t for t in tr_all if t[6] != OURS]
    tr = [t for t in tr if d["slot"] - 1 <= t[0] <= d["slot"] + 16]
    if dst[0] < 25e9 or dst[0] > 110e9: return None
    out = dict(d)
    first = (d["slot"], d["idx"] + 1)
    for nm, ex in EXITS:
        r = simulate(tr, first, dst, B, guard=1.05, exit_mode=ex, fr=fr, tip=TIP)
        out["F_" + nm] = round(r["pnl_net"], 5) if r else None
    bs = SL.get(d["slot"], [None])[0] or 400
    agg = collections.defaultdict(float); n = 0
    for k in K:
        if k["ds"] == 0:
            oi = d["idx"] + k["dIdx"]
            pos = (d["slot"], oi) if oi <= bs else (d["slot"] + 1, 20)
        else:
            pos = (d["slot"] + 1, k["oi"])
        n += 1
        for g in (1.05, 1.10, 1.15, None):
            r = simulate(tr, pos, dst, B, guard=g, exit_mode=("time", 5, 100), fr=fr, tip=TIP)
            if r is None: continue
            agg[f"K{g}_fill"] += r["fill"]; agg[f"K{g}_pnl"] += r["pnl_net"]
        r = simulate(tr, pos, dst, B, guard=1.05, exit_mode=("time", 2, 100), fr=fr, tip=TIP)
        if r: agg["K1.05h2_pnl"] += r["pnl_net"]
    for k, v in agg.items(): out[k] = round(v / n, 6)
    out["vsol"] = dst[0]
    return out
if __name__ == "__main__":
    with Pool(4) as p:
        res = [r for r in p.imap(work, D, chunksize=50) if r]
    json.dump(res, open(f"{A}/out/cf_pop.json", "w"))
    print("dumps", len(D), "simulated", len(res))
