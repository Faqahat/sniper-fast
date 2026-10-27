#!/usr/bin/env python3
"""DIPML pre-send side: LIVE-measured pre-send per window (filter agent's per-window table pw8/pw26: realized + rent back
- failed-try fees, chain), restricted to the TEST period (arm time >= 10-26 14:40 UTC = first TEST slot).
'before' = what live did (no QUIET for r24/r25 FRA/AMS; r26 had no QUIET live either). 'after' = QUIET replayed
(exact replay) - NOTE AMS r24/r25 were QUIET's dev set, so only r26 is a clean holdout for 'after'.
Active hours = arm-time segments split on gaps > 20 min (+2 min tail), as filter/daily/daily.py."""
import json, collections
D = "/home/moiz/sniper-data/presend_filter/daily"
W = json.load(open(f"{D}/pw8.json")) + json.load(open(f"{D}/pw26.json"))
T0 = 1793025600e9 if False else None
import numpy as np
S = np.load("/home/moiz/sniper-data/dipml/slots.npy"); i = np.searchsorted(S["slot"], 461_701_097); T0 = int(S["bt"][i]) * 1e9
H = 3600e9
def summarize(ws, label):
    by = collections.defaultdict(list)
    for w in ws: by[w["run"]].append(w)
    tot_h = 0; out = {}
    for r, xs in sorted(by.items()):
        ts = sorted(w["t"] for w in xs); segs = []; a = p = ts[0]
        for t in ts[1:]:
            if t - p > 20 * 60e9: segs.append((a, p + 120e9)); a = t
            p = t
        segs.append((a, p + 120e9)); h = sum(b - a for a, b in segs) / H; tot_h += h
        f = [w for w in xs if w["filled"]]
        out[r] = dict(h=round(h, 2), fills=len(f), before=round(sum(w["before"] for w in xs), 3), after=round(sum(w["after"] for w in xs), 3),
                      spend=round(float(np.mean([w["spend"] for w in f])) / 1e9, 2) if f else None,
                      win=round(np.mean([(w.get("net") if w.get("net") is not None else w["before"]) > 0 for w in f]), 2) if f else None)
    b = sum(v["before"] for v in out.values()); a = sum(v["after"] for v in out.values()); nf = sum(v["fills"] for v in out.values())
    print(f"{label}: {tot_h:.2f} active h | live (MEASURED) {b:+.3f} = {b / tot_h * 24:+.2f}/day | QUIET replay {a:+.3f} = {a / tot_h * 24:+.2f}/day | fills {nf} = {nf / tot_h * 24:.0f}/day")
    for r, v in out.items(): print("   ", r, v)
    return dict(hours=tot_h, live_day=b / tot_h * 24, quiet_day=a / tot_h * 24, fills_day=nf / tot_h * 24, runs=out)
res = {"test": summarize([w for w in W if w["t"] >= T0], "TEST (10-26 19:40 PKT ->)"),
       "pre_test": summarize([w for w in W if w["t"] < T0], "pre-TEST"),
       "holdout_r26": summarize([w for w in W if w["run"] == "ams:r26"], "AMS r26 only (QUIET holdout)")}
json.dump(res, open("/home/moiz/sniper-data/dipml/presend_test.json", "w"), indent=1, default=float)
