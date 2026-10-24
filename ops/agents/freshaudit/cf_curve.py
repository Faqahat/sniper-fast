#!/usr/bin/env python3
# speed curve: P&L / fill rate if our buy always landed dIdx block positions after the dump (same slot; overflow -> next slot idx 10)
import sys, json, glob, gzip, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from sim import *
A = "/home/moiz/sniper/ops/agents/freshaudit"
TP = load_tapes(f"{A}/out/tapes_live.json.gz")
SL = {}
for f in sorted(glob.glob(f"{A}/x/r3/*.jsonl.gz"))[-75:]:
    for l in gzip.open(f, "rt"):
        if l.startswith('["SLOTS'): SL.update({int(a): b for a, b in json.loads(l)[1].items()})
POP = json.load(open(f"{A}/out/cf_pop.json"))
thr8 = -0.18683692105426744
D = [r for r in POP if r["score"] >= thr8]
OFFS = [1, 10, 25, 50, 75, 100, 150, 200, 300]
def work(d):
    rows = TP.get(d["mint"]); tr_all = trades(rows)
    for t in tr_all:
        if (t[0], t[1]) == (d["slot"], d["idx"]) and t[3] == 0: dst = (t[7], t[8]); fr = (t[9] + t[10]) / 1e4; break
    tr = [t for t in tr_all if t[6] != OURS and d["slot"] - 1 <= t[0] <= d["slot"] + 16]
    bs = SL.get(d["slot"], [None])[0] or 400
    out = dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], score=d["score"], run=d["run"], bs=bs)
    for o in OFFS:
        oi = d["idx"] + o
        pos = (d["slot"], oi) if oi <= bs else (d["slot"] + 1, 10)
        for g in (1.05, None):
            r = simulate(tr, pos, dst, 0.35, guard=g, exit_mode=("time", 5, 100), fr=fr, tip=3_000_000)
            out[f"o{o}_g{g}"] = (r["fill"], round(r["pnl_net"], 5))
    return out
if __name__ == "__main__":
    with Pool(4) as p: res = list(p.imap(work, D, chunksize=20))
    json.dump(res, open(f"{A}/out/cf_curve.json", "w"))
    thr2 = 0.5419185740413283; thr4 = 0.21088520504965255
    for lab, c in (("top2", lambda r: r["score"] >= thr2), ("thr4..thr2", lambda r: thr4 <= r["score"] < thr2), ("thr8..thr4", lambda r: thr8 <= r["score"] < thr4)):
        sub = [r for r in res if c(r)]
        print(f"== {lab} n={len(sub)} (per 3.68 h)")
        for o in OFFS:
            k = f"o{o}_g1.05"; fills = sum(r[k][0] for r in sub); pnl = sum(r[k][1] for r in sub)
            k2 = f"o{o}_gNone"; pnl2 = sum(r[k2][1] for r in sub)
            pos = sum(1 for r in sub if r[k][1] > 0) / len(sub)
            print(f"   dIdx={o:>3}: fill {fills/len(sub):4.0%}  net(g5%) {pnl:+7.3f}  per-dump {pnl/len(sub):+.4f}  win {pos:4.0%}   net(no guard) {pnl2:+7.3f}")
