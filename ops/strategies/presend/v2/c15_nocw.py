#!/usr/bin/env python3
# PRE-SEND V2 step c15: the COHORT test (memory rule: always report it). Remove the BUYS of the 541 consistent-winner bots
# (ops/overnight/dip/drop_cw.json) after our entry, and re-run the finalists. If V2 lives on their buying after us, it collapses.
# Built with: PSV2_DROP=.../drop_cw.json PSV2_TAG=_nocw python3 v2lib.py <day>
import os, sys, json, importlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
F = json.load(open(f"{V.OUT}/finalists.json")); F.update(json.load(open(f"{V.OUT}/finalists_h6.json")))
names = ["P1_as_run_0.2_k4", "A_k4_0.55", "B_k8_0.55", "A6_k4_0.55", "B6_k8_0.55", "C6_k8_1.0", "D6_k12_1.0"]
res = {}
for tag in ("", "_nocw", "_norand"):
    os.environ["PSV2_TAG"] = tag
    import v2eng as E; importlib.reload(E)
    import v2run as R; importlib.reload(R)
    R.G["DD"] = {d: E.load(d) for d in V.DAYS}
    for n in names:
        r = R.ev(F[n], V.DAYS); tr = R.agg(r, R.TRAIN); te = R.agg(r, R.TEST)
        res[f"{n}{tag}"] = dict(train=tr["per24"], test=te["per24"], test_fill=te["per_fill"], days={d: r[d]["per24"] for d in V.DAYS})
        print(f"{ {"": "as recorded   ", "_nocw": "cohort REMOVED", "_norand": "random REMOVED"}[tag]} {n:18s}: TRAIN {tr['per24']:+6.2f}/d | TEST {te['per24']:+6.2f}/d ({te['per_fill']:+.4f}/fill) | "
              + " ".join(f"{d} {r[d]['per24']:+6.2f}" for d in V.DAYS), flush=True)
json.dump(res, open(f"{V.OUT}/c15_nocw.json", "w"), default=float)
