#!/usr/bin/env python3
"""WHALEFLIP step 10: collect the key numbers into whaleflip.json (labels, replay scores, costs, re-fill sources). usage: w10_summary.py"""
import sys, json, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W
X = json.load(open(f"{W.D}/exact.json")); E = json.load(open(f"{W.D}/engine_labels.json"))
R = json.load(open(f"{W.D}/replay.json"))["rows"]
out = {"exact_labels": {}, "engine_labels": {}, "refill_sources": {}, "scores": {}, "costs": json.load(open(f"{W.D}/costs.json"))}
for per in ("DEV", "VAL", "HOLD", "ALL"):
    for kind in ("t2", "rearm"):
        g = collections.defaultdict(list); ge = collections.defaultdict(list)
        for r in X:
            if r["kind"] == kind and r["covered"] and (per == "ALL" or r["period"] == per): g[r["xlab"]].append(r["pnl"])
        for r in E:
            if r["kind"] == kind and (per == "ALL" or r["period"] == per): ge[r["elab"]].append(r["pnl"])
        out["exact_labels"][f"{kind}|{per}"] = {k: W.st(v) for k, v in g.items()}
        out["engine_labels"][f"{kind}|{per}"] = {str(k): W.st(v) for k, v in ge.items()}
t2 = [r for r in X if r["kind"] == "t2" and r["covered"]]
out["shadow_vs_exact"] = {f"{a}->{b}": n for (a, b), n in collections.Counter((r["slab"], r["xlab"]) for r in t2).items()}
for v in ("A0.5", "A0.25", "A0"):
    for per in ("DEV", "VAL", "HOLD"):
        c = collections.Counter(); pn = collections.defaultdict(float)
        for r in R:
            if r["period"] != per: continue
            s = r["v"][v]["src"]; n = sum(s.values())
            for k, m in s.items():
                c[str(k)] += m / n
            if s.get("live", 0) < n: pn["refill_pnl"] += r["v"][v]["fill_pnl"] if s.get("live", 0) == 0 else 0
        out["refill_sources"][f"{v}|{per}"] = {k: round(x, 1) for k, x in c.items()} | {"refill_pnl": round(pn["refill_pnl"], 3)}
for fn in ("score_DEV_VAL.json", "score_HOLD.json"):
    out["scores"][fn] = json.load(open(f"{W.D}/{fn}"))
json.dump(out, open("/home/it/sniper/ops/strategies/presend/filters3/whaleflip/whaleflip.json", "w"), indent=1)
json.dump(out, open(f"{W.D}/whaleflip.json", "w"), indent=1)
print(json.dumps(out["refill_sources"], indent=0))
