#!/usr/bin/env python3
# read-only diagnostics of the replayed rows: fidelity by mayhem / quote, outliers of x vs r
import json, gzip, collections
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/fifaw/selection/sel_dataset.jsonl.gz", "rt")]
rep = [r for r in R if r.get("rep")]
g = collections.defaultdict(lambda: [0, 0, 0])
for r in rep:
    k = (r["att"], r["mayhem"], r["quote_sol"], r["out_ok"])
    g[k][0] += 1; g[k][1] += r.get("rep_bad", 0); g[k][2] += r.get("rep_n", 0)
for k, v in sorted(g.items()): print("att,mayhem,quote,out_ok", k, "launches", v[0], "mismatch", v[1], "of", v[2])
print("population mayhem", sum(r["mayhem"] for r in R), "quote_sol=0", sum(1 for r in R if not r["quote_sol"]), "out_ok", sum(r["out_ok"] for r in R))
print("attempted: mayhem", sum(r["mayhem"] for r in R if r["att"]), "quote0", sum(1 for r in R if r["att"] and not r["quote_sol"]), "out_ok", sum(r["out_ok"] for r in R if r["att"]))
for r in rep:
    if r["att"] and r.get("x_5s") and r.get("r_5s") and abs(r["x_5s"] / r["r_5s"] - 1) > 0.01:
        print("outlier", r["mint"][:6], "mayhem", r["mayhem"], "q", r["quote_sol"], "x5", round(r["x_5s"], 3), "r5", round(r["r_5s"], 3), "w5", round(r.get("w_5s") or 0, 3), "bad", r["rep_bad"], r["rep_n"], "max_vsol", r["max_vsol"])
