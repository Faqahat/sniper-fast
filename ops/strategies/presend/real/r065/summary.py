#!/usr/bin/env python3
"""REPLAY_065: the report's numbers from results.json / wallet.json / paper.json / notrade.json (+ per-size no-trade lines,
worst trades, swings, running drawdown vs the 0.5 SOL kill switch). Writes summary.json."""
import sys, json, pickle, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core
B = core.BASE
R = json.load(open(f"{B}/results.json")); W = json.load(open(f"{B}/wallet.json"))
RENT = 1_508_820 / 1e9
SZ = ("live", "s50", "s65", "s100")
T = R["trades"]
def val(t, sz): return t["live"] if sz == "live" else t[sz]
out = {"wallet": {}, "notrade": {}, "worst": {}, "swing": {}, "dd": {}}
for run in ("r24", "r25"):
    segs = [k for k in W if k.startswith(run + ":")]
    fail = sum(W[k].get("ps_fail_fee", 0) + W[k].get("reg_fail_fee", 0) for k in segs)
    rent = sum(W[k].get("ps_rent_back", 0) for k in segs)
    chg = sum(W[k]["change"] for k in segs)
    o = {"wallet_change_measured": chg, "fail_fees": fail, "rent_back": rent}
    for sz in SZ:
        tr = sum(val(t, sz) or 0 for t in T if t["run"] == run)
        o[sz] = tr + rent - fail
    out["wallet"][run] = o
    for kind in ("ps", "reg"):
        Q = [t for t in T if t["run"] == run and t["kind"] == kind]
        Z = [t for t in Q if t["n_between"] == 0]
        out["notrade"][f"{run}:{kind}"] = {sz: dict(zero=sum(val(t, sz) or 0 for t in Z), total=sum(val(t, sz) or 0 for t in Q), without=sum(val(t, sz) or 0 for t in Q if t["n_between"] > 0)) for sz in SZ}
        out["notrade"][f"{run}:{kind}"]["n_zero"] = len(Z)
for kind in ("ps", "reg"):
    Q = [t for t in T if t["kind"] == kind]
    w = sorted(Q, key=lambda t: t["s65"])[:5]
    out["worst"][kind] = [dict(run=t["run"], t=time.strftime("%m-%d %H:%M", time.gmtime(t["t"] / 1e9 + 18000)), mint=t["mint"], live=t["live"], s65=t["s65"], s100=t["s100"],
                               why_live=t["why_live"], why65=t["why65"], drop65=t["drop65"], nb=t["n_between"]) for t in w]
    out["swing"][kind] = {sz: dict(sd=float(np.std([val(t, sz) for t in Q])), min=float(min(val(t, sz) for t in Q)), max=float(max(val(t, sz) for t in Q)),
                                   per_fill=float(np.mean([val(t, sz) for t in Q]))) for sz in SZ}
# running drawdown per engine segment (trades in time order + their rent back; failed-try fees spread evenly over the segment's trades)
for run in ("r24", "r25"):
    for seg in sorted({t["seg"] for t in T if t["run"] == run}):
        Q = sorted([t for t in T if t["run"] == run and t["seg"] == seg], key=lambda t: t["t"])
        k = f"{run}:{seg}"; ff = (W[k].get("ps_fail_fee", 0) + W[k].get("reg_fail_fee", 0)) / max(len(Q), 1)
        d = {}
        for sz in SZ:
            c = 0; peak = 0; mdd = 0; low = 0
            for t in Q:
                c += (val(t, sz) or 0) + (RENT if t["kind"] == "ps" else 0) - ff
                peak = max(peak, c); mdd = min(mdd, c - peak); low = min(low, c)
            d[sz] = dict(max_drawdown=mdd, lowest_vs_start=low, end=c)
        out["dd"][k] = d
json.dump(out, open(f"{B}/summary.json", "w"), indent=1)
for k, v in out["wallet"].items(): print("wallet", k, {a: round(b, 4) for a, b in v.items()})
for k, v in out["notrade"].items(): print("notrade", k, v["n_zero"], {sz: {a: round(b, 4) for a, b in v[sz].items()} for sz in SZ})
for k, v in out["dd"].items(): print("dd", k, {sz: {a: round(b, 3) for a, b in v[sz].items()} for sz in SZ})
for k, v in out["swing"].items(): print("swing", k, {sz: {a: round(b, 4) for a, b in v[sz].items()} for sz in SZ})
for k, v in out["worst"].items():
    for x in v: print("worst", k, x)
