#!/usr/bin/env python3
"""r3: re-arm windows the live engine ARMED but did not fill while the shadow (row c) filled: where did our attempts land relative
to the paper's crossing dump x (same slot before/after it, next slot), and what happened (6042 = price above our limit)."""
import json, collections
EXT = "/home/moiz/sniper-data/filters3/obsstrat/ext"; CUT = 1793516400000000000
pairs = collections.Counter(); val = collections.defaultdict(float); ex = []
for run in ("r40", "r42"):
    pos = set()
    for l in open("/home/moiz/sniper-data/filters3/obsstrat/pos_join.jsonl"):
        d = json.loads(l)
        if d["run"] == run and d["kind"] == "rearm": pos.add((d["mint"], d["dump"]["sig"]))
    arm = {}
    for l in open(f"{EXT}/{run}.rearm_live.jsonl"):
        d = json.loads(l)
        if d["ev"] == "presend_live_arm": arm[(d["mint"], d["dump"]["sig"])] = d
    lands = collections.defaultdict(list)
    for l in open(f"{EXT}/{run}.rearm_land.jsonl"):
        d = json.loads(l); lands[d["mint"]].append((d.get("slot") or -1, d.get("idx"), d.get("res"), d.get("t_send"), d.get("send_slot")))
    for l in open(f"{EXT}/{run}.obs_sel.jsonl"):
        if '"ev":"rearm_window"' not in l: continue
        x = json.loads(l); k = (x["mint"], x["dump"]["sig"])
        f = ((x.get("rows") or {}).get("c") or {}).get("fill")
        if not f or k in pos or k not in arm: continue
        per = "DEV" if x["dump"]["t"] < CUT else "VAL"
        X = f["x"]; pap = ((f.get("px") or {}).get("0.65") or {}).get("live", 0) / 1e3
        L = [z for z in lands[x["mint"]] if X["slot"] - 1 <= z[0] <= X["slot"] + 2]
        same = [z for z in L if z[0] == X["slot"]]
        cat = []
        if not L: cat.append("no attempt landed x-1..x+2")
        else:
            if any(z[1] is not None and z[1] < X["idx"] for z in same): cat.append("landed in x slot BEFORE x")
            if any(z[1] is not None and z[1] > X["idx"] for z in same): cat.append("landed in x slot AFTER x (still failed)")
            if not same: cat.append("none in x slot")
            if any(z[0] == X["slot"] + 1 for z in L): cat.append("landed x+1 (failed)")
        key = (per, " & ".join(cat)); pairs[key] += 1; val[key] += pap
print("re-arm windows: live armed, no live fill, shadow row c filled (r40 + r42)")
for k in sorted(pairs): print(f"  {k[0]} {k[1]:70s} n {pairs[k]:4d} paper(0.65, gross) {val[k]:+7.3f}")
