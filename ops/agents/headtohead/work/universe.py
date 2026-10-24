#!/usr/bin/env python3
# every dump our engine logged in runs 1-5 -> race summary with all buy attempts in [S, S+5] (read-only)
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/headtohead/work")
from race import *
from fires_analysis_lib import kind, txinfo
R = json.load(open(W + "/runs.json"))
E = load_ext()
SOL_IN = 345679011
out = []; miss = 0
for d in R["dumps"]:
    txs = E.get(d["mint"], [])
    k0 = next((k for k, r in enumerate(txs) if r["sig"] == d["sig"]), None)
    if k0 is None: miss += 1; continue
    D = txs[k0]
    dtr = [t for t in D["tr"] if t["mint"] == d["mint"] and not t["buy"]]
    if not dtr: miss += 1; continue
    V, T = dtr[-1]["vsol"], dtr[-1]["vtok"]
    min_out = tokens_out(V, T, SOL_IN) * 100 // 105
    rc = race(txs, d["sig"], SOL_IN, min_out, horizon=5)
    if rc is None: miss += 1; continue
    seq = []
    for k, row in enumerate(rc["rows"]):
        r = row["r"]; kd = kind(r, rc["mint"])
        if kd in ("OTHER",): continue
        x = txinfo(r); x.update(kind=kd, ds=r["s"] - rc["S"], pre_ok=row["pre_ok"], post_ok=row["post_ok"], pm=round(row["pmult"], 4),
                              sol=sum(t["sol"] for t in row["trs"]) if row["trs"] else 0, k=k)
        x.pop("sig", None)
        seq.append(x)
    cr = rc["crossed"]
    out.append(dict(sig=d["sig"], mint=d["mint"], run=d["run"], S=rc["S"], iD=rc["iD"], dump_payer=D["signers"][0], dump_sol=dtr[-1]["sol"],
                    score=d["score"], passed=d["passed"], age=d["age"], t=d["t"], vsol=V, cross_k=cr, seq=seq))
json.dump(out, open(W + "/universe.json", "w"))
print("dumps", len(R["dumps"]), "reconstructed", len(out), "missing", miss)
