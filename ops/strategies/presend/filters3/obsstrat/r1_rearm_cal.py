#!/usr/bin/env python3
"""r1: re-arm shadow (obs rearm_window, row c) vs live re-arm (arms / skips / fills, realized) on the same (mint, dump sig).
Gives the per-window calibration of the re-arm paper and where the paper's extra fills come from. r38..r42 (DEV+VAL)."""
import json, collections, sys
EXT = "/home/it/sniper-data/filters3/obsstrat/ext"; CUT = 1793516400000000000
HRS = {"DEV": 74.35 - 18.42, "VAL": 20.61}   # r37 has no live re-arm
pos = {}
for line in open("/home/it/sniper-data/filters3/obsstrat/pos_join.jsonl"):
    d = json.loads(line)
    if d["kind"] == "rearm": pos[(d["run"], d["mint"], d["dump"]["sig"])] = d
res = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0.0, 0]))  # cat -> per -> [n, paper65 SOL, live SOL, paper_wins]
pairs = []
for run in ["r38", "r39", "r40", "r41", "r42"]:
    arm, skip, dis = {}, {}, {}
    for line in open(f"{EXT}/{run}.rearm_live.jsonl"):
        d = json.loads(line); k = (d["mint"], (d.get("dump") or {}).get("sig"))
        if d["ev"] == "presend_live_arm": arm[k] = d
        elif d["ev"] == "presend_live_skip": skip[k] = d.get("why")
    disw = {}
    for line in open(f"{EXT}/{run}.rearm_live.jsonl"):
        d = json.loads(line)
        if d["ev"] == "presend_live_disarm": disw[(d["mint"], d.get("trig_slot"))] = d
    for line in open(f"{EXT}/{run}.obs_sel.jsonl"):
        if '"ev":"rearm_window"' not in line: continue
        x = json.loads(line); k = (x["mint"], x["dump"]["sig"]); per = "DEV" if x["dump"]["t"] < CUT else "VAL"
        c = (x.get("rows") or {}).get("c") or {}; f = c.get("fill")
        pap = None
        if f:
            px = (f.get("px") or {}).get("0.65") or {}
            pap = px.get("live")
        live = pos.get((run,) + k)
        if live is not None: cat = "live_fill"
        elif k in arm: cat = "live_armed_nofill"
        elif k in skip: cat = "live_skip:" + str(skip[k])
        else: cat = "live_none"
        o = res[(cat, "paper_fill" if f else "paper_nofill")][per]
        o[0] += 1
        if pap is not None: o[1] += pap / 1e3 - 0.0; o[3] += pap > 0
        if live is not None: o[2] += live["pnl"]
        if f and live is not None:
            pairs.append(dict(run=run, per=per, mint=x["mint"], paper=pap / 1e3 if pap is not None else None, live=live["pnl"],
                              ms_after_arm=f.get("ms_after_arm"), sad=f.get("slots_after_dump"), live_sat=live.get("sat"),
                              r5=x.get("r5_skip"), x_slot=(f.get("x") or {}).get("slot"), live_slot=live["fslot"]))
print("paper = row c, size 0.65, policy 'live' (gross mSOL/1000 = SOL); live = realized SOL")
print(f"{'category':40s} {'per':4s} {'n':>5s} {'paper SOL':>10s} {'live SOL':>9s}")
for cat in sorted(res):
    for per in ("DEV", "VAL"):
        o = res[cat][per]
        if o[0]: print(f"{cat[0]+' / '+cat[1]:40s} {per:4s} {o[0]:5d} {o[1]:+10.3f} {o[2]:+9.3f}")
json.dump(pairs, open("/home/it/sniper-data/filters3/obsstrat/rearm_pairs.json", "w"))
for per in ("DEV", "VAL"):
    P = [p for p in pairs if p["per"] == per and p["paper"] is not None]
    if not P: continue
    same = [p for p in P if p["x_slot"] == p["live_slot"]]
    print(per, "both filled:", len(P), "paper", round(sum(p["paper"] for p in P), 3), "live", round(sum(p["live"] for p in P), 3),
          "| same fill slot", len(same), "paper", round(sum(p["paper"] for p in same), 3), "live", round(sum(p["live"] for p in same), 3))
