#!/usr/bin/env python3
# READ-ONLY. Freeze, BEFORE the overnight outcomes are read, one exit per candidate gate, fitted on pre-night data only
# (historical random sample, all of it, + forward run 1). Objective = TOTAL GAIN: the pooled mean realistic PnL (2 SOL,
# land <= 100 txs), with the worst-period mean shown. Candidates: time exits and fat-tail "runner" exits.
import json, sys, time, statistics as st
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, hostbad, C
from fwdrows import build
R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
H = [r for r in R if r["in_rand"] and not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8 and r["has_path"] and not r.get("bad_ev")]
H.sort(key=lambda r: r["slot"]); cut = H[int(len(H) * .6)]["slot"]
F = [o for o in build("/root/race/paper_fwd.log", "/root/race/fwd_onchain.jsonl", "/root/race/paths_fwd.jsonl", verbose=False) if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
P = {"hist-train": [r for r in H if r["slot"] < cut], "hist-test": [r for r in H if r["slot"] >= cut], "fwd1": F}
pre = json.load(open("/root/race/PREREG_v2.json"))["prereg"]
GATES = {"Gate B": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2 and r["n_len"] <= 12,
         "Gate B strict (bundle>=3)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 3 and r["n_len"] <= 12,
         "Gate B no-name (dev>=3 & bundle>=2)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2,
         "FIX base": lambda r: True}
for k, p in enumerate(pre):
    GATES[f"PREREG_v2 #{k + 1}"] = (lambda r, rule=p["rule"]: all(C[c](r) for c in rule))
XN = [x for x in EXITS if x.startswith("time ") or x.startswith("runner") or x in [p["exit"] for p in pre]]
out = {"written_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "gates": {}}
for gn, fn in GATES.items():
    g = {pk: [r for r in rows if fn(r)] for pk, rows in P.items()}
    best = None
    for xn in XN:
        per = {pk: [sim(r, EXITS[xn]) for r in rows] for pk, rows in g.items()}
        pooled = [x for v in per.values() for x in v]
        if not pooled:
            continue
        sc = st.mean(pooled)
        if best is None or sc > best[0]:
            best = (sc, xn, {pk: (len(v), st.mean(v) if v else float("nan")) for pk, v in per.items()})
    run = max((x for x in XN if x.startswith("runner")), key=lambda xn: st.mean([sim(r, EXITS[xn]) for v in g.values() for r in v]))
    out["gates"][gn] = {"exit": best[1], "pooled_mean": best[0], "periods": best[2], "best_runner_exit": run}
    print(f"{gn:38} best exit {best[1]:42} pooled {best[0]:+.2%} | " + " ".join(f"{pk} n{n} {m:+.1%}" for pk, (n, m) in best[2].items()) + f" | best runner: {run}")
json.dump(out, open("/root/race/EXIT_FREEZE.json", "w"), indent=1)
print("EXIT_FREEZE.json written", out["written_utc"])
