#!/usr/bin/env python3
"""Quick live check of a running segment: quote error per venue (free sims at decision time vs our prediction),
exec counters, verdicts. usage: quick.py <seg>"""
import json, collections, sys, os
os.chdir(f"/root/arb-lab/runs/{sys.argv[1]}")
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
e = collections.defaultdict(list)
for l in open("sims.jsonl"):
    x = json.loads(l); d = x.get("delivered")
    if not d or len(d) < 2 or not x.get("predicted_mid"): continue
    st = "state" if x.get("trigger_feed") == "state" else "decoded"
    e[(st, x["buy_venue"], "leg1")].append((d[0] - x["predicted_mid"]) / x["predicted_mid"] * 1e4)
    if d[0] and x.get("predicted_back"):
        e[(st, x["sell_venue"], "leg2 rate")].append(((d[1] / d[0]) - (x["predicted_back"] / x["predicted_mid"])) / (x["predicted_back"] / x["predicted_mid"]) * 1e4)
for k, v in sorted(e.items(), key=lambda x: -len(x[1])):
    if len(v) >= 4: print(k, len(v), "bps p10/p50/p90", q(v, .1), q(v, .5), q(v, .9))
s = json.loads(open("status.jsonl").readlines()[-1])
print(s["exec"]["counts"]); print({k: s["exec"]["sending"][k] for k in ("sent", "landed", "wins", "failed_fees_lamports", "profit_lamports")})
o = [json.loads(l) for l in open("outcomes.jsonl")]
print("verdicts:", collections.Counter("WIN" if x.get("ok") else "landed-fail" if x.get("landed") else "gated" if "sim_gated" in json.dumps(x) else "not landed" for x in o))
g = [v for x in o for v in x.values() if isinstance(v, str) and v.startswith("sim_gated")]
for m in g[-5:]: print("  gate:", m[:200])
