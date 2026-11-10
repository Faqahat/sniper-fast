#!/usr/bin/env python3
"""c1: calibrate the SELECTION census paper (paper_065_msol: 0.65 SOL right after a >= 12% dump, sold before the first trade >= 200 ms
later; gross, zero latency, no costs) against LIVE T2 realized on the same (mint, crossing wallet) in r42; then what the census's
classes would be worth at that calibration (ESTIMATE). Wallets in the census are 8-char prefixes."""
import json, collections
CUT = 1793516400000000000; HRS = {"DEV": 32.19, "VAL": 20.61}
live = {}
for l in open("/home/it/sniper-data/filters3/obsstrat/pos_join.jsonl"):
    d = json.loads(l)
    if d["run"] == "r42" and d["kind"] == "t2" and (d.get("trig") or {}).get("wallet"): live[(d["mint"], d["trig"]["wallet"][:8])] = d
agg = collections.defaultdict(lambda: [0, 0.0, 0.0, 0]); cls = collections.defaultdict(lambda: [0, 0.0])
for l in open("/home/it/sniper-data/filters3/obsstrat/ext/r42.select.jsonl"):
    x = json.loads(l); per = "DEV" if x["t"] < CUT else "VAL"
    p = ((x.get("outcome") or {}).get("paper_065_msol"))
    w10 = ((x.get("outcome") or {}).get("in_window") or [False])[0]
    if p is not None and w10:
        c = cls[(per, x["class"], x["live_arms"])]; c[0] += 1; c[1] += p / 1e3
    L = live.get((x["mint"], x["w"]))
    if x["class"] == "first_buy" and x["live_arms"] and L is not None:
        a = agg[(per, p is not None)]; a[0] += 1; a[1] += (p or 0) / 1e3; a[2] += L["pnl"]; a[3] += 1
print("live T2 fills matched to a census crossing (r42): [per, census paper fill?] n, paper SOL (gross), live realized SOL")
for k in sorted(agg): print("  ", k, agg[k][0], round(agg[k][1], 3), round(agg[k][2], 3))
print("census paper fills inside 10 slots of the crossing, by class / live-armable (gross, no costs):")
for k in sorted(cls): print("  ", k, cls[k][0], round(cls[k][1], 3))
