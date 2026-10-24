#!/usr/bin/env python3
# READ-ONLY: slippage-limit coverage = share of outside buys inside each exit window (after our insert) whose decoded
# limit exists in rp.load_slip(); per set and mode (fills only).
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/fifaw/copy")
import q6, rp
from multiprocessing import Pool
SETS = q6.SETS; RES = json.load(open("q6_res.json"))["res"]
want = {"(a) oracle: its attempts", "(a') oracle: its filled buys", "(b) walk-forward deployer list (>=2 att, >=10%)", "(z) random control launches"}
mints = set().union(*[set(SETS[s]) for s in want])
def work(job):
    run, b, ms = job; q6.init(); tra = q6.read(run, b, ms); out = {}
    for m, tr in tra.items():
        r = RES.get(m)
        if not r: continue
        c = q6.L[m]; S = c["slot"]; o = {}
        for mode, d in r["modes"].items():
            if not d.get("v"): continue
            idx = d["idx"]; bs = max(S, tr[idx - 1]["s"]) if idx > 0 else S
            for e, w in q6.EXW.items():
                win = [t for t in tr[idx:] if t["buy"] and (t["s"] <= bs + 1 if w is None else (t["s"] - bs) * q6.SLOT < w)]
                o[(mode, e)] = (len(win), sum(1 for t in win if t["sig"] in q6.SL))
        out[m] = {f"{k[0]}|{k[1]}": v for k, v in o.items()}
    return out
if __name__ == "__main__":
    byb = collections.defaultdict(set)
    for m in mints:
        if m in q6.L: byb[(q6.L[m]["run"], rp.bucket(m))].add(m)
    C = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, [(r, b, ms) for (r, b), ms in byb.items()]): C.update(o)
    out = {}
    for sn in want:
        agg = collections.defaultdict(lambda: [0, 0])
        for m in SETS[sn]:
            for k, (n, k_) in C.get(m, {}).items(): agg[k][0] += n; agg[k][1] += k_
        out[sn] = {k: round(v[1] / v[0], 3) if v[0] else None for k, v in agg.items()}
        print(sn[:34], " ".join(f"{k}:{out[sn][k]}" for k in sorted(out[sn]) if k.split('|')[0] in ("L45", "L75", "D0.15", "D1")))
    json.dump(out, open("q6_slip_coverage.json", "w"), indent=1)
