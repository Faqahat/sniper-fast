#!/usr/bin/env python3
# PRE-SEND V2: the finalists on the FRESH hours R5 (10-25 09:56 PKT -> recording end - 30 min; built after every choice was made).
# Same engine and costs as v2final; per config: SOL/24h, fills, net per fill, fill rate, clock hours, worst hour.
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {"R5": E.load("R5")}
D = R.G["DD"]["R5"]; h = D["hours"]
F = json.load(open(f"{V.OUT}/finalists.json")); F.update(json.load(open(f"{V.OUT}/finalists_hq.json"))); F.update(json.load(open(f"{V.OUT}/finalists_h6.json")))
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
say(f"R5 fresh hours {V.WIN['R5'][0]} -> {V.WIN['R5'][1]} PKT ({h:.2f} h)")
res = {}
for name, cfg in F.items():
    r = R.ev(cfg, ("R5",), detail=True)["R5"]
    hr = E.hourly(r, "R5")
    res[name] = dict(per24=r["per24"], pnl=r["pnl"], fills=r["fill"], armed=r["armed"], per_fill=r["per_fill"], gross_fill=r["gross_per_fill"], hourly=hr.tolist())
    say(f"  {name:22s} {r['pnl']:+7.3f} SOL in {h:.1f} h ({r['per24']:+6.2f}/24h) | fills {r['fill']} of {r['armed']} armed ({100 * r['fill_rate']:.1f}%) | "
        f"after pump fees {r['gross_per_fill']:+.4f}/fill, net {r['per_fill']:+.4f}/fill | clock hours " + " ".join(f"{x:+.2f}" for x in hr))
json.dump(res, open(f"{V.OUT}/r5_eval.json", "w"), default=float)
open(f"{V.OUT}/r5_eval.txt", "w").write("\n".join(LOG) + "\n")
